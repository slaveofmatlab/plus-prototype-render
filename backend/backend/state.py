"""全局状态管理：维护每个 task 的匹配结果和用户选择"""
import uuid
import threading
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
    customer_name: str = ""
    # 后台异步处理进度
    match_status: str = ""          # "" | "processing" | "done" | "error"
    match_progress: int = 0
    match_total: int = 0
    match_error: str = ""
    # 预处理缓存：避免匹配时重复调用 process_single_record
    query_info_map: Dict[int, Dict] = field(default_factory=dict)
    is_special: bool = False
    special_label: Optional[str] = None
    preprocessed_map: Dict[int, str] = field(default_factory=dict)


_tasks: Dict[str, TaskState] = {}
_lock = threading.Lock()


def create_task() -> TaskState:
    task_id = str(uuid.uuid4())
    task = TaskState(task_id=task_id)
    with _lock:
        _tasks[task_id] = task
    return task


def get_task(task_id: str) -> Optional[TaskState]:
    with _lock:
        return _tasks.get(task_id)


def update_confirmed(task_id: str, item_index: int, confirmed_match: Dict):
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task.confirmed[item_index] = confirmed_match


def update_quote_info(task_id: str, product_code: str, quote: Dict):
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task.quote_info[product_code] = quote


def set_match_progress(task_id: str, progress: int, total: int, status: str = "processing"):
    """线程安全更新处理进度"""
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task.match_progress = progress
            task.match_total = total
            task.match_status = status


def set_match_done(task_id: str, results: List[Dict]):
    """标记处理完成"""
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task.match_results = results
            task.match_progress = task.match_total
            task.match_status = "done"


def set_match_error(task_id: str, error: str):
    """标记处理失败"""
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task.match_error = error
            task.match_status = "error"
