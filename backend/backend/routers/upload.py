"""文件上传接口"""
import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from backend.config import UPLOAD_DIR
from backend.state import create_task
from backend.services.file_parser import parse_excel

router = APIRouter()


class UploadRequest(BaseModel):
    """上传后选择 sheet 和 column 的请求"""
    task_id: str
    sheet_name: Optional[str] = None
    column_name: Optional[str] = None


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传 Excel 询价单，返回 sheets 和 columns 信息供用户选择"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 和 .xls 格式的 Excel 文件")

    task = create_task()
    save_path = os.path.join(UPLOAD_DIR, f"{task.task_id}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 解析（自动选择最佳 sheet 和 column）
    try:
        items, columns, sheets_info = parse_excel(save_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件解析失败: {str(e)}")

    # 存储文件路径到 task
    task.file_path = save_path

    # 如果自动识别到了商品，直接返回
    if items:
        task.items = items
        return {
            "task_id": task.task_id,
            "filename": file.filename,
            "items": items,
            "columns": columns,
            "sheets_info": sheets_info,
            "total": len(items),
            "need_selection": False,
        }

    # 需要用户选择 sheet 和 column
    return {
        "task_id": task.task_id,
        "filename": file.filename,
        "items": [],
        "columns": [],
        "sheets_info": sheets_info,
        "total": 0,
        "need_selection": True,
    }


@router.post("/upload/select")
async def select_sheet_column(req: UploadRequest):
    """用户选择 sheet 和 column 后重新解析"""
    from backend.state import get_task

    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if not hasattr(task, "file_path") or not task.file_path:
        raise HTTPException(status_code=400, detail="未找到上传文件")

    try:
        items, columns, sheets_info = parse_excel(
            task.file_path,
            sheet_name=req.sheet_name,
            column_name=req.column_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

    if not items:
        raise HTTPException(status_code=400, detail="所选列中没有有效的商品数据")

    task.items = items
    return {
        "task_id": req.task_id,
        "items": items,
        "columns": columns,
        "sheets_info": sheets_info,
        "total": len(items),
    }
