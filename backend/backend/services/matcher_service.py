"""封装匹配算法调用，不修改原有算法源码"""
import sys
import os
import logging

logger = logging.getLogger(__name__)

# 从 config 中获取路径（已基于 __file__ 自动计算，支持迁移）
from backend.config import MATCHING_ALGORITHM_DIR, PREPROCESS_DIR

if MATCHING_ALGORITHM_DIR not in sys.path:
    sys.path.insert(0, MATCHING_ALGORITHM_DIR)

if PREPROCESS_DIR not in sys.path:
    sys.path.insert(0, PREPROCESS_DIR)

from normalizer.main import process_single_record

from backend.services.ai_match_check import check_matches_batch, AI_MATCH_CHECK_ENABLED

_matcher_instance = None


def get_matcher():
    """获取匹配器单例（自动加载最新数据库）"""
    global _matcher_instance
    if _matcher_instance is not None:
        return _matcher_instance

    from service import get_matcher as _get_matcher
    _matcher_instance = _get_matcher()
    logger.info("匹配算法初始化完成")
    return _matcher_instance


def match_single(query_text: str, top_n: int = 10) -> dict:
    """
    单条商品匹配（含置信度计算）。
    参考 batch_match.py 的流程:
      1. process_single_record 归一化查询
      2. query_extended 召回候选
      3. compute_confidence 逐条计算置信度
    """
    matcher = get_matcher()

    # Step 1: 归一化查询（提取品牌/规格/核心名，用于置信度评分）
    query_info = process_single_record(query_text.strip(), brands_sorted=matcher.brands)

    # Step 2: 召回候选（传入 query_info 避免重复计算）
    candidates = matcher.query_extended(query_text, top_n=top_n, query_info=query_info)

    # Step 3: 逐条计算置信度
    for c in candidates:
        c["confidence"] = matcher.compute_confidence(query_info, c)

    if not candidates:
        return {"top_match": None, "alternatives": []}

    top = candidates[0]
    top_match = _format_result(top)

    alternatives = [_format_result(r) for r in candidates[1:]]

    return {"top_match": top_match, "alternatives": alternatives}




def match_single_preprocessed(query_text: str, top_n: int = 10, query_info=None) -> dict:
    """
    单条商品匹配（基于已预处理的查询文本）。
    可选传入 query_info 复用归一化结果，避免重复调用 process_single_record。
    """
    matcher = get_matcher()
    if query_info is None:
        query_info = process_single_record(query_text.strip(), brands_sorted=matcher.brands)
    candidates = matcher.query_extended(query_text, top_n=top_n, query_info=query_info)
    for c in candidates:
        c["confidence"] = matcher.compute_confidence(query_info, c)
    if not candidates:
        return {"top_match": None, "alternatives": []}
    top = candidates[0]
    top_match = _format_result(top)
    return {"top_match": top_match, "alternatives": [_format_result(r) for r in candidates[1:]]}


def _apply_ai_match_check_batch(results: list) -> None:
    """批量 AI 兜底复核：收集「查询商品 vs 匹配标准品」配对，分批 + 并发核对后回填。

    复核失败（无 key / 超时 / 解析失败）的位置保持规则结果不变。
    """
    if not AI_MATCH_CHECK_ENABLED:
        return
    if not results:
        return

    pairs = []
    valid_indices = []
    for i, r in enumerate(results):
        top = r.get("top_match")
        if top and top.get("product_name"):
            pairs.append((str(r.get("raw_name", "")).strip(), str(top["product_name"])))
            valid_indices.append(i)

    if not pairs:
        return

    check_results = check_matches_batch(pairs)

    for k, idx in enumerate(valid_indices):
        if k >= len(check_results):
            break
        is_match, reason = check_results[k]
        top = results[idx].get("top_match")
        if not top:
            continue
        if is_match is False:
            top["ai_rejected"] = True
            top["ai_reason"] = reason
            try:
                top["confidence"] = round(min(float(top.get("confidence", 0)), 0.3), 2)
            except (ValueError, TypeError):
                top["confidence"] = 0.3
        elif is_match is True:
            top["ai_rejected"] = False


def match_batch_preprocessed(items: list, preprocessed_map: dict, top_n: int = 10,
                             query_info_map=None, progress_callback=None) -> list:
    """
    批量商品匹配（使用已预处理名称 + 可选预计算 query_info 缓存）。

    Args:
        items: [{"index": 0, "raw_name": "xxx"}, ...]
        preprocessed_map: {item_index: preprocessed_name}
        top_n: 返回结果数量
        query_info_map: {item_index: query_info_dict}，预处理阶段缓存的归一化结果，避免重复计算
        progress_callback: 可选回调，每处理一条调用 callback(current, total)
    """
    results = []
    total = len(items)
    for item in items:
        raw = item.get("raw_name", "")
        idx = item.get("index", 0)
        preprocessed_name = preprocessed_map.get(idx, "")
        query = preprocessed_name if preprocessed_name else raw
        query_info = (query_info_map or {}).get(idx)

        if progress_callback:
            progress_callback(idx + 1, total)

        if not query.strip():
            results.append({
                "index": idx,
                "raw_name": raw,
                "top_match": None,
                "alternatives": [],
            })
            continue

        match_res = match_single_preprocessed(query, top_n=top_n, query_info=query_info)
        results.append({
            "index": idx,
            "raw_name": raw,
            "top_match": match_res["top_match"],
            "alternatives": match_res["alternatives"],
        })

    # 批量 AI 兜底复核（分批 + 并发，避免一条一调）
    _apply_ai_match_check_batch(results)

    return results


def match_batch(items: list, top_n: int = 10) -> list:
    """
    批量商品匹配。
    items: [{"index": 0, "raw_name": "xxx"}, ...]
    """
    results = []
    total = len(items)
    for i, item in enumerate(items):
        logger.info(f"匹配进度: {i+1}/{total} - {item['raw_name'][:30]}")
        match_res = match_single(item["raw_name"], top_n=top_n)
        results.append({
            "index": item["index"],
            "raw_name": item["raw_name"],
            "top_match": match_res["top_match"],
            "alternatives": match_res["alternatives"],
        })
    return results


def _format_result(r: dict) -> dict:
    """格式化单条匹配结果（字段已由 matcher 预提取，O(1) 读取，不走 DataFrame 扫描）。"""
    product_code = str(r.get("标准产品编码", "") or r.get("product_code", ""))
    product_name = str(r.get("标准产品名称", "") or r.get("product_name", ""))

    return {
        "product_code": product_code,
        "product_name": product_name,
        "confidence": round(float(r.get("confidence", 0)), 2),
        "score": round(float(r.get("score", 0)), 4),
        "detected_brand": str(r.get("detected_brand", "")),
        "normalized_spec": str(r.get("normalized_spec", "")),
        "core_name": str(r.get("core_name", "")),
        "attributes": r.get("attributes", []),
        "cat1": str(r.get("_cat1", "")),
        "unit": str(r.get("_unit", "")),
        "is_yihai": str(r.get("_is_yihai", "")),
        "brand": str(r.get("_brand_full", "")),
        "spec": str(r.get("_spec_full", "")),
    }
