# -*- coding: utf-8 -*-
"""
商品名称标准化工具包 (Product Name Normalizer)

用于将商品名称标准化为统一格式，便于后续的BM25检索匹配。

主要功能:
- 文本清洗 (全角转半角、统一符号等)
- 单位统一 (kg->g, L->mL等)
- 包装数量标准化
- 品牌规范
- 括号内容处理
- 称重术语统一 (散称→称重)
- Token切分 (最长匹配策略)
- 无意义符号清理

使用示例:
    from normalizer import normalize_query, process_excel
    
    # 标准化单个query
    result = normalize_query("百瑞意大利式整火腿（去骨）6KG*1条", brand="百瑞")
    print(result['normalized_name'])  # 百瑞 意大利式 整火腿 去骨 6000g 1条
    print(result['tokens'])           # ['百瑞', '意大利式', '整火腿', '去骨', '6000g', '1条']
    
    # 批量处理Excel文件
    df = process_excel("products.xlsx")
"""

from .normalize import ProductNormalizer, normalize_product_name
from .tokenizer import ProductTokenizer, tokenize_text, tokens_to_json
from .main import (
    normalize_query,
    normalize_batch,
    process_excel,
    get_normalizer,
    get_tokenizer,
)

__version__ = '2.0.0'
__author__ = 'Product Search Team'

__all__ = [
    # 核心类
    'ProductNormalizer',
    'ProductTokenizer',
    
    # 便捷函数 - 单个query
    'normalize_query',
    'normalize_product_name',
    'tokenize_text',
    'tokens_to_json',
    
    # 便捷函数 - 批量处理
    'normalize_batch',
    'process_excel',
    
    # 实例获取
    'get_normalizer',
    'get_tokenizer',
]
