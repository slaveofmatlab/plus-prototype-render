# -*- coding: utf-8 -*-
"""上传报价单 -> 预处理 -> 匹配 -> 报价 一体化接口"""
import os
import shutil
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from backend.config import UPLOAD_DIR
from backend.state import create_task
from backend.services.file_parser import parse_excel
from backend.services.preprocess_service import detect_special_customer, preprocess_items
from backend.services.matcher_service import get_matcher, match_single_preprocessed
from backend.services.quote_service import lookup_quotes
from backend.services.procurement_service import lookup_procurement

logger = logging.getLogger(__name__)
router = APIRouter()


class PreprocessMatchResponse(BaseModel):
    task_id: str
    filename: str
    customer_name: str
    is_special: bool
    special_label: Optional[str]
    total: int
    results: List[dict]


def _extract_prefer_customers(customer_name: str, is_special: bool, special_label: Optional[str]) -> List[str]:
    """从客户名称提取报价优先匹配关键词。"""
    keywords = []
    if customer_name:
        keywords.append(customer_name.strip())
    if is_special and special_label:
        keywords.append(special_label.strip())
    seen = set()
    out = []
    for k in keywords:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


@router.post("/preprocess_match")
async def preprocess_match(
    file: UploadFile = File(...),
    customer_name: str = Form(default=""),
    top_n: int = Form(default=10),
):
    """
    上传客户报价单 Excel，自动完成：
    1. 解析 Excel 商品名称
    2. 根据 customer_name 检测是否特殊客户
    3. 执行对应预处理
    4. 对预处理后名称做标准产品匹配
    5. 查询历史报价（优先匹配当前客户）与采购数据
    返回完整结果供前端渲染。
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 和 .xls 格式的 Excel 文件")

    task = create_task()
    save_path = os.path.join(UPLOAD_DIR, f"{task.task_id}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    task.file_path = save_path

    try:
        items, columns, sheets_info = parse_excel(save_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件解析失败: {str(e)}")

    if not items:
        raise HTTPException(status_code=400, detail="未从文件中识别到有效商品名称，请检查表头或选择正确的列")

    task.items = items

    special_info = detect_special_customer(customer_name)
    is_special = special_info is not None
    special_label = special_info.get("label") if special_info else None

    matcher = get_matcher()
    try:
        preprocessed = preprocess_items(items, is_special=is_special, brands_sorted=matcher.brands)
    except Exception as e:
        logger.exception("预处理失败")
        raise HTTPException(status_code=500, detail=f"预处理失败: {str(e)}")

    prefer_customers = _extract_prefer_customers(customer_name, is_special, special_label)
    results = []
    product_codes = []
    for item in preprocessed:
        raw_name = item.get("raw_name", "")
        preprocessed_name = item.get("preprocessed_name", "")
        method = item.get("preprocess_method", "")

        if not preprocessed_name:
            results.append({
                "index": item.get("index"),
                "raw_name": raw_name,
                "preprocessed_name": "",
                "preprocess_method": method,
                "top_match": None,
                "alternatives": [],
                "quote": None,
            })
            continue

        match_res = match_single_preprocessed(preprocessed_name, top_n=top_n)
        top = match_res.get("top_match")
        results.append({
            "index": item.get("index"),
            "raw_name": raw_name,
            "preprocessed_name": preprocessed_name,
            "preprocess_method": method,
            "top_match": top,
            "alternatives": match_res.get("alternatives", []),
            "quote": None,
        })
        if top and top.get("product_code"):
            product_codes.append(top["product_code"])

    quotes = {}
    procs = {}
    if product_codes:
        try:
            quotes = lookup_quotes(product_codes, prefer_customers=prefer_customers)
        except Exception as e:
            logger.exception("报价查询失败")
        try:
            procs = lookup_procurement(product_codes)
        except Exception as e:
            logger.exception("采购数据查询失败")

    for r in results:
        top = r.get("top_match")
        if top and top.get("product_code"):
            r["quote"] = quotes.get(top["product_code"])
            r["procurement"] = procs.get(top["product_code"])

    task.match_results = results

    return {
        "task_id": task.task_id,
        "filename": file.filename,
        "customer_name": customer_name,
        "is_special": is_special,
        "special_label": special_label,
        "total": len(results),
        "results": results,
    }
