# -*- coding: utf-8 -*-
"""AI 匹配复核：规则算法匹配出候选后，AI 兜底判断核心产品是否一致。

用于拦截「字面相似但核心商品完全不同」的错配，例如：
  - 「特级雪燕」误匹配到「特级虾皮（散称）」
  - 「芒果果酱」误匹配到「芒果」

批量场景下采用「分批 + 并发」调用，避免一条一调导致上千条超时。
"""
import os
import json
import logging
import re
from typing import List, Optional, Tuple

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 是否启用 AI 匹配复核（默认关闭；需要时通过环境变量开启）
AI_MATCH_CHECK_ENABLED = os.environ.get("AI_MATCH_CHECK_ENABLED", "0") == "1"

# 批量复核参数：每批条数、并发批数
AI_MATCH_CHECK_BATCH_SIZE = int(os.environ.get("AI_MATCH_CHECK_BATCH_SIZE", "30"))
AI_MATCH_CHECK_MAX_WORKERS = int(os.environ.get("AI_MATCH_CHECK_MAX_WORKERS", "5"))

# 触发 AI 复核的置信度区间（含下限，不含上限）
AI_MATCH_CHECK_MIN_CONF = float(os.environ.get("AI_MATCH_CHECK_MIN_CONF", "0.2"))
AI_MATCH_CHECK_MAX_CONF = float(os.environ.get("AI_MATCH_CHECK_MAX_CONF", "0.6"))

# AI 确认核心产品一致后，赋予的置信度
AI_MATCH_CHECK_CONFIRMED_CONF = float(os.environ.get("AI_MATCH_CHECK_CONFIRMED_CONF", "0.8"))


def _parse_bool(v) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.lower() == "true":
            return True
        if v.lower() == "false":
            return False
    return None


def check_match_semantics(
    query_name: str,
    matched_name: str,
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    timeout: int = 15,
) -> Tuple[Optional[bool], str]:
    """单条 AI 复核（测试/兜底用）。返回 (is_match, reason)，失败返回 (None, '')。"""
    key = api_key or DEEPSEEK_API_KEY
    if not key:
        return None, ""
    if not query_name or not matched_name:
        return None, ""

    prompt = f"""你是商品对品复核专家。判断下面两个商品名称是否指「同一个核心产品」。

核心产品的判断标准：
- 核心品类 + 核心食材/原料必须一致才算匹配。
- 规格、包装、品牌、容量不同，但核心产品一致 → 算匹配。
  例：「金龙鱼大豆油5L」 vs 「大豆油5L×4」 → 匹配。
- 核心产品不一致 → 不匹配。
  例：「芒果果酱」 vs 「芒果」 → 不匹配（果酱 ≠ 水果）。
  例：「芒果果酱」 vs 「草莓果酱」 → 不匹配（核心食材不同）。
  例：「特级雪燕」 vs 「特级虾皮（散称）」 → 不匹配（燕窝类 ≠ 海鲜）。

查询商品：{query_name}
匹配标准品：{matched_name}

只返回一个 JSON 对象，不要任何其他文字：
{{"is_match": true 或 false, "reason": "一句话理由"}}"""

    try:
        data = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 120,
        }).encode("utf-8")
        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=data,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        resp_data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, Exception) as e:
        logger.warning(f"AI 匹配复核请求失败: {e}")
        return None, ""

    try:
        content = resp_data["choices"][0]["message"]["content"].strip()
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        result = json.loads(content)
    except (KeyError, json.JSONDecodeError, IndexError) as e:
        logger.warning(f"AI 匹配复核响应解析失败: {e}")
        return None, ""

    return _parse_bool(result.get("is_match")), str(result.get("reason", "")).strip()


def _check_one_batch(batch: List[Tuple[str, str]], key: str, model: str, timeout: int) -> List[Tuple[Optional[bool], str]]:
    """核对一批 pairs，返回与 batch 等长的 [(is_match, reason), ...]，失败位置为 (None, '')。"""
    out = [(None, "") for _ in batch]
    prompt_lines = []
    for j, (q, m) in enumerate(batch, 1):
        prompt_lines.append(f"{j}. 查询：{q} → 匹配：{m}")
    prompt = f"""你是商品对品复核专家。下面有 {len(batch)} 组「查询商品」和「匹配标准品」，请逐组判断它们是否指「同一个核心产品」。

判断标准：
- 核心产品必须「完全一样」才算匹配（不只是同类）。规格/包装/品牌/容量不同但核心产品一致 → 匹配。
- 「芒果果酱」vs「芒果果酱」→ 匹配；「芒果果酱」vs「蓝莓果酱」→ 不匹配（同类但核心食材不同）；「芒果果酱」vs「果茸」→ 不匹配（形态/工艺不同）；「芒果果酱」vs「芒果」→ 不匹配。

{chr(10).join(prompt_lines)}

只返回一个 JSON 数组，长度必须等于 {len(batch)}，每个元素按顺序对应上面每一组，不要任何其他文字：
[{{"is_match": true 或 false, "reason": "一句话理由"}}, ...]"""
    try:
        data = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 50 * len(batch) + 100,
        }).encode("utf-8")
        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=data,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        resp_data = json.loads(resp.read().decode("utf-8"))
        content = resp_data["choices"][0]["message"]["content"].strip()
        arr_match = re.search(r'\[[\s\S]*\]', content, re.DOTALL)
        if arr_match:
            content = arr_match.group(0)
        arr = json.loads(content)
        if isinstance(arr, list):
            for j, item in enumerate(arr):
                if j >= len(batch):
                    break
                if not isinstance(item, dict):
                    continue
                out[j] = (_parse_bool(item.get("is_match")), str(item.get("reason", "")).strip())
    except Exception as e:
        logger.warning(f"AI 批量复核失败: {e}")
    return out


def check_matches_batch(
    pairs: List[Tuple[str, str]],
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    timeout: int = 60,
    batch_size: Optional[int] = None,
    max_workers: Optional[int] = None,
) -> List[Tuple[Optional[bool], str]]:
    """批量 AI 复核：分批 + 并发，一次请求核对多条。

    Returns:
        [(is_match, reason), ...]，与 pairs 一一对应；复核失败的位置 is_match=None
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    key = api_key or DEEPSEEK_API_KEY
    if not key:
        return [(None, "") for _ in pairs]
    if not pairs:
        return []

    batch_size = batch_size or AI_MATCH_CHECK_BATCH_SIZE
    max_workers = max_workers or AI_MATCH_CHECK_MAX_WORKERS

    batches = [pairs[i:i + batch_size] for i in range(0, len(pairs), batch_size)]
    results: List[Optional[Tuple[Optional[bool], str]]] = [None] * len(pairs)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        offset = 0
        for batch in batches:
            fut = ex.submit(_check_one_batch, batch, key, model, timeout)
            futures[fut] = offset
            offset += len(batch)
        total_batches = len(batches)
        done = 0
        for fut in as_completed(futures):
            off = futures[fut]
            try:
                batch_results = fut.result()
            except Exception:
                batch_results = [(None, "") for _ in range(max(0, (len(batches) and 0) or 0))]
            for j, res in enumerate(batch_results):
                idx = off + j
                if idx < len(results):
                    results[idx] = res
            done += 1
            if total_batches > 1 and (done % 5 == 0 or done == total_batches):
                logger.info(f"AI 批量复核进度: {done}/{total_batches} 批")

    # 兜底：未被填写的保持 (None, '')
    return [r if r is not None else (None, "") for r in results]
