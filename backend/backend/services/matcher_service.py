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
    return {"top_match": _format_result(top), "alternatives": [_format_result(r) for r in candidates[1:]]}


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
    """格式化单条匹配结果，同时带出主数据字段供前端渲染。"""
    matcher = get_matcher()
    product_code = str(r.get("标准产品编码", "") or r.get("product_code", ""))
    product_name = str(r.get("标准产品名称", "") or r.get("product_name", ""))
    # 从商品库主数据补充品类、单位、是否益海等字段
    extra = {}
    if matcher and product_code and hasattr(matcher, "df"):
        rows = matcher.df[matcher.df["标准产品编码"].astype(str).str.strip() == product_code]
        if not rows.empty:
            row = rows.iloc[0]
            extra = {
                "cat1": str(row.get("一级分类", "")),
                "unit": str(row.get("基本单位", "")),
                "is_yihai": str(row.get("是否益海", "")),
                "brand": str(row.get("品牌", "")),
                "spec": str(row.get("规格", "")),
            }
    return {
        "product_code": product_code,
        "product_name": product_name,
        "confidence": round(float(r.get("confidence", 0)), 2),
        "score": round(float(r.get("score", 0)), 4),
        "detected_brand": str(r.get("detected_brand", "")),
        "normalized_spec": str(r.get("normalized_spec", "")),
        "core_name": str(r.get("core_name", "")),
        "attributes": r.get("attributes", []),
        "cat1": extra.get("cat1", ""),
        "unit": extra.get("unit", ""),
        "is_yihai": extra.get("is_yihai", ""),
        "brand": extra.get("brand", ""),
        "spec": extra.get("spec", ""),
    }
