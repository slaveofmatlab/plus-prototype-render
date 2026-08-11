# -*- coding: utf-8 -*-
"""
测试模块 - 商品名称标准化工具的单元测试
"""

import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalizer.normalize import ProductNormalizer
from normalizer.tokenizer import ProductTokenizer


class TestProductNormalizer(unittest.TestCase):
    """测试商品名称标准化器"""
    
    def setUp(self):
        """初始化测试环境"""
        self.brands = ['百瑞', '海天', '伊利', '蒙牛']
        self.normalizer = ProductNormalizer(brands=self.brands, log_level='WARNING')
        self.tokenizer = ProductTokenizer(brands=self.brands, log_level='WARNING')
    
    def test_step1_clean_text(self):
        """测试Step1: 文本清洗"""
        # 全角转半角
        self.assertEqual(
            self.normalizer.step1_clean_text('（去骨）'),
            '(去骨)'
        )
        
        # 乘号统一
        self.assertEqual(
            self.normalizer.step1_clean_text('6KG×1条'),
            '6KG*1条'
        )
        
        # 多个空格合并
        self.assertEqual(
            self.normalizer.step1_clean_text('百瑞  火腿'),
            '百瑞 火腿'
        )
    
    def test_step2_normalize_units(self):
        """测试Step2: 单位统一"""
        # kg -> g
        self.assertEqual(
            self.normalizer.step2_normalize_units('6KG'),
            '6000g'
        )
        
        # 小数kg -> g
        self.assertEqual(
            self.normalizer.step2_normalize_units('2.5kg'),
            '2500g'
        )
        
        # 公斤 -> g
        self.assertEqual(
            self.normalizer.step2_normalize_units('1公斤'),
            '1000g'
        )
        
        # 斤 -> g
        self.assertEqual(
            self.normalizer.step2_normalize_units('5斤'),
            '2500g'
        )
        
        # 克 -> g
        self.assertEqual(
            self.normalizer.step2_normalize_units('1000克'),
            '1000g'
        )
        
        # ML -> mL
        self.assertEqual(
            self.normalizer.step2_normalize_units('500ML'),
            '500mL'
        )
        
        # L -> mL
        self.assertEqual(
            self.normalizer.step2_normalize_units('2L'),
            '2000mL'
        )
    
    def test_step3_normalize_packages(self):
        """测试Step3: 包装数量标准化"""
        # 20包/箱 -> 20包 箱
        self.assertEqual(
            self.normalizer.step3_normalize_packages('20包/箱'),
            '20包 箱'
        )
        
        # 6瓶/箱 -> 6瓶 箱
        self.assertEqual(
            self.normalizer.step3_normalize_packages('6瓶/箱'),
            '6瓶 箱'
        )
        
        # 1kg*12袋 -> 1000g 12袋 (需要先转换单位)
        text = self.normalizer.step2_normalize_units('1kg*12袋')
        result = self.normalizer.step3_normalize_packages(text)
        self.assertEqual(result, '1000g 12袋')
    
    def test_step4_normalize_brand(self):
        """测试Step4: 品牌规范"""
        # 海天牌 -> 海天
        self.assertEqual(
            self.normalizer.step4_normalize_brand('海天牌酱油'),
            '海天酱油'
        )
        
        # 伊利品牌 -> 伊利
        self.assertEqual(
            self.normalizer.step4_normalize_brand('伊利品牌牛奶'),
            '伊利牛奶'
        )
    
    def test_step5_process_brackets(self):
        """测试Step5: 括号处理"""
        # （去骨） -> 去骨
        self.assertEqual(
            self.normalizer.step5_process_brackets('整火腿（去骨）'),
            '整火腿 去骨'
        )
        
        # (前腿) -> 前腿
        self.assertEqual(
            self.normalizer.step5_process_brackets('猪肉(前腿)'),
            '猪肉 前腿'
        )
    
    def test_full_normalization(self):
        """测试完整标准化流程"""
        # 测试用例1: 百瑞意大利式整火腿
        result = self.normalizer.normalize(
            '百瑞意大利式整火腿（去骨）6KG*1条',
            brand='百瑞'
        )
        self.assertIn('百瑞', result)
        self.assertIn('6000g', result)
        self.assertIn('去骨', result)
        
        # 测试用例2: 海天牌酱油
        result = self.normalizer.normalize(
            '海天牌酱油500ML',
            brand='海天'
        )
        self.assertIn('海天', result)
        self.assertIn('500mL', result)
    
    def test_tokenization(self):
        """测试分词功能"""
        # 测试基本分词
        tokens = self.tokenizer.tokenize('百瑞 意大利式 整火腿 去骨 6000g')
        self.assertIn('百瑞', tokens)
        self.assertIn('整火腿', tokens)
        self.assertIn('6000g', tokens)
        
        # 测试数字+单位合并
        tokens = self.tokenizer.tokenize('1000g 12袋')
        self.assertIn('1000g', tokens)
        self.assertIn('12袋', tokens)
    
    def test_edge_cases(self):
        """测试边界情况"""
        # 空字符串
        self.assertEqual(self.normalizer.normalize(''), '')
        self.assertEqual(self.normalizer.normalize(None), '')
        
        # 纯数字
        result = self.normalizer.normalize('123')
        self.assertEqual(result, '123')
        
        # 纯英文
        result = self.normalizer.normalize('ABC')
        self.assertEqual(result, 'ABC')
        
        # 特殊字符
        result = self.normalizer.normalize('商品***名称')
        self.assertNotIn('***', result)


class TestProductTokenizer(unittest.TestCase):
    """测试商品名称分词器"""
    
    def setUp(self):
        """初始化测试环境"""
        self.brands = ['百瑞', '海天']
        self.tokenizer = ProductTokenizer(brands=self.brands, log_level='WARNING')
    
    def test_brand_recognition(self):
        """测试品牌识别"""
        tokens = self.tokenizer.tokenize('百瑞火腿')
        self.assertIn('百瑞', tokens)
    
    def test_spec_word_recognition(self):
        """测试规格词识别"""
        tokens = self.tokenizer.tokenize('整火腿')
        self.assertIn('整火腿', tokens)
        
        # 不应该拆分
        self.assertNotIn('整', tokens)
        self.assertNotIn('火腿', tokens)
    
    def test_number_unit_merge(self):
        """测试数字+单位合并"""
        tokens = self.tokenizer.tokenize('6000g 1条')
        self.assertIn('6000g', tokens)
        self.assertIn('1条', tokens)


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试
    suite.addTests(loader.loadTestsFromTestCase(TestProductNormalizer))
    suite.addTests(loader.loadTestsFromTestCase(TestProductTokenizer))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    run_tests()
