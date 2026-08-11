"""报价数据查询服务：根据产品编码查找历史报价"""
import pandas as pd
import logging
from typing import Dict, List, Optional
from backend.config import QUOTE_DATA_FILE

logger = logging.getLogger(__name__)

_quote_df = None
_quote_index = None  # product_code -> list of row indices


def init_quote_data():
    """启动时加载报价数据并建立索引"""
    global _quote_df, _quote_index
    quote_path = QUOTE_DATA_FILE
    logger.info(f"加载报价数据: {quote_path}")
    _quote_df = pd.read_excel(quote_path, engine="openpyxl")
    _quote_df["产品编码"] = _quote_df["产品编码"].astype(str).str.strip()

    # 建立编码索引
    _quote_index = {}
    for idx, row in _quote_df.iterrows():
        code = row["产品编码"]
        if code not in _quote_index:
            _quote_index[code] = []
        _quote_index[code].append(idx)

    logger.info(f"报价数据加载完成: {len(_quote_df)} 条记录, {len(_quote_index)} 个产品编码")


def lookup_quotes(product_codes: List[str], prefer_customers: Optional[List[str]] = None) -> Dict[str, dict]:
    """
    根据产品编码列表批量查询报价信息。
    若提供 prefer_customers，优先匹配客户名称中包含任一关键词的记录，否则取最新记录。
    返回: {product_code: quote_info_dict}
    """
    global _quote_df, _quote_index
    if _quote_df is None or _quote_index is None:
        init_quote_data()

    results = {}
    for code in product_codes:
        code = str(code).strip()
        if code in _quote_index:
            rows = _quote_df.iloc[_quote_index[code]].copy()

            # 优先客户匹配
            if prefer_customers:
                mask = rows["客户名称"].fillna("").apply(
                    lambda x: any(pc in x for pc in prefer_customers if pc)
                )
                preferred = rows[mask]
                if not preferred.empty:
                    rows = preferred

            # 取最新一条（按创建时间排序）
            if "创建时间" in rows.columns:
                rows = rows.sort_values("创建时间", ascending=False)
            latest = rows.iloc[0]
            results[code] = {
                "product_name": str(latest.get("产品名称", "")),
                "quote_name": str(latest.get("报价单名称", "")),
                "unit_price": _safe_float(latest.get("单价")),
                "unit_price_without_tax": _safe_float(latest.get("不含税单价")),
                "purchase_price": _safe_float(latest.get("采购价")),
                "tax_rate": str(latest.get("税率", "")),
                "company": str(latest.get("运营公司", "")),
                "customer_name": str(latest.get("客户名称", "")),
                "project_site": str(latest.get("项目点", "")),
                "supplier_name": str(latest.get("供应商名称", "")),
                "unit": str(latest.get("单位", "")),
                "quote_time": str(latest.get("创建时间", "")),
                "valid_period": str(latest.get("有效期范围", "")),
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
