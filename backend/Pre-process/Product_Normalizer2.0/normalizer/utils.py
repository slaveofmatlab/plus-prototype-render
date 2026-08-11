# -*- coding: utf-8 -*-
"""
工具函数模块 - 提供通用的辅助函数
"""

import re
import logging
from typing import List, Dict, Any, Optional
from . import config


def setup_logger(name: str, level: str = None) -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    if level is None:
        level = config.LOG_LEVEL
    
    logger.setLevel(getattr(logging, level))
    
    # 避免重复添加handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(getattr(logging, level))
        formatter = logging.Formatter(config.LOG_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def fullwidth_to_halfwidth(text: str) -> str:
    """
    全角字符转半角字符
    
    Args:
        text: 输入文本
        
    Returns:
        str: 转换后的文本
    """
    result = []
    for char in text:
        if char in config.FULLWIDTH_TO_HALFWIDTH:
            result.append(config.FULLWIDTH_TO_HALFWIDTH[char])
        else:
            # 处理其他全角字符 (通用转换)
            code = ord(char)
            if 0xFF01 <= code <= 0xFF5E:
                result.append(chr(code - 0xFEE0))
            elif code == 0x3000:  # 全角空格
                result.append(' ')
            else:
                result.append(char)
    return ''.join(result)


def normalize_multiply_chars(text: str) -> str:
    """
    统一乘号字符为 *
    
    Args:
        text: 输入文本
        
    Returns:
        str: 统一后的文本
    """
    for char in config.MULTIPLY_CHARS:
        text = text.replace(char, '*')
    return text


def remove_special_chars(text: str) -> str:
    """
    删除连续特殊符号
    
    Args:
        text: 输入文本
        
    Returns:
        str: 清理后的文本
    """
    # 保留中文、字母、数字、空格和常用符号
    text = re.sub(r'[^\w\s\u4e00-\u9fff\*\+\-\/\.\(\)\[\]\{\}]+', ' ', text)
    return text


def normalize_spaces(text: str) -> str:
    """
    多个空格合并为一个，并去除首尾空格
    
    Args:
        text: 输入文本
        
    Returns:
        str: 规范化后的文本
    """
    # 多个空格合并为一个
    text = re.sub(r'\s+', ' ', text)
    # 去除首尾空格
    return text.strip()


def convert_weight_to_gram(value: float, multiplier: float) -> str:
    """
    将重量转换为克
    
    Args:
        value: 数值
        multiplier: 转换系数
        
    Returns:
        str: 转换后的字符串 (如: 6000g)
    """
    result = value * multiplier
    # 如果是整数，不显示小数点
    if result == int(result):
        return f"{int(result)}g"
    else:
        return f"{result:.2f}g"


def convert_volume_to_ml(value: float, multiplier: float) -> str:
    """
    将体积转换为毫升
    
    Args:
        value: 数值
        multiplier: 转换系数
        
    Returns:
        str: 转换后的字符串 (如: 500mL)
    """
    result = value * multiplier
    # 如果是整数，不显示小数点
    if result == int(result):
        return f"{int(result)}mL"
    else:
        return f"{result:.2f}mL"


def extract_bracket_content(text: str) -> List[str]:
    """
    提取括号内的内容
    
    Args:
        text: 输入文本
        
    Returns:
        List[str]: 括号内容列表
    """
    pattern = r'[\(（\[]([^)）\]]*)[\)）\]]'
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches if m.strip()]


def remove_brackets(text: str) -> str:
    """
    删除括号但保留内容
    
    当括号后紧跟数字/字母时，插入空格分隔，避免内容合并。
    例如: (2023)750ml -> 2023 750ml
    
    Args:
        text: 输入文本
        
    Returns:
        str: 删除括号后的文本
    """
    # 括号后紧跟数字或字母 → 加空格分隔
    text = re.sub(r'[\(（\[]([^)）\]]*)[\)）\]](?=\d|[a-zA-Z])', r' \1 ', text)
    # 其他情况正常去除括号
    text = re.sub(r'[\(（\[]([^)）\]]*)[\)）\]]', r' \1 ', text)
    return text


def is_number(s: str) -> bool:
    """
    判断字符串是否为数字
    
    Args:
        s: 输入字符串
        
    Returns:
        bool: 是否为数字
    """
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def format_number(value: float) -> str:
    """
    格式化数字显示 (整数不显示小数点)
    
    Args:
        value: 数值
        
    Returns:
        str: 格式化后的字符串
    """
    if value == int(value):
        return str(int(value))
    else:
        return str(value)


def load_brands_from_dataframe(df) -> List[str]:
    """
    从DataFrame中加载品牌列表
    
    Args:
        df: pandas DataFrame
        
    Returns:
        List[str]: 品牌列表
    """
    brands = []
    if '品牌' in df.columns:
        brands = df['品牌'].dropna().unique().tolist()
        # 过滤空值
        brands = [b.strip() for b in brands if isinstance(b, str) and b.strip() and b.strip() not in ('无', 'nan', 'None')]
    return brands


def log_step(logger: logging.Logger, step_name: str, input_text: str, output_text: str):
    """
    记录标准化步骤的日志
    
    Args:
        logger: 日志记录器
        step_name: 步骤名称
        input_text: 输入文本
        output_text: 输出文本
    """
    logger.info(f"[{step_name}] 输入: '{input_text}' -> 输出: '{output_text}'")
