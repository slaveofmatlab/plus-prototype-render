# -*- coding: utf-8 -*-
"""AI 辅助列检测：当规则无法识别商品名称列时，调用 DeepSeek 兜底。"""
import os
import json
import logging
import re
from typing import Optional, Tuple

import pandas as pd
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def _rows_to_text(raw: pd.DataFrame, max_rows: int = 25, max_cell_len: int = 100) -> str:
    """将 DataFrame 前 N 行转为文本表格，供 LLM 分析。"""
    limit = min(max_rows, len(raw))
    lines = []
    for i in range(limit):
        cells = []
        for j in range(raw.shape[1]):
            v = raw.iloc[i, j]
            if pd.isna(v):
                cells.append("")
            else:
                s = str(v).replace("\n", " ").replace("|", "/")
                cells.append(s[:max_cell_len])
        lines.append(f"Row{i}: " + " | ".join(cells))
    return "\n".join(lines)


def detect_column_with_ai(
    file_path: str,
    sheet_name: str,
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    timeout: int = 20,
) -> Tuple[Optional[int], Optional[str]]:
    """
    使用 LLM 识别 Excel sheet 中的表头行和商品名称列。

    Returns:
        (header_row, product_column_name) 或 (None, None) 表示识别失败。
    """
    key = api_key or DEEPSEEK_API_KEY
    if not key:
        logger.warning("DEEPSEEK_API_KEY 未设置，跳过 AI 列检测")
        return None, None

    try:
        raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=25)
    except Exception as e:
        logger.error(f"读取 Excel 失败: {e}")
        return None, None

    if raw.empty:
        return None, None

    table_text = _rows_to_text(raw)

    prompt = f"""You are analyzing an Excel spreadsheet to find the product name column.
Each row starts with "RowN:" followed by cells separated by "|".
The first non-empty cell in each column might be the column header.

Below is the data:

{table_text}

Task:
1. Find the HEADER ROW — the row whose cells are column names (not data values).
   - A header row typically has short, descriptive text like "商品名称", "品名", "Description", "Product Name", "goods.name", etc.
   - Data rows have specific product values like "西红柿500g", "Coca Cola 330ml", etc.
   - Sometimes the first few rows are metadata/title rows (like company name, date), skip those.
   - If Row0 cells look like data values (actual products), then Row0 IS the header row.

2. Find the PRODUCT NAME COLUMN — the column that contains product/item/goods names.
   - Look at the HEADER ROW cells for keywords like: 商品名称, 品名, 产品名称, 产品品名, goods.name, Description, Item, Name, 描述, 物料名称, 货品名称, etc.
   - If the header row cells are all "Unnamed: X" or empty, look at the DATA below each column:
     * Product name columns contain descriptive text (like "西红柿500g", "Coca Cola 330ml")
     * Non-product columns contain numbers (quantity, price), codes (F0810...), or short labels
   - The product name column usually has the longest text values.

Reply ONLY with a JSON object (no other text):
{{"header_row": <row number>, "product_column": "<column header text>"}}

If you truly cannot determine either value, use null:
{{"header_row": null, "product_column": null}}"""

    try:
        data = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 200,
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
        logger.error(f"AI 列检测请求失败: {e}")
        return None, None
    except Exception as e:
        logger.error(f"AI 列检测异常: {e}")
        return None, None

    try:
        content = resp_data["choices"][0]["message"]["content"].strip()
        # 提取 JSON（可能被 markdown code block 包裹）
        json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        result = json.loads(content)
    except (KeyError, json.JSONDecodeError, IndexError) as e:
        logger.error(f"AI 列检测响应解析失败: {e}, content={content[:200]}")
        return None, None

    header_row = result.get("header_row")
    product_column = result.get("product_column")

    if header_row is None or product_column is None:
        logger.warning("AI 列检测返回 null，无法识别")
        return None, None

    try:
        header_row = int(header_row)
    except (ValueError, TypeError):
        header_row = None

    return header_row, str(product_column)
