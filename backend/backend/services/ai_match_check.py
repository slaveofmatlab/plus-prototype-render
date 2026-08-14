# -*- coding: utf-8 -*-
"""AI 匹配复核：规则算法匹配出候选后，AI 兜底判断核心产品是否一致。

用于拦截「字面相似但核心商品完全不同」的错配，例如：
  - 「特级雪燕」误匹配到「特级虾皮（散称）」
  - 「芒果果酱」误匹配到「芒果」
"""
import os
import json
import logging
import re
from typing import Optional, Tuple

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 是否启用 AI 匹配复核（实验阶段默认关闭；需要时通过环境变量开启）
AI_MATCH_CHECK_ENABLED = os.environ.get("AI_MATCH_CHECK_ENABLED", "0") == "1"

# 仅对置信度低于该阈值的匹配做 AI 复核（高置信度大概率正确，跳过以省调用）
AI_MATCH_CHECK_MIN_CONF = float(os.environ.get("AI_MATCH_CHECK_MIN_CONF", "0.7"))


def check_match_semantics(
    query_name: str,
    matched_name: str,
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    timeout: int = 15,
) -> Tuple[Optional[bool], str]:
    """
    AI 兜底复核：判断查询商品与匹配标准品是否为同一核心商品。

    Returns:
        (is_match, reason)
        - is_match=True / False：AI 明确判断是否同一核心商品
        - is_match=None：复核失败（无 key / 请求异常 / 解析失败），调用方应回退规则结果
    """
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
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        resp_body = resp.read().decode("utf-8")
        resp_data = json.loads(resp_body)
    except urllib.error.URLError as e:
        logger.warning(f"AI 匹配复核请求失败: {e}")
        return None, ""
    except Exception as e:
        logger.warning(f"AI 匹配复核异常: {e}")
        return None, ""

    try:
        content = resp_data["choices"][0]["message"]["content"].strip()
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        result = json.loads(content)
    except (KeyError, json.JSONDecodeError, IndexError) as e:
        logger.warning(f"AI 匹配复核响应解析失败: {e}, content={content[:200]}")
        return None, ""

    is_match = result.get("is_match")
    reason = str(result.get("reason", "")).strip()
    if isinstance(is_match, bool):
        return is_match, reason
    # 兼容字符串 "true"/"false"
    if isinstance(is_match, str):
        if is_match.lower() == "true":
            return True, reason
        if is_match.lower() == "false":
            return False, reason
    return None, reason
