"""商品匹配 + 备选切换接口"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.state import get_task, update_confirmed
from backend.services.matcher_service import match_batch, match_single
from backend.services.quote_service import lookup_quotes
from backend.services.procurement_service import lookup_procurement

router = APIRouter()


class MatchRequest(BaseModel):
    task_id: str
    top_n: int = 10


class SelectAlternativeRequest(BaseModel):
    task_id: str
    item_index: int
    selected_code: str


@router.post("/match")
async def do_match(req: MatchRequest):
    """执行商品匹配"""
    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在，请重新上传文件")

    results = match_batch(task.items, top_n=req.top_n)
    task.match_results = results

    # 默认确认第一条匹配
    for r in results:
        if r["top_match"]:
            update_confirmed(req.task_id, r["index"], r["top_match"])

    # 自动查询报价
    codes = []
    for r in results:
        if r["top_match"]:
            codes.append(r["top_match"]["product_code"])
    if codes:
        quotes = lookup_quotes(codes)
        for code, quote in quotes.items():
            task.quote_info[code] = quote  # 存储所有结果，包括 None（无报价）

        # 查询采购数据
        procs = lookup_procurement(codes)
        for code, proc in procs.items():
            task.quote_info[code + "_proc"] = proc  # 用 _proc 后缀区分

    all_info = dict(task.quote_info)
    # 分离报价和采购数据
    quote_data = {k: v for k, v in all_info.items() if not k.endswith("_proc")}
    proc_data = {k.replace("_proc", ""): v for k, v in all_info.items() if k.endswith("_proc")}

    return {"task_id": req.task_id, "results": results, "total": len(results), "quotes": quote_data, "procurements": proc_data}


@router.post("/select_alternative")
async def select_alternative(req: SelectAlternativeRequest):
    """用户选择备选匹配"""
    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 在匹配结果中找到对应条目
    match_result = None
    for r in task.match_results:
        if r["index"] == req.item_index:
            match_result = r
            break

    if not match_result:
        raise HTTPException(status_code=404, detail="未找到该商品的匹配结果")

    # 查找选中的备选
    selected = None
    # 先检查是否是当前的 top_match
    if match_result["top_match"] and match_result["top_match"]["product_code"] == req.selected_code:
        selected = match_result["top_match"]
    else:
        for alt in match_result["alternatives"]:
            if alt["product_code"] == req.selected_code:
                selected = alt
                break

    if not selected:
        raise HTTPException(status_code=404, detail="未找到选中的备选匹配")

    # 更新确认
    update_confirmed(req.task_id, req.item_index, selected)

    # 查询新报价
    quote = lookup_quotes([req.selected_code])
    if quote.get(req.selected_code):
        task.quote_info[req.selected_code] = quote[req.selected_code]

    # 查询新采购数据
    proc = lookup_procurement([req.selected_code])
    if proc.get(req.selected_code):
        task.quote_info[req.selected_code + "_proc"] = proc[req.selected_code]

    return {
        "success": True,
        "confirmed": selected,
        "quote_info": quote.get(req.selected_code),
        "procurement_info": proc.get(req.selected_code),
    }
