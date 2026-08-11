"""全局状态管理：维护每个 task 的匹配结果和用户选择"""
import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class TaskState:
    task_id: str
    items: List[Dict] = field(default_factory=list)
    match_results: List[Dict] = field(default_factory=list)
    confirmed: Dict[int, Dict] = field(default_factory=dict)
    quote_info: Dict[str, Dict] = field(default_factory=dict)
    file_path: str = ""


_tasks: Dict[str, TaskState] = {}


def create_task() -> TaskState:
    task_id = str(uuid.uuid4())
    task = TaskState(task_id=task_id)
    _tasks[task_id] = task
    return task


def get_task(task_id: str) -> Optional[TaskState]:
    return _tasks.get(task_id)


def update_confirmed(task_id: str, item_index: int, confirmed_match: Dict):
    task = _tasks.get(task_id)
    if task:
        task.confirmed[item_index] = confirmed_match


def update_quote_info(task_id: str, product_code: str, quote: Dict):
    task = _tasks.get(task_id)
    if task:
        task.quote_info[product_code] = quote
