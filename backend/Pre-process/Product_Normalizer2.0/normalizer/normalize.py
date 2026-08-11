# -*- coding: utf-8 -*-
"""
标准化核心模块 - 实现商品名称标准化的各个步骤
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from . import config
from . import utils


class ProductNormalizer:
    """
    商品名称标准化器
    
    按照预定义的规则对商品名称进行标准化处理
    """
    
    def __init__(self, brands: List[str] = None, log_level: str = None):
        """
        初始化标准化器
        
        Args:
            brands: 品牌列表
            log_level: 日志级别
        """
        self.logger = utils.setup_logger('ProductNormalizer', log_level)
        self.brands = brands or []
        self.logger.info(f"初始化标准化器，加载品牌数: {len(self.brands)}")
    
    def normalize(self, product_name: str, brand: str = None) -> str:
        """
        对商品名称进行完整标准化
        
        Args:
            product_name: 原始商品名称
            brand: 品牌名称 (可选)
            
        Returns:
            str: 标准化后的商品名称
        """
        if not product_name or not isinstance(product_name, str):
            return ""
        
        original = product_name
        self.logger.debug(f"开始标准化: '{original}'")
        
        # Step 1: 文本清洗
        text = self.step1_clean_text(product_name)
        utils.log_step(self.logger, "Step1-文本清洗", original, text)
        
        # Step 2: 单位统一
        text = self.step2_normalize_units(text)
        utils.log_step(self.logger, "Step2-单位统一", original, text)
        
        # Step 2.5: 长度单位统一 (厘米→cm)
        text = self.step2b_normalize_length_units(text)
        utils.log_step(self.logger, "Step2b-长度单位", original, text)
        
        # Step 2.6: 克/G统一为g
        text = self.step2c_unify_gram_variants(text)
        utils.log_step(self.logger, "Step2c-克/G统一", original, text)
        
        # Step 3: 包装数量标准化
        text = self.step3_normalize_packages(text)
        utils.log_step(self.logger, "Step3-包装标准化", original, text)
        
        # Step 4: 品牌规范
        text = self.step4_normalize_brand(text, brand)
        utils.log_step(self.logger, "Step4-品牌规范", original, text)
        
        # Step 5: 保留括号内容
        text = self.step5_process_brackets(text)
        utils.log_step(self.logger, "Step5-括号处理", original, text)
        
        # Step 6: 称重术语统一
        text = self.step6_unify_weighing_terms(text)
        utils.log_step(self.logger, "Step6-称重术语", original, text)
        
        # 最终清理
        text = utils.normalize_spaces(text)
        
        self.logger.debug(f"标准化完成: '{original}' -> '{text}'")
        return text
    
    def step1_clean_text(self, text: str) -> str:
        """
        Step1: 文本清洗
        
        - 全角→半角
        - 多空格→一个空格
        - 去除首尾空格
        - 中文括号、英文括号统一
        - ×、X统一成*
        - 删除连续特殊符号
        
        Args:
            text: 输入文本
            
        Returns:
            str: 清洗后的文本
        """
        # 1. 全角转半角
        text = utils.fullwidth_to_halfwidth(text)
        
        # 2. 统一乘号
        text = utils.normalize_multiply_chars(text)
        
        # 3. 统一括号 (中文括号转英文括号，后续步骤会处理)
        text = text.replace('（', '(').replace('）', ')')
        text = text.replace('【', '[').replace('】', ']')
        
        # 4. 删除连续特殊符号
        text = utils.remove_special_chars(text)
        
        # 5. 多个空格合并为一个
        text = utils.normalize_spaces(text)
        
        return text
    
    def step2_normalize_units(self, text: str) -> str:
        """
        Step2: 单位统一
        
        将各种单位统一转换为标准单位:
        - 重量: kg/公斤/斤/两/磅/盎司 -> g
        - 体积: L/ML -> mL
        
        Args:
            text: 输入文本
            
        Returns:
            str: 单位统一后的文本
        """
        # 处理重量单位
        for rule_name, rule in config.WEIGHT_UNIT_RULES.items():
            pattern = rule['pattern']
            multiplier = rule['multiplier']
            target_unit = rule['target_unit']
            
            def replace_weight(match):
                value = float(match.group(1))
                return utils.convert_weight_to_gram(value, multiplier)
            
            text = re.sub(pattern, replace_weight, text, flags=re.IGNORECASE)
        
        # 处理体积单位
        for rule_name, rule in config.VOLUME_UNIT_RULES.items():
            pattern = rule['pattern']
            multiplier = rule['multiplier']
            target_unit = rule['target_unit']
            
            def replace_volume(match):
                value = float(match.group(1))
                return utils.convert_volume_to_ml(value, multiplier)
            
            text = re.sub(pattern, replace_volume, text, flags=re.IGNORECASE)
        
        # 统一ML为mL
        text = re.sub(r'(\d+)\s*ML\b', r'\1mL', text)
        text = re.sub(r'(\d+)\s*Ml\b', r'\1mL', text)
        
        return text
    
    def step2b_normalize_length_units(self, text: str) -> str:
        """
        Step2b: 长度单位统一
        
        将中文长度单位转换为英文:
        - 厘米 -> cm
        - 毫米 -> mm
        - 分米 -> dm
        
        Args:
            text: 输入文本
            
        Returns:
            str: 长度单位统一后的文本
        """
        for rule_name, rule in config.LENGTH_UNIT_RULES.items():
            pattern = rule['pattern']
            target_unit = rule['target_unit']
            
            def replace_length(match, unit=target_unit):
                value = match.group(1)
                # 如果是整数，不显示小数点
                if '.' in value:
                    return f"{value}{unit}"
                return f"{int(float(value))}{unit}"
            
            text = re.sub(pattern, replace_length, text)
        
        return text
    
    def step2c_unify_gram_variants(self, text: str) -> str:
        """
        Step2c: 克/G统一为g
        
        将独立的"克"和"G"统一为"g":
        - 500G -> 500g
        - 独立"克" -> g (如: 500克 已在step2处理)
        
        Args:
            text: 输入文本
            
        Returns:
            str: 克/G统一后的文本
        """
        # 处理数字+G (如: 500G -> 500g)
        text = re.sub(r'(\d+(?:\.\d+)?)\s*G\b', r'\1g', text)
        
        # 处理数字+克 (如: 500克 -> 500g)
        text = re.sub(r'(\d+(?:\.\d+)?)\s*克\b', r'\1g', text)
        
        return text
    
    def step3_normalize_packages(self, text: str) -> str:
        """
        Step3: 包装数量标准化
        
        - 20包/箱 -> 20包 箱
        - 1kg*12袋 -> 1000g 12袋
        
        Args:
            text: 输入文本
            
        Returns:
            str: 包装标准化后的文本
        """
        # 处理 "数量单位/包装" 格式
        text = re.sub(
            r'(\d+[包瓶袋盒罐箱桶件支条根个片块粒双组套])\s*/\s*(箱|件|组|套|包|盒)',
            r'\1 \2',
            text
        )
        
        # 处理 "数量*数量单位" 格式 (如: 1kg*12袋)
        # 注意：这里需要在单位转换之后处理，所以单位已经是标准单位
        text = re.sub(
            r'(\d+(?:\.\d+)?g)\s*\*\s*(\d+)\s*([包瓶袋盒罐桶件支条根个片块粒双组套])',
            r'\1 \2\3',
            text
        )
        
        # 处理 "数量单位*数量单位" 格式
        text = re.sub(
            r'(\d+(?:\.\d+)?mL)\s*\*\s*(\d+)\s*([包瓶袋盒罐桶件支条根个片块粒双组套])',
            r'\1 \2\3',
            text
        )
        
        return text
    
    def step4_normalize_brand(self, text: str, brand: str = None) -> str:
        """
        Step4: 品牌规范
        
        - 优先使用品牌列的品牌名，从商品名称中摘除
        - 删除品牌后缀词 (如: 海天牌 -> 海天)
        - 保持品牌一致性
        
        Args:
            text: 输入文本
            brand: 品牌名称 (来自品牌列)
            
        Returns:
            str: 品牌规范化后的文本
        """
        # 优先使用品牌列的品牌，从商品名称中摘除
        if brand and brand.strip():
            brand_clean = brand.strip()
            
            # 尝试移除 "品牌名+后缀" 或 "品牌名" 从商品名称中
            removed = False
            for suffix in config.BRAND_SUFFIXES:
                brand_with_suffix = brand_clean + suffix
                if brand_with_suffix in text:
                    text = text.replace(brand_with_suffix, '', 1)
                    removed = True
                    break
            
            # 如果没有匹配到带后缀的，尝试直接移除品牌名
            if not removed and brand_clean in text:
                text = text.replace(brand_clean, '', 1)
            
            # 清理可能产生的多余空格
            text = utils.normalize_spaces(text)
        
        # 删除品牌后缀词 (兜底处理)
        for suffix in config.BRAND_SUFFIXES:
            pattern = rf'([\u4e00-\u9fff]+){suffix}'
            text = re.sub(pattern, r'\1', text)
        
        return text
    
    def step5_process_brackets(self, text: str) -> str:
        """
        Step5: 保留括号内容，删除括号本身
        
        - （去骨） -> 去骨
        - (前腿) -> 前腿
        
        Args:
            text: 输入文本
            
        Returns:
            str: 处理后的文本
        """
        # 提取括号内容并用空格分隔
        text = utils.remove_brackets(text)
        
        # 清理多余空格
        text = utils.normalize_spaces(text)
        
        return text
    
    def step6_unify_weighing_terms(self, text: str) -> str:
        """
        Step6: 称重术语统一
        
        - 称重 -> 散称
        - 散称 -> 散称 (保持不变)
        - 散装称重 -> 散称
        
        Args:
            text: 输入文本
            
        Returns:
            str: 术语统一后的文本
        """
        for term, unified in config.WEIGHING_TERMS.items():
            text = text.replace(term, unified)
        return text


def normalize_product_name(product_name: str, brand: str = None, 
                          normalizer: ProductNormalizer = None) -> str:
    """
    便捷函数: 对单个商品名称进行标准化
    
    Args:
        product_name: 商品名称
        brand: 品牌名称
        normalizer: 标准化器实例
        
    Returns:
        str: 标准化后的商品名称
    """
    if normalizer is None:
        normalizer = ProductNormalizer()
    
    return normalizer.normalize(product_name, brand)
