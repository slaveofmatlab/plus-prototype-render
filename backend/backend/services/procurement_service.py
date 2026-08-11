"""采购数据查询服务：根据产品编码查找采购价格"""
import os
import pandas as pd
import logging
from typing import Dict, List, Optional
from backend.config import PROCUREMENT_DATA_FILE

logger = logging.getLogger(__name__)

_proc_df = None
_proc_index = None  # product_code -> list of row indices


def init_procurement_data():
    """启动时加载采购数据并建立索引"""
    global _proc_df, _proc_index
    proc_path = PROCUREMENT_DATA_FILE
    logger.info(f"加载采购数据: {proc_path}")
    _proc_df = pd.read_excel(proc_path, engine="openpyxl")
    _proc_df["商品代码"] = _proc_df["商品代码"].astype(str).str.strip()

    # 建立编码索引
    _proc_index = {}
    for idx, row in _proc_df.iterrows():
        code = row["商品代码"]
        if code not in _proc_index:
            _proc_index[code] = []
        _proc_index[code].append(idx)

    logger.info(f"采购数据加载完成: {len(_proc_df)} 条记录, {len(_proc_index)} 个产品编码")


def lookup_procurement(product_codes: List[str]) -> Dict[str, Optional[dict]]:
    """
    根据产品编码列表批量查询采购价格信息。
    返回: {product_code: proc_info_dict_or_None}
    """
    if _proc_df is None or _proc_index is None:
        init_procurement_data()

    results = {}
    for code in product_codes:
        code = str(code).strip()
        if code in _proc_index:
            rows = _proc_df.iloc[_proc_index[code]]
            # 取最新一条（按创建时间排序）
            if "创建时间" in rows.columns:
                rows = rows.sort_values("创建时间", ascending=False)
            latest = rows.iloc[0]
            results[code] = {
                "product_name": str(latest.get("商品名称", "")),
                "procurement_price": _safe_float(latest.get("含税协议价(采购单位)")),
                "supplier_name": str(latest.get("供应商名称", "")),
                "start_time": str(latest.get("开始时间", "")),
                "end_time": str(latest.get("终止时间", "")),
                "records_count": len(rows),
            }
        else:
            results[code] = None
    return results


def _safe_float(val) -> Optional[float]:
    if pd.isna(val):
        return None
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return None
