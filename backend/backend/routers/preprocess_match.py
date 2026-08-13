# -*- coding: utf-8 -*-
"""上传报价单 -> 预处理 -> 匹配 -> 报价 一体化接口（后台异步 + 进度轮询）"""
import os
import shutil
import threading
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from backend.config import UPLOAD_DIR
from backend.state import create_task, get_task, set_match_progress, set_match_done, set_match_error
from backend.services.file_parser import parse_excel, detect_column_with_fallback, parse_single_sheet
from backend.services.preprocess_service import detect_processing_mode, preprocess_items
from backend.services.matcher_service import get_matcher, match_batch_preprocessed
from backend.services.quote_service import lookup_quotes
from backend.services.procurement_service import lookup_procurement

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_prefer_customers(customer_name: str) -> List[str]:
    """从客户名称提取报价优先匹配关键词。"""
    keywords = []
    if customer_name:
        keywords.append(customer_name.strip())
    seen = set()
    out = []
    for k in keywords:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _parse_with_ai_fallback(file_path: str, sheets_info: dict):
    """规则识别不出商品列时，用 AI 兜底逐 sheet 检测并合并解析结果。"""
    items = []
    columns = []
    for sheet_name in sheets_info.keys():
        try:
            detection = detect_column_with_fallback(file_path, sheet_name, use_ai=True)
        except Exception as e:
            logger.warning(f"sheet「{sheet_name}」AI 列检测异常: {e}")
            continue
        col = detection.get("detected_column")
        if not col:
            continue
        try:
            sheet_items = parse_single_sheet(file_path, sheet_name, col, detection.get("header_row"))
        except Exception as e:
            logger.warning(f"sheet「{sheet_name}」解析失败: {e}")
            continue
        if sheet_items:
            if not columns:
                columns = detection.get("columns", [])
            for it in sheet_items:
                it["index"] = len(items)
                items.append(it)
    return items, columns, sheets_info


def _run_preprocess_match(task_id: str, save_path: str, filename: str, customer_name: str, top_n: int):
    """后台线程：解析 → 预处理 → 匹配 → 查价，通过 state 报告进度。"""
    try:
        task = get_task(task_id)
        if not task:
            return

        # Step 1: 解析 Excel（规则 + AI 兜底）
        logger.info(f"开始解析 Excel: {save_path}")
        items, columns, sheets_info = parse_excel(save_path)
        logger.info(f"Excel 解析完成，识别到 {len(items)} 条商品")
        if not items:
            logger.info("规则未识别出商品列，尝试 AI 兜底检测...")
            items, columns, sheets_info = _parse_with_ai_fallback(save_path, sheets_info)
        if not items:
            set_match_error(task_id, "未从文件中识别到有效商品名称，请检查表头或选择正确的列")
            return
        task.items = items

        # Step 2: 判定模式 + 预处理（纯基于文件内容）
        mode = detect_processing_mode(items)
        is_special = (mode == 'special')
        special_label = '酒店投标格式' if is_special else None
        task.is_special = is_special
        task.special_label = special_label
        logger.info(f"处理模式判定: mode={mode}, is_special={is_special}")

        matcher = get_matcher()
        preprocessed, query_info_map = preprocess_items(items, is_special=is_special, brands_sorted=matcher.brands)
        preprocessed_map = {item["index"]: item.get("preprocessed_name", "") for item in preprocessed}

        # Step 3: 批量匹配（带进度回调，复用 query_info 缓存避免重复归一化）
        total = len(items)
        set_match_progress(task_id, 0, total, "processing")

        def on_progress(current, total_):
            set_match_progress(task_id, current, total_, "processing")

        match_results = match_batch_preprocessed(
            items, preprocessed_map, top_n=top_n,
            query_info_map=query_info_map, progress_callback=on_progress,
        )

        # Step 4: 查价（报价优先匹配当前客户 + 采购价）
        product_codes = []
        for r in match_results:
            if r.get("top_match") and r["top_match"].get("product_code"):
                product_codes.append(r["top_match"]["product_code"])

        quotes = {}
        procs = {}
        if product_codes:
            try:
                quotes = lookup_quotes(product_codes, prefer_customers=_extract_prefer_customers(customer_name))
            except Exception as e:
                logger.exception("报价查询失败")
            try:
                procs = lookup_procurement(product_codes)
            except Exception as e:
                logger.exception("采购数据查询失败")

        # Step 5: 组装结果（保持原返回结构供前端渲染）
        results = []
        for r in match_results:
            idx = r["index"]
            item = preprocessed[idx] if idx < len(preprocessed) else {}
            top = r["top_match"]
            code = top.get("product_code") if top else None
            results.append({
                "index": idx,
                "raw_name": r["raw_name"],
                "preprocessed_name": item.get("preprocessed_name", ""),
                "preprocess_method": item.get("preprocess_method", ""),
                "top_match": top,
                "alternatives": r["alternatives"],
                "quote": quotes.get(code) if code else None,
                "procurement": procs.get(code) if code else None,
            })

        task.match_results = results
        set_match_done(task_id, results)
        logger.info(f"匹配完成: task={task_id}, total={len(results)}")
    except Exception as e:
        logger.exception(f"匹配失败: task={task_id}")
        set_match_error(task_id, str(e))


@router.post("/preprocess_match")
async def preprocess_match(
    file: UploadFile = File(...),
    customer_name: str = Form(default=""),
    top_n: int = Form(default=10),
):
    """
    上传客户报价单 Excel，启动后台异步处理，立即返回 task_id。
    前端轮询 GET /preprocess_match/{task_id}/progress 获取进度与结果。
    """
    logger.info(f"收到上传请求: filename={file.filename}, customer_name={customer_name}")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".xlsx", ".xls"):
        logger.error(f"不支持的文件格式: {ext}")
        raise HTTPException(status_code=400, detail=f"仅支持 .xlsx 和 .xls 格式，收到: {ext}")

    task = create_task()
    save_path = os.path.join(UPLOAD_DIR, f"{task.task_id}{ext}")

    try:
        logger.info(f"保存文件到: {save_path}")
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"文件保存成功: {save_path}")
    except Exception as e:
        logger.exception("文件保存失败")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    task.file_path = save_path

    # 启动后台线程处理，立即返回
    thread = threading.Thread(
        target=_run_preprocess_match,
        args=(task.task_id, save_path, file.filename, customer_name, top_n),
        daemon=True,
    )
    thread.start()

    return {
        "task_id": task.task_id,
        "filename": file.filename,
        "status": "processing",
        "progress": 0,
        "total": 0,
    }


@router.get("/preprocess_match/{task_id}/progress")
async def get_preprocess_match_progress(task_id: str):
    """轮询处理进度。status=done 时附带 results / is_special / special_label。"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在，请重新上传文件")

    resp = {
        "task_id": task_id,
        "status": task.match_status or "processing",
        "progress": task.match_progress,
        "total": task.match_total,
    }

    if task.match_status == "done":
        resp["results"] = task.match_results
        resp["total"] = len(task.match_results)
        resp["is_special"] = task.is_special
        resp["special_label"] = task.special_label
    elif task.match_status == "error":
        resp["error"] = task.match_error

    return resp
