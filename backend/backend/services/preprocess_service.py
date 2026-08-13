# -*- coding: utf-8 -*-
"""预处理服务：根据客户类型选择特殊或普通预处理。"""
import os
import sys
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 引入特殊订单预处理
XGL_DIR = os.path.join(PROJECT_ROOT, 'Special Orders Process', 'XGLL')
if XGL_DIR not in sys.path:
    sys.path.insert(0, XGL_DIR)

# 引入普通商品标准化
NORMALIZER_DIR = os.path.join(PROJECT_ROOT, 'Pre-process', 'Product_Normalizer2.0')
if NORMALIZER_DIR not in sys.path:
    sys.path.insert(0, NORMALIZER_DIR)

from process_orders_xgll import process_description as _special_preprocess
from normalizer.main import process_single_record as _normal_process_single
from normalizer.main import _init_instances

# 酒店投标格式检测：英文大写类目前缀 + 中英混合 + 末尾中文括号
_SPECIAL_FORMAT_RE = re.compile(r'^[A-Z]{2,10}\s')
_HAS_CHINESE_RE = re.compile(r'[一-鿿]')


def _last_bracket_has_chinese(name: str) -> bool:
    """检查字符串中最后一个括号对是否包含中文（处理嵌套括号）。"""
    last_open = name.rfind('(')
    if last_open == -1:
        return False
    rest = name[last_open + 1:]
    close = rest.rfind(')')
    if close == -1:
        return False
    content = rest[:close]
    return bool(_HAS_CHINESE_RE.search(content))


def detect_processing_mode(items: List[Dict[str, Any]], sample_size: int = 10) -> str:
    """
    采样前 N 条产品名，自动判断处理模式。
    规则：英文大写类目前缀 + 含中文 + 末尾括号含中文 → 酒店投标格式 → 'special'
    不依赖客户名称，纯基于文件内容判断（覆盖香格里拉、乐高乐园等各类客户）。
    """
    if not items:
        return 'normal'

    sample = items[:sample_size]
    special_count = 0
    for item in sample:
        name = str(item.get('raw_name', '')).strip()
        if not name:
            continue
        if (_SPECIAL_FORMAT_RE.match(name) and
                _HAS_CHINESE_RE.search(name) and
                _last_bracket_has_chinese(name)):
            special_count += 1

    threshold = max(1, len(sample) * 0.5)
    return 'special' if special_count >= threshold else 'normal'


# 特殊客户检测规则（基于客户名称）
# 注意：已废弃。特殊/普通预处理判定统一改用 detect_processing_mode（基于文件内容），
# 此处仅保留用于历史兼容/潜在兜底，当前无调用方。
SPECIAL_CUSTOMER_PATTERNS = [
    {'pattern': re.compile(r'香格里拉|Shangri[-\s]?La', re.IGNORECASE), 'label': '香格里拉'}
]


def detect_special_customer(customer_name: str) -> Optional[Dict[str, str]]:
    """检测是否命中特殊客户预处理规则（已废弃，请改用 detect_processing_mode）。"""
    if not customer_name:
        return None
    for rule in SPECIAL_CUSTOMER_PATTERNS:
        if rule['pattern'].search(customer_name):
            return {'name': customer_name, 'label': rule['label']}
    return None


def preprocess_items(items: List[Dict[str, Any]], is_special: bool, brands_sorted: List[str]) -> List[Dict[str, Any]]:
    """
    批量预处理商品名称。
    items: [{index, raw_name, ...}, ...]
    is_special: 是否使用特殊客户预处理
    brands_sorted: 按长度降序排列的品牌列表
    """
    if not is_special:
        # 确保普通标准化器已初始化
        _init_instances(brands_sorted)

    results = []
    for item in items:
        raw = str(item.get('raw_name') or '').strip()
        if not raw:
            results.append({**item, 'preprocessed_name': '', 'preprocess_method': 'special' if is_special else 'normal'})
            continue

        if is_special:
            preprocessed = _special_preprocess(raw)
            method = 'special'
        else:
            info = _normal_process_single(raw, brands_sorted=brands_sorted)
            preprocessed = info.get('normalized_name') or raw
            method = 'normal'

        results.append({**item, 'preprocessed_name': preprocessed, 'preprocess_method': method})

    return results
