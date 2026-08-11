"""报价查询接口"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from backend.state import get_task
from backend.services.quote_service import lookup_quotes

router = APIRouter()


class QuoteLookupRequest(BaseModel):
    task_id: str
    product_codes: List[str]


@router.post("/quote_lookup")
async def quote_lookup(req: QuoteLookupRequest):
    """根据产品编码查询历史报价"""
    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    quotes = lookup_quotes(req.product_codes)

    # 更新 task 中的报价信息
    for code, quote in quotes.items():
        task.quote_info[code] = quote

    return {"quotes": quotes}
