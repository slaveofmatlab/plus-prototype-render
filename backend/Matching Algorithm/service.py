# -*- coding: utf-8 -*-
"""
共享匹配器服务

- 自动定位最新的预处理后商品库
- 维护全局唯一的 ProductMatcher 单例，供各功能模块复用
"""

import os
import glob

from matcher import ProductMatcher

# 商品库目录
_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Database')

# 全局匹配器单例
_matcher = None


def find_latest_db() -> str:
    """自动查找最新的预处理后商品库文件"""
    pattern = os.path.join(_DB_DIR, 'RSM_723_normalized_*.xlsx')
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"未找到预处理后的商品库文件: {pattern}")
    # 按修改时间排序取最新
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def get_matcher() -> ProductMatcher:
    """获取全局匹配器单例（首次调用时加载商品库）"""
    global _matcher
    if _matcher is None:
        db_path = find_latest_db()
        print(f"[INFO] 加载商品库: {db_path}")
        _matcher = ProductMatcher(db_path, log_level='WARNING')
        print(f"[INFO] 商品库加载完成, 共 {len(_matcher.df)} 条记录")
    return _matcher
