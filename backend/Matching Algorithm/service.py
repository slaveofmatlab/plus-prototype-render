# -*- coding: utf-8 -*-
"""
共享匹配器服务

- 加载预处理后商品库文件
- 维护全局唯一的 ProductMatcher 单例，供各功能模块复用
"""

import os

from matcher import ProductMatcher

# 商品库目录
_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Database')

# 预处理后商品库文件名
_DB_FILENAME = '处理后标品库.xlsx'

# 全局匹配器单例
_matcher = None


def get_db_path() -> str:
    """返回预处理后商品库文件的完整路径"""
    db_path = os.path.join(_DB_DIR, _DB_FILENAME)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"未找到预处理后的商品库文件: {db_path}")
    return db_path


def get_matcher() -> ProductMatcher:
    """获取全局匹配器单例（首次调用时加载商品库）"""
    global _matcher
    if _matcher is None:
        db_path = get_db_path()
        print(f"[INFO] 加载商品库: {db_path}")
        _matcher = ProductMatcher(db_path, log_level='WARNING')
        print(f"[INFO] 商品库加载完成, 共 {len(_matcher.df)} 条记录")
    return _matcher
