# -*- coding: utf-8 -*-
"""
主程序模块 - 商品名称标准化工具的入口

提供以下API:
1. normalize_query(query, brand=None) -> dict: 标准化单个query
2. process_excel(input_file, output_file=None) -> DataFrame: 批量处理Excel文件
3. get_normalizer() / get_tokenizer(): 获取单例实例
"""

import os
import sys
import re
import json
import logging
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime

import pandas as pd

from .normalize import ProductNormalizer
from .tokenizer import ProductTokenizer, tokens_to_json
from . import utils
from . import config


# ============================================
# 全局单例 (延迟初始化)
# ============================================
_normalizer_instance = None
_tokenizer_instance = None
_brands_cache = None


def _init_instances(brands: List[str] = None, log_level: str = None):
    """
    初始化全局单例
    
    Args:
        brands: 品牌列表
        log_level: 日志级别
    """
    global _normalizer_instance, _tokenizer_instance, _brands_cache
    
    # 如果品牌列表没变化，不重新初始化
    if _normalizer_instance is not None and _brands_cache == brands:
        return
    
    _normalizer_instance = ProductNormalizer(brands=brands, log_level=log_level)
    _tokenizer_instance = ProductTokenizer(brands=brands, log_level=log_level)
    _brands_cache = brands.copy() if brands else []


def get_normalizer(brands: List[str] = None, log_level: str = None) -> ProductNormalizer:
    """
    获取标准化器实例
    
    Args:
        brands: 品牌列表
        log_level: 日志级别
        
    Returns:
        ProductNormalizer: 标准化器实例
    """
    _init_instances(brands, log_level)
    return _normalizer_instance


def get_tokenizer(brands: List[str] = None, log_level: str = None) -> ProductTokenizer:
    """
    获取分词器实例
    
    Args:
        brands: 品牌列表
        log_level: 日志级别
        
    Returns:
        ProductTokenizer: 分词器实例
    """
    _init_instances(brands, log_level)
    return _tokenizer_instance


# ============================================
# 核心API函数
# ============================================

def process_single_record(product_name: str, brand: str = None,
                         brands_sorted: List[str] = None,
                         brand_automaton=None) -> Dict[str, Any]:
    """
    处理单条商品名称 - 完整预处理流程的核心函数
    
    流程: 品牌检测 → 标准化 → 分词 → 规格分离
    
    Args:
        product_name: 原始商品名称
        brand: 已检测的品牌名 (可选，传入则跳过品牌检测)
        brands_sorted: 按长度降序的品牌列表 (用于品牌检测)
        brand_automaton: Aho-Corasick自动机 (可选，批量处理时传入提升性能)
        
    Returns:
        Dict[str, Any]: 包含以下字段:
            - original: 原始名称
            - normalized_name: 标准化后的名称
            - tokens: 全量token列表 (含品牌+规格)
            - tokens_json: JSON格式的token字符串
            - detected_brand: 检测到的品牌
            - core_name: 去掉品牌和规格的核心产品名
            - raw_spec: 原始规格信息
            - normalized_spec: 标准化后的规格信息
            - core_tokens: 不含品牌和规格的tokens
            - core_tokens_json: JSON格式的core_tokens字符串
            
    Example:
        >>> result = process_single_record("味达美牌味极鲜酱油1L/瓶")
        >>> print(result['detected_brand'])
        '味达美'
        >>> print(result['core_name'])
        '味极鲜酱油'
        >>> print(result['core_tokens'])
        ['味极鲜', '酱油']
    """
    # Step A: 品牌检测（若未传入brand）
    detected_brand = brand
    if not detected_brand and brands_sorted:
        detected_brand = _detect_brand(product_name, brands_sorted, brand_automaton)
    
    # 过滤无效品牌值
    if detected_brand and detected_brand.strip() in ('无', 'nan', 'None', ''):
        detected_brand = None
    
    # Step B: 标准化（去品牌、统一单位、清洗文本）
    normalized_name = _normalizer_instance.normalize(product_name, brand=detected_brand)
    
    # Step C: 分词
    tokens = _tokenizer_instance.tokenize(normalized_name)
    
    # Step D: 品牌插入tokens开头
    if detected_brand:
        tokens.insert(0, detected_brand)
    
    # Step E: 规格分离
    norm_spec = _extract_spec_from_normalized(normalized_name)
    core_name = _remove_spec_from_normalized(normalized_name)
    raw_spec = _extract_raw_spec(product_name, detected_brand)
    core_tks = _filter_core_tokens(tokens, detected_brand)
    
    # Step F: 属性提取（只识别不摘除，从原始名称中匹配）
    attributes = _extract_attributes(product_name)
    
    return {
        'original': product_name,
        'normalized_name': normalized_name,
        'tokens': tokens,
        'tokens_json': tokens_to_json(tokens),
        'detected_brand': detected_brand or '',
        'core_name': core_name,
        'raw_spec': raw_spec,
        'normalized_spec': norm_spec,
        'core_tokens': core_tks,
        'core_tokens_json': json.dumps(core_tks, ensure_ascii=False),
        'attributes': attributes,
        'attributes_json': json.dumps(attributes, ensure_ascii=False),
    }


def normalize_query(query: str, brand: str = None, 
                   brands: List[str] = None) -> Dict[str, Any]:
    """
    标准化单个query - 主要API入口
    
    将商品名称标准化并切分为tokens，返回完整结果。
    内部调用 process_single_record 实现。
    
    Args:
        query: 原始商品名称
        brand: 品牌名称 (可选，用于品牌规范)
        brands: 品牌列表 (可选，用于分词时识别品牌)
        
    Returns:
        Dict[str, Any]: 完整处理结果 (见 process_single_record)
            
    Example:
        >>> result = normalize_query("味达美牌味极鲜酱油1L/瓶")
        >>> print(result['normalized_name'])
        '味极鲜酱油1000mL/瓶'
        >>> print(result['tokens'])
        ['味达美', '味极鲜', '酱油', '1000mL', '瓶']
        >>> print(result['core_tokens'])
        ['味极鲜', '酱油']
    """
    # 过滤无效品牌值
    if brand and brand.strip() in ('无', 'nan', 'None', ''):
        brand = None
    
    # 将单个brand合并到brands列表中，确保分词器能识别品牌
    all_brands = list(brands) if brands else []
    if brand and brand not in all_brands:
        all_brands.append(brand)
    
    _init_instances(all_brands if all_brands else None)
    
    brands_sorted = sorted(set(all_brands), key=len, reverse=True) if all_brands else None
    return process_single_record(query, brand=brand, brands_sorted=brands_sorted)


def normalize_batch(queries: List[str], brands: List[str] = None) -> List[Dict[str, Any]]:
    """
    批量标准化多个query
    
    Args:
        queries: 商品名称列表
        brands: 品牌列表
        
    Returns:
        List[Dict[str, Any]]: 标准化结果列表
    """
    _init_instances(brands)
    
    brands_sorted = sorted(set(brands), key=len, reverse=True) if brands else None
    brand_automaton = _build_brand_automaton(brands_sorted) if brands_sorted else None
    
    results = []
    for query in queries:
        result = process_single_record(
            query, brands_sorted=brands_sorted, brand_automaton=brand_automaton
        )
        results.append(result)
    
    return results


def _build_brand_automaton(brands_sorted: List[str]):
    """
    构建 Aho-Corasick 自动机用于多模品牌匹配
    
    Args:
        brands_sorted: 按长度降序排列的品牌列表
        
    Returns:
        ahocorasick.Automaton 实例，或 None（库未安装时）
    """
    try:
        import ahocorasick
        automaton = ahocorasick.Automaton()
        for brand in brands_sorted:
            if brand:
                automaton.add_word(brand, brand)
        automaton.make_automaton()
        return automaton
    except ImportError:
        return None


def _detect_brand(text: str, brands_sorted: List[str], automaton=None) -> Optional[str]:
    """
    从文本中检测品牌
    
    检测优先级:
    1. "XX牌"模式：提取文本开头"牌"字前的部分作为品牌（最高优先级）
    2. 品牌库匹配：Aho-Corasick 多模匹配 / 线性扫描（最长匹配）
    
    Args:
        text: 商品名称文本
        brands_sorted: 按长度降序排列的品牌列表
        automaton: Aho-Corasick 自动机（可选，传入时使AC算法加速）
        
    Returns:
        检测到的品牌名，未检测到返回 None
    """
    # 策略1（最高优先级）："XX牌"模式 → 提取"牌"前的部分作为品牌
    # 匹配开头的中文/英文/数字/连字符/空格/中间点，直到遇到"牌"字
    pai_match = re.match(r'^([A-Za-z0-9\u4e00-\u9fff\s\-·]{1,10}?)\u724c', text)
    if pai_match:
        candidate = pai_match.group(1).strip()
        if candidate:  # 确保非空
            return candidate
    
    # 策略2：品牌库匹配（回退）
    if automaton is not None:
        # Aho-Corasick: 一次扫描找到所有匹配，取最长
        best = None
        for _, brand in automaton.iter(text):
            if best is None or len(brand) > len(best):
                best = brand
        return best
    else:
        # 回退：线性扫描
        for brand in brands_sorted:
            if brand in text:
                return brand
        return None


def _load_brand_document(brand_path: str) -> List[str]:
    """
    从 Brand_words_document.xlsx 加载品牌列表
    
    Args:
        brand_path: 品牌文档路径
        
    Returns:
        按长度降序排列的品牌列表
    """
    df = pd.read_excel(brand_path)
    brands = []
    for _, row in df.iterrows():
        brand = str(row.iloc[0]).strip()
        if brand and brand not in ('无', 'nan', 'None', ''):
            brands.append(brand)
    brands_sorted = sorted(set(brands), key=len, reverse=True)
    return brands_sorted


# ============================================
# 规格提取与分离辅助函数
# ============================================

# 匹配标准化后的规格信息: 数字*数字+量词(乘法结构), 数字+单位, 数字+中文量词
# 注意: 不匹配孤立裸数字(避免误提取等级/天数等)；但"数字*数字+量词"乘法结构中的
#       首数字属于规格(如 2.5*6袋 表示每袋2.5×6袋)，需作为整体识别。
_SPEC_PATTERN = re.compile(
    r'\d+(?:\.\d+)?\s*[\*xX×]\s*\d+(?:\.\d+)?\s*[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板箱]'
    r'|\d+(?:\.\d+)?(?:g|mL|kg|ml|L|cm|mm|dm|m)'
    r'|\d+(?:\.\d+)?[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板]'
)

# 匹配原始名称中的规格信息: 数字+单位(含中文单位), 数字*数字, 数字/包装
_RAW_SPEC_PATTERN = re.compile(
    r'\d+(?:\.\d+)?\s*(?:kg|KG|g|G|克|千克|ml|mL|ML|L|l|升|毫升|斤|两|磅|盎司|lb|oz|cm|mm)'
    r'|\d+(?:\.\d+)?\s*[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板箱]'
    r'|\d+(?:\.\d+)?\s*[\*xX×]\s*\d+(?:\.\d+)?(?:\s*[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板箱])?'
    r'|\d+(?:\.\d+)?\s*/\s*[包瓶袋盒罐桶箱]'
)

# 包装单位单字（当它们独立作为token时视为规格）
_PACKAGE_UNITS = {'箱', '包', '袋', '盒', '罐', '桶', '瓶', '杯', '碗', '盘', '件', '板'}

# 散称/散装类术语（统一视为规格信息）
_BULK_TERMS = {'散称', '散装', '称重', '散卖', '过秤'}

# 规格乘法符号（如 2.5*6袋 中的连接符）
_MULT_SYMBOLS = {'*', '×', 'x', 'X'}


def _extract_spec_from_normalized(normalized_name: str) -> str:
    """
    从标准化后的名称中提取规格信息
    
    例如: "韩国精选辣椒面1000g/袋" → "1000g/袋"
    """
    if not normalized_name:
        return ''
    # 提取所有数字+单位片段
    parts = _SPEC_PATTERN.findall(normalized_name)
    # 检查散称/散装类术语
    for term in _BULK_TERMS:
        if term in normalized_name:
            parts.append(term)
            break
    # 检查独立的包装单位字 (如 "/袋" 中的 "袋")
    pkg_match = re.findall(r'[/／]\s*([包瓶袋盒罐桶箱件板])', normalized_name)
    for p in pkg_match:
        if p not in parts:
            parts.append(p)
    return ' '.join(parts) if parts else ''


def _remove_spec_from_normalized(normalized_name: str) -> str:
    """
    从标准化后的名称中移除规格信息，保留核心产品名
    
    例如: "韩国精选辣椒面1000g/袋" → "韩国精选辣椒面"
    """
    if not normalized_name:
        return ''
    text = normalized_name
    # 移除数字+单位
    text = _SPEC_PATTERN.sub('', text)
    # 移除包装连接符+单位 (如 "/袋")
    text = re.sub(r'[/／]\s*[包瓶袋盒罐桶箱件板]', '', text)
    # 移除独立包装单位字
    for unit in _PACKAGE_UNITS:
        text = re.sub(rf'(?<![一-鿿]){unit}(?![一-鿿])', '', text)
    # 移除散称/散装类术语
    for term in _BULK_TERMS:
        text = text.replace(term, '')
    # 清理残余符号和空格
    text = re.sub(r'[\*xX×/／\-]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_raw_spec(product_name: str, brand: str = None) -> str:
    """
    从原始产品名称中提取规格信息（标准化前的原始形式）
    
    例如: "户户牌韩国精选辣椒面1kg/袋" → "1kg/袋"
    """
    if not product_name:
        return ''
    text = product_name
    # 先移除品牌部分
    if brand:
        text = text.replace(brand + '牌', '').replace(brand, '')
    # 提取规格片段
    parts = _RAW_SPEC_PATTERN.findall(text)
    # 检查包装单位 (如 "/箱")
    pkg_match = re.findall(r'[/／]\s*([包瓶袋盒罐桶箱件板])', text)
    for p in pkg_match:
        if p not in ' '.join(parts):
            parts.append(p)
    return ' '.join(parts) if parts else ''


def _filter_core_tokens(tokens: List[str], brand: str = None) -> List[str]:
    """
    从tokens中移除品牌和规格相关token，保留核心产品描述
    
    移除规则:
    - 品牌名
    - 数字+单位 (1000g, 500mL)
    - 数字+中文量词 (12袋, 6瓶)
    - 纯数字 + 紧跟包装单位 (如 "1"+"袋" 视为规格数量)
    - 独立包装单位 (箱, 袋)
    - 散称/散装类术语
    
    注意: 不无条件过滤纯数字，避免误删等级(M3+)、天数(150天)等描述性数字
    """
    core = []
    skip_next_pkg = False  # 标记下一个包装单位是否应跳过
    for i, t in enumerate(tokens):
        # 跳过品牌
        if brand and t == brand:
            continue
        # 跳过数字+单位
        if re.match(r'^\d+(?:\.\d+)?(?:g|mL|kg|ml|L|cm|mm|dm|m)$', t, re.IGNORECASE):
            continue
        # 跳过数字+中文量词
        if re.match(r'^\d+(?:\.\d+)?[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板]$', t):
            continue
        # 纯数字: 仅当紧跟包装单位时视为规格数量(如 "1"+"袋")
        if re.match(r'^\d+(?:\.\d+)?$', t):
            # 看下一个token是否是包装单位
            if i + 1 < len(tokens) and tokens[i + 1] in _PACKAGE_UNITS:
                skip_next_pkg = True
                continue  # 跳过这个数字
            # 紧跟乘号 (如 "2.5*6袋" 中的 "2.5") → 规格乘法的一部分，跳过
            if i + 1 < len(tokens) and tokens[i + 1] in _MULT_SYMBOLS:
                continue
            # 紧跟"数字+量词"token (乘号已被分词器删除, 如 "2.5"+"6袋") → 规格乘法首数字
            if i + 1 < len(tokens) and re.match(r'^\d+(?:\.\d+)?[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板箱]$', tokens[i + 1]):
                continue
            # 否则保留（可能是等级/天数等描述性数字）
            core.append(t)
            continue
        # 跳过规格乘号 (如 "2.5*6袋" 中的 "*")
        if t in _MULT_SYMBOLS:
            continue
        # 跳过独立包装单位
        if t in _PACKAGE_UNITS:
            if skip_next_pkg:
                skip_next_pkg = False
            continue
        # 跳过散称/散装类术语
        if t in _BULK_TERMS:
            continue
        core.append(t)
    return core


# ============================================
# 属性提取辅助函数
# ============================================

def _extract_attributes(text: str) -> List[str]:
    """
    从商品名称中提取属性词（只识别不摘除）
    
    采用最长匹配策略，避免"非转基因"被误匹配为"转基因"。
    属性词库已按长度降序排列，逐个扫描文本进行匹配。
    
    Args:
        text: 原始商品名称（或标准化后的名称）
        
    Returns:
        List[str]: 匹配到的属性词列表（按在文本中出现顺序）
        
    Example:
        >>> _extract_attributes("福临门牌非转基因一级大豆油8L*2桶/箱")
        ['非转基因', '一级']
    """
    if not text or not config.DETAIL_WORDS:
        return []
    
    found = []
    # 记录已匹配区间，避免重叠匹配（如"非转基因"匹配后不再匹配其中的"转基因"）
    matched_ranges = []
    
    for word in config.DETAIL_WORDS:  # 已按长度降序
        start = 0
        while True:
            idx = text.find(word, start)
            if idx == -1:
                break
            end = idx + len(word)
            # 检查是否与已匹配区间重叠
            overlap = False
            for (ms, me) in matched_ranges:
                if idx < me and end > ms:
                    overlap = True
                    break
            if not overlap:
                found.append((idx, word))
                matched_ranges.append((idx, end))
            start = idx + 1
    
    # 按出现位置排序
    found.sort(key=lambda x: x[0])
    return [word for _, word in found]


def process_excel(input_file: str, output_file: str = None, 
                  log_level: str = 'INFO') -> pd.DataFrame:
    """
    处理Excel文件，添加标准化后的商品名称和tokens
    
    流程:
    1. 从 Brand_words_document.xlsx 加载品牌列表
    2. 对每个商品名做品牌检测（最长匹配）
    3. 摘除品牌名后标准化 + 分词
    4. 品牌名单独存储，不混入 tokens
    
    Args:
        input_file: 输入Excel文件路径
        output_file: 输出Excel文件路径 (可选，默认在原文件名后添加_normalized)
        log_level: 日志级别
        
    Returns:
        pd.DataFrame: 处理后的DataFrame
    """
    # 设置日志
    logger = utils.setup_logger('MainProcessor', log_level)
    logger.info(f"开始处理文件: {input_file}")
    
    # 读取Excel文件（优先使用 calamine 引擎，速度提升 5-10 倍）
    print("[STATUS] 正在读取Excel文件...", flush=True)
    logger.info("正在读取Excel文件...")
    try:
        try:
            df = pd.read_excel(input_file, engine='calamine')
        except (ImportError, ValueError):
            # calamine 未安装或文件不支持，回退到默认引擎
            df = pd.read_excel(input_file)
        logger.info(f"成功读取 {len(df)} 条记录")
    except Exception as e:
        logger.error(f"读取Excel文件失败: {e}")
        raise
    
    # 检查必要的列 - 支持多种列名
    NAME_COLUMNS = ['商品名称', '标准产品名称', '产品名称', '品名']
    name_column = None
    for col_name in NAME_COLUMNS:
        if col_name in df.columns:
            name_column = col_name
            break
    
    # 如果找不到商品名称列，尝试检测真实表头行（处理第一行是数据的情况）
    if name_column is None:
        print("[STATUS] 正在检测表头行...", flush=True)
        for skip_rows in range(1, 6):
            try:
                try:
                    df_retry = pd.read_excel(input_file, engine='calamine', header=skip_rows)
                except (ImportError, ValueError):
                    df_retry = pd.read_excel(input_file, header=skip_rows)
                for col_name in NAME_COLUMNS:
                    if col_name in df_retry.columns:
                        name_column = col_name
                        df = df_retry
                        logger.info(f"检测到表头在第 {skip_rows + 1} 行")
                        break
                if name_column:
                    break
            except Exception:
                continue
    
    if name_column is None:
        raise ValueError(f"Excel文件缺少商品名称列(商品名称/标准产品名称/产品名称/品名)。可用列: {df.columns.tolist()[:10]}")
    
    logger.info(f"使用列名: '{name_column}' 作为商品名称")

    # 跳过商品名称中含"禁用"的记录（不纳入处理与保存）
    name_series = df[name_column]
    if isinstance(name_series, pd.DataFrame):  # 重复列名时取第一列
        name_series = name_series.iloc[:, 0]
    _skip_mask = name_series.astype(str).str.contains('禁用', na=False, regex=False)
    _skip_count = int(_skip_mask.sum())
    if _skip_count:
        df = df[~_skip_mask].reset_index(drop=True)
        logger.info(f"跳过含'禁用'的记录 {_skip_count} 条，剩余 {len(df)} 条")
        print(f"[STATUS] 跳过含'禁用'的记录 {_skip_count} 条", flush=True)

    # 从 Brand_words_document.xlsx 加载品牌列表
    print("[STATUS] 正在加载品牌词库...", flush=True)
    db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    brand_doc_path = os.path.join(db_dir, 'Spec_words', 'Brand_words_document.xlsx')
    
    if os.path.exists(brand_doc_path):
        brands_sorted = _load_brand_document(brand_doc_path)
        logger.info(f"从品牌文档加载品牌列表: {len(brands_sorted)} 个品牌")
    else:
        brands_sorted = []
        logger.warning(f"品牌文档不存在: {brand_doc_path}，将跳过品牌检测")
    
    # 构建 Aho-Corasick 自动机（性能优化：品牌检测从 O(n×6134) 降为 O(text_len)）
    brand_automaton = _build_brand_automaton(brands_sorted) if brands_sorted else None
    
    # 初始化标准化器和分词器（传入品牌列表用于分词识别）
    # 批量处理时使用 WARNING 级别，避免每条记录输出6步INFO日志
    print("[STATUS] 正在初始化标准化引擎...", flush=True)
    _init_instances(brands_sorted, 'WARNING')
    
    # 处理每一行（调用 process_single_record 核心函数）
    print(f"[STATUS] 开始处理 0/{len(df)}", flush=True)
    logger.info("开始处理商品名称...")
    normalized_names = []
    tokens_list = []
    detected_brands = []
    core_names = []
    raw_specs = []
    normalized_specs = []
    core_tokens_list = []
    attributes_list = []
    
    total = len(df)
    for idx, row in df.iterrows():
        product_name = str(row.get(name_column, ''))
        
        # 调用单条处理核心函数
        result = process_single_record(
            product_name,
            brands_sorted=brands_sorted,
            brand_automaton=brand_automaton
        )
        
        normalized_names.append(result['normalized_name'])
        tokens_list.append(result['tokens'])
        detected_brands.append(result['detected_brand'])
        core_names.append(result['core_name'])
        raw_specs.append(result['raw_spec'])
        normalized_specs.append(result['normalized_spec'])
        core_tokens_list.append(result['core_tokens'])
        attributes_list.append(result['attributes'])
        
        # 输出进度到 stdout（供 Web 前端实时解析）
        current = idx + 1
        if current % 100 == 0 or current == total:
            print(f"[PROGRESS] {current}/{total}", flush=True)
        
        if current % 1000 == 0:
            logger.info(f"已处理 {current}/{total} 条记录")
    
    # 添加新列
    logger.info("添加新列到DataFrame...")
    
    # 找到商品名称列的位置
    name_col_idx = df.columns.get_loc(name_column)
    
    # 插入新列到商品名称后面
    df.insert(name_col_idx + 1, 'normalized_name', normalized_names)
    df.insert(name_col_idx + 2, 'tokens', [json.dumps(t, ensure_ascii=False) for t in tokens_list])
    df.insert(name_col_idx + 3, 'detected_brand', detected_brands)
    df.insert(name_col_idx + 4, 'core_name', core_names)
    df.insert(name_col_idx + 5, 'raw_spec', raw_specs)
    df.insert(name_col_idx + 6, 'normalized_spec', normalized_specs)
    df.insert(name_col_idx + 7, 'core_tokens', [json.dumps(t, ensure_ascii=False) for t in core_tokens_list])
    df.insert(name_col_idx + 8, 'attributes', [json.dumps(a, ensure_ascii=False) for a in attributes_list])
    
    # 生成输出文件名
    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{base_name}_normalized_{timestamp}.xlsx"
    
    # 保存结果
    print("[STATUS] 正在保存结果...", flush=True)
    logger.info(f"正在保存结果到: {output_file}")
    try:
        # 清洗非法控制字符（openpyxl/xlsxwriter 不允许 \x00-\x08, \x0b-\x0c, \x0e-\x1f）
        _ILLEGAL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].apply(
                lambda x: _ILLEGAL_CHARS_RE.sub('', x) if isinstance(x, str) else x
            )
        # 优先使用 xlsxwriter 引擎（写入速度比 openpyxl 快 2-3 倍）
        try:
            df.to_excel(output_file, index=False, engine='xlsxwriter')
        except (ImportError, ValueError):
            df.to_excel(output_file, index=False)
        logger.info(f"成功保存 {len(df)} 条记录到: {output_file}")
    except Exception as e:
        logger.error(f"保存Excel文件失败: {e}")
        raise
    
    logger.info("处理完成!")
    return df


# ============================================
# 命令行入口
# ============================================

def main():
    """
    主函数 - 命令行入口
    """
    parser = argparse.ArgumentParser(
        description='商品名称标准化工具 (Product Name Normalizer)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 处理Excel文件
  python -m normalizer.main -i products.xlsx
  
  # 指定输出文件
  python -m normalizer.main -i products.xlsx -o output.xlsx
  
  # 处理单个商品名称
  python -m normalizer.main --name "百瑞意大利式整火腿（去骨）6KG*1条" --brand "百瑞"
        """
    )
    
    parser.add_argument('-i', '--input', 
                       help='输入Excel文件路径')
    parser.add_argument('-o', '--output', 
                       help='输出Excel文件路径 (可选)')
    parser.add_argument('--name', 
                       help='单个商品名称 (用于测试)')
    parser.add_argument('--brand', 
                       help='品牌名称 (配合--name使用)')
    parser.add_argument('--log-level', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO',
                       help='日志级别 (默认: INFO)')
    
    args = parser.parse_args()
    
    # 处理单个商品名称
    if args.name:
        result = normalize_query(args.name, brand=args.brand)
        print("\n" + "="*60)
        print("商品名称标准化结果")
        print("="*60)
        print(f"原始名称: {result['original']}")
        print(f"标准化名称: {result['normalized_name']}")
        print(f"Tokens: {result['tokens']}")
        print("="*60)
        return
    
    # 处理Excel文件
    if args.input:
        if not os.path.exists(args.input):
            print(f"错误: 文件不存在: {args.input}")
            sys.exit(1)
        
        process_excel(args.input, args.output, args.log_level)
        return
    
    # 如果没有提供参数，显示帮助信息
    parser.print_help()


if __name__ == '__main__':
    main()
