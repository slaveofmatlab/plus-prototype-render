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

# 特殊客户检测规则（与前端原型保持一致）
SPECIAL_CUSTOMER_PATTERNS = [
    {'pattern': re.compile(r'香格里拉|Shangri[-\s]?La', re.IGNORECASE), 'label': '香格里拉'}
]


def detect_special_customer(customer_name: str) -> Optional[Dict[str, str]]:
    """检测是否命中特殊客户预处理规则。"""
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
