# -*- coding: utf-8 -*-
"""
商品匹配算法 V1

召回策略: BM25 + 2-gram 二路召回
粗筛: 品牌过滤
重排: 规格匹配加权 + 属性词命中加权 + 无规格订单的散称候选加分

Usage:
    from matcher import ProductMatcher
    matcher = ProductMatcher(db_path)
    results = matcher.query("五得利五星特精小麦粉25kg", top_n=10)
"""

import os
import sys
import json
import math
import re
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

import pandas as pd

# 将 Pre-process 模块加入路径
_PREPROCESS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', 'Pre-process', 'Product_Normalizer2.0')
sys.path.insert(0, os.path.abspath(_PREPROCESS_DIR))

from normalizer.main import process_single_record, _init_instances, _load_brand_document


class BM25Index:
    """轻量 BM25 索引"""

    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lens = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_lens) / max(self.corpus_size, 1)

        # 构建倒排索引: term -> {doc_id: term_freq}
        self.inverted_index = defaultdict(dict)
        # 文档频率: term -> 包含该term的文档数
        self.df = defaultdict(int)

        for doc_id, doc in enumerate(corpus):
            tf = defaultdict(int)
            for token in doc:
                tf[token] += 1
            for term, freq in tf.items():
                self.inverted_index[term][doc_id] = freq
                self.df[term] += 1

    def score(self, query_tokens: List[str]) -> List[Tuple[int, float]]:
        """计算所有文档对query的BM25得分，返回 (doc_id, score) 列表"""
        scores = defaultdict(float)

        for term in query_tokens:
            if term not in self.inverted_index:
                continue
            df = self.df[term]
            # IDF: log((N - df + 0.5) / (df + 0.5) + 1)
            idf = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)

            for doc_id, tf in self.inverted_index[term].items():
                dl = self.doc_lens[doc_id]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[doc_id] += idf * numerator / denominator

        return list(scores.items())


class BigramIndex:
    """字符 2-gram 倒排索引"""

    def __init__(self, corpus_texts: List[str]):
        self.corpus_size = len(corpus_texts)
        # 每个文档的bigram集合
        self.doc_bigrams = []
        # 倒排索引: bigram -> set(doc_ids)
        self.inverted_index = defaultdict(set)

        for doc_id, text in enumerate(corpus_texts):
            bigrams = self._get_bigrams(text)
            self.doc_bigrams.append(bigrams)
            for bg in bigrams:
                self.inverted_index[bg].add(doc_id)

    @staticmethod
    def _get_bigrams(text: str) -> set:
        """提取字符2-gram集合"""
        text = text.replace(' ', '')
        if len(text) < 2:
            return {text} if text else set()
        return {text[i:i+2] for i in range(len(text) - 1)}

    def recall(self, query_text: str, top_n: int = 200) -> List[Tuple[int, float]]:
        """基于bigram Jaccard相似度召回"""
        query_bigrams = self._get_bigrams(query_text)
        if not query_bigrams:
            return []

        # 统计每个文档命中的bigram数
        hit_counts = defaultdict(int)
        for bg in query_bigrams:
            for doc_id in self.inverted_index.get(bg, set()):
                hit_counts[doc_id] += 1

        # 计算 Jaccard = |intersection| / |union|
        scores = []
        query_size = len(query_bigrams)
        for doc_id, intersection in hit_counts.items():
            doc_size = len(self.doc_bigrams[doc_id])
            union = query_size + doc_size - intersection
            jaccard = intersection / max(union, 1)
            scores.append((doc_id, jaccard))

        scores.sort(key=lambda x: -x[1])
        return scores[:top_n]


class ProductMatcher:
    """
    商品匹配器 V1

    召回: BM25(core_tokens) + 2-gram(core_name) 二路召回
    粗筛: 品牌过滤
    重排: 规格匹配 + 属性命中 + 无规格订单散称优先 加权
    """

    def __init__(self, db_path: str, brand_dict_path: str = None, log_level: str = 'WARNING'):
        """
        初始化匹配器

        Args:
            db_path: 预处理后的商品库Excel路径
            brand_dict_path: 品牌词库路径（默认自动定位）
            log_level: 日志级别
        """
        # 1. 加载品牌词库 & 初始化预处理器
        if brand_dict_path is None:
            brand_dict_path = os.path.join(_PREPROCESS_DIR, 'Spec_words', 'Brand_words_document.xlsx')
        self.brands = _load_brand_document(brand_dict_path)
        _init_instances(self.brands, log_level)

        # 2. 加载商品库
        self.df = pd.read_excel(db_path)
        self._prepare_index()

    def _prepare_index(self):
        """构建索引"""
        # 解析 core_tokens 列 (JSON string -> list)
        self.core_tokens_list = []
        for val in self.df['core_tokens']:
            if pd.isna(val) or not val:
                self.core_tokens_list.append([])
            elif isinstance(val, str):
                try:
                    self.core_tokens_list.append(json.loads(val))
                except json.JSONDecodeError:
                    self.core_tokens_list.append([])
            elif isinstance(val, list):
                self.core_tokens_list.append(val)
            else:
                self.core_tokens_list.append([])

        # 解析 attributes 列
        self.attributes_list = []
        for val in self.df['attributes']:
            if pd.isna(val) or not val:
                self.attributes_list.append([])
            elif isinstance(val, str):
                try:
                    self.attributes_list.append(json.loads(val))
                except json.JSONDecodeError:
                    self.attributes_list.append([])
            elif isinstance(val, list):
                self.attributes_list.append(val)
            else:
                self.attributes_list.append([])

        # 解析 normalized_spec 列
        self.spec_list = []
        for val in self.df['normalized_spec']:
            if pd.isna(val) or not val:
                self.spec_list.append('')
            else:
                self.spec_list.append(str(val).strip())

        # 解析 detected_brand 列
        self.brand_list = []
        for val in self.df['detected_brand']:
            if pd.isna(val) or not val:
                self.brand_list.append('')
            else:
                self.brand_list.append(str(val).strip())

        # core_name 列 (用于bigram)
        self.core_name_list = []
        for val in self.df['core_name']:
            if pd.isna(val) or not val:
                self.core_name_list.append('')
            else:
                self.core_name_list.append(str(val).strip())

        # 预提取 _format_result 需要的列，避免热路径上做 DataFrame 全表扫描
        def _safe_str(series, default=''):
            """将 DataFrame 列转为 Python list[str]，避免 pandas dtype 开销"""
            result = []
            for val in series:
                if pd.isna(val) or val is None:
                    result.append(default)
                else:
                    result.append(str(val).strip())
            return result

        self.product_code_list = _safe_str(self.df['标准产品编码'])
        self.product_name_list = _safe_str(self.df['标准产品名称'])
        self.cat1_list = _safe_str(self.df.get('一级分类', pd.Series(dtype=object)))
        self.unit_list = _safe_str(self.df.get('基本单位', pd.Series(dtype=object)))
        self.is_yihai_list = _safe_str(self.df.get('是否益海', pd.Series(dtype=object)))
        self.brand_full_list = _safe_str(self.df.get('品牌', pd.Series(dtype=object)))
        self.spec_full_list = _safe_str(self.df.get('规格', pd.Series(dtype=object)))

        # 构建 BM25 索引 (基于 core_tokens)
        self.bm25 = BM25Index(self.core_tokens_list)

        # 构建 2-gram 索引 (基于 core_name)
        self.bigram_index = BigramIndex(self.core_name_list)

    def query(self, query_text: str, top_n: int = 10, recall_size: int = 200,
              query_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        查询匹配

        Args:
            query_text: 用户输入的商品名称
            top_n: 返回结果数量
            recall_size: 召回数量

        Returns:
            List[Dict]: 匹配结果列表，每项包含:
                - rank: 排名
                - score: 综合得分
                - 标准产品名称: 原始标准品名
                - 标准产品编码: 产品编码
                - detected_brand: 品牌
                - normalized_spec: 规格
                - core_name: 核心名称
                - attributes: 属性
        """
        if not query_text or not query_text.strip():
            return []

        # Step 1: 对用户输入做预处理（复用Pre-process模块；外部已提供时跳过避免重复计算）
        if query_info is None:
            query_info = process_single_record(
                query_text.strip(), brands_sorted=self.brands
            )
        query_core_tokens = query_info['core_tokens']
        query_brand = query_info['detected_brand']
        query_spec = query_info['normalized_spec']
        query_attributes = query_info['attributes']
        query_core_name = query_info['core_name']

        # Step 2: 二路召回
        # 路径A: BM25 (基于 core_tokens)
        bm25_scores = {}
        if query_core_tokens:
            for doc_id, score in self.bm25.score(query_core_tokens):
                bm25_scores[doc_id] = score

        # 路径B: 2-gram (基于 core_name)
        bigram_scores = {}
        recall_text = query_core_name if query_core_name else query_text
        for doc_id, score in self.bigram_index.recall(recall_text, top_n=recall_size):
            bigram_scores[doc_id] = score

        # 合并召回集 (取并集)
        candidate_ids = set(bm25_scores.keys()) | set(bigram_scores.keys())

        # 限制召回数量: 按各自得分排序取top
        if len(candidate_ids) > recall_size:
            # 归一化后合并得分排序
            bm25_max = max(bm25_scores.values()) if bm25_scores else 1.0
            bigram_max = max(bigram_scores.values()) if bigram_scores else 1.0

            merged = []
            for doc_id in candidate_ids:
                s = (bm25_scores.get(doc_id, 0) / max(bm25_max, 1e-9) +
                     bigram_scores.get(doc_id, 0) / max(bigram_max, 1e-9))
                merged.append((doc_id, s))
            merged.sort(key=lambda x: -x[1])
            candidate_ids = set(doc_id for doc_id, _ in merged[:recall_size])

        # Step 3: 品牌粗筛
        if query_brand:
            filtered = set()
            for doc_id in candidate_ids:
                db_brand = self.brand_list[doc_id]
                if db_brand and (query_brand in db_brand or db_brand in query_brand):
                    filtered.add(doc_id)
            # 如果品牌过滤后候选太少，保留原候选（避免漏召回）
            if len(filtered) >= 5:
                candidate_ids = filtered

        # Step 4: 重排
        bm25_max = max(bm25_scores.values()) if bm25_scores else 1.0
        bigram_max = max(bigram_scores.values()) if bigram_scores else 1.0

        ranked = []
        for doc_id in candidate_ids:
            # 基础得分 (归一化 BM25 + bigram)
            base_score = (bm25_scores.get(doc_id, 0) / max(bm25_max, 1e-9) * 0.6 +
                         bigram_scores.get(doc_id, 0) / max(bigram_max, 1e-9) * 0.4)

            # 规格匹配加分
            spec_bonus = 0.0
            if query_spec and self.spec_list[doc_id]:
                spec_bonus = self._spec_similarity(query_spec, self.spec_list[doc_id])

            # 属性命中加分
            attr_bonus = 0.0
            if query_attributes and self.attributes_list[doc_id]:
                query_attr_set = set(query_attributes)
                db_attr_set = set(self.attributes_list[doc_id])
                overlap = query_attr_set & db_attr_set
                if overlap:
                    attr_bonus = len(overlap) / max(len(query_attr_set), 1) * 0.15

            # 品牌匹配加分（高优先级）
            # 用户显式指定品牌(尤其'XX牌'模式)时，应优先返回同品牌商品。
            # 加分需足以克服同品类内的名称差异(如'微辣鸡米花'vs'鸡米花'的base差距~0.3)，
            # 但又不能过大，避免名称完全不相关的同品牌商品强行上位。
            brand_bonus = 0.0
            if query_brand and self.brand_list[doc_id]:
                if query_brand in self.brand_list[doc_id] or self.brand_list[doc_id] in query_brand:
                    brand_bonus = 0.35

            # 散称优先加分: 订单名称没有规格时，散称类候选更符合预期
            # （如'沙葱' → '沙葱（散称）' 应优于 '沙葱0.5kg*20盒/箱'）
            bulk_bonus = 0.0
            if not query_spec:
                db_spec_i = self.spec_list[doc_id]
                if db_spec_i and any(t in db_spec_i for t in self._BULK_TERMS):
                    bulk_bonus = self._BULK_BONUS

            final_score = base_score + spec_bonus + attr_bonus + brand_bonus + bulk_bonus
            ranked.append((doc_id, final_score))

        ranked.sort(key=lambda x: -x[1])

        # Step 5: 构建返回结果（全部用预提取的 list，不走 pandas iloc）
        results = []
        for rank, (doc_id, score) in enumerate(ranked[:top_n], 1):
            results.append({
                'rank': rank,
                'score': round(score, 4),
                '标准产品名称': self.product_name_list[doc_id],
                '标准产品编码': self.product_code_list[doc_id],
                'detected_brand': self.brand_list[doc_id],
                'normalized_spec': self.spec_list[doc_id],
                'core_name': self.core_name_list[doc_id],
                'attributes': self.attributes_list[doc_id],
                # _format_result 需要的额外字段
                'product_code': self.product_code_list[doc_id],
                'product_name': self.product_name_list[doc_id],
                '_cat1': self.cat1_list[doc_id],
                '_unit': self.unit_list[doc_id],
                '_is_yihai': self.is_yihai_list[doc_id],
                '_brand_full': self.brand_full_list[doc_id],
                '_spec_full': self.spec_full_list[doc_id],
            })

        return results

    @staticmethod
    def _spec_similarity(query_spec: str, db_spec: str) -> float:
        """
        规格相似度计算

        核心逻辑: 数值精确匹配给强加分，数值不匹配给惩罚
        - 数值+单位完全匹配: +0.5
        - 数值匹配(单位不同): +0.4
        - 一方无规格: 0
        - 双方都有规格但数值不同: -0.1 (惩罚)
        """
        if not query_spec or not db_spec:
            return 0.0

        # 提取数值
        query_nums = set(re.findall(r'\d+(?:\.\d+)?', query_spec))
        db_nums = set(re.findall(r'\d+(?:\.\d+)?', db_spec))

        # 提取单位
        query_units = set(re.findall(r'[a-zA-Z]+|[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板]', query_spec))
        db_units = set(re.findall(r'[a-zA-Z]+|[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板]', db_spec))

        num_overlap = query_nums & db_nums
        unit_overlap = query_units & db_units

        if num_overlap and unit_overlap:
            return 0.5  # 数值+单位完全匹配
        elif num_overlap:
            return 0.4  # 数值匹配
        elif query_nums and db_nums and not num_overlap:
            return -0.1  # 数值不匹配，惩罚
        return 0.0

    def query_extended(self, query_text: str, top_n: int = 50,
                       query_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """扩展查询，返回更多结果（用于下拉列表）"""
        return self.query(query_text, top_n=top_n, recall_size=500, query_info=query_info)

    # ============================================
    # 重排阶段常量
    # ============================================
    # 散称类规格术语: 订单名称无规格时，含这些术语的候选获得加分
    _BULK_TERMS = ('散称', '称重', '散装')
    _BULK_BONUS = 0.3

    # ============================================
    # 匹配置信度评分（独立于召回重排得分）
    # ============================================
    # 目的: 对召回重排后的备选列表逐条评估"匹配结果大概率正确"的程度，
    # 供用户识别哪些可直接采信、哪些需人工核查。
    # 三个维度:
    #   1. 品牌对应（订单有品牌时，结果无品牌或品牌不同 → 低分）
    #   2. 规格对应（订单有规格时，一致满分/不一致低分）
    #   3. 除品牌与规格外的核心名称最小编辑距离

    # 各维度权重（仅参与有订单信息的维度，权重自动归一化）
    _CONF_W_BRAND = 0.3
    _CONF_W_SPEC = 0.3
    _CONF_W_NAME = 0.4

    @staticmethod
    def _edit_distance(a: str, b: str) -> int:
        """最小编辑距离（Levenshtein，滚动数组实现）"""
        if not a:
            return len(b)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1,        # 删除
                               cur[j - 1] + 1,     # 插入
                               prev[j - 1] + (0 if ca == cb else 1)))  # 替换
            prev = cur
        return prev[-1]

    @classmethod
    def _brand_conf_score(cls, query_brand: str, db_brand: str) -> float:
        """
        品牌维度得分
        - 双方均无品牌: 1.0（不扣分）
        - 订单无品牌，结果有品牌: 0.8（少扣一点）
        - 订单有品牌，结果无品牌: 0.1（多扣一点）
        - 订单有品牌，结果品牌不一致: 0.0（最大扣分）
        - 订单有品牌，结果品牌匹配（互相包含）: 1.0
        """
        # 双方均无品牌: 不扣分
        if not query_brand and not db_brand:
            return 1.0
        # 订单无品牌，结果有品牌: 少扣一点
        if not query_brand and db_brand:
            return 0.8
        # 订单有品牌，结果无品牌: 多扣一点
        if query_brand and not db_brand:
            return 0.1
        # 订单有品牌，结果有品牌: 检查是否匹配
        if query_brand in db_brand or db_brand in query_brand:
            return 1.0
        # 品牌不一致: 最大扣分
        return 0.0

    @classmethod
    def _spec_conf_score(cls, query_spec: str, db_spec: str) -> float:
        """
        规格维度得分（仅当订单条目有规格时参与评分）
        - 数值+单位均匹配: 1.0
        - 数值匹配（单位不同）: 0.7
        - 结果无规格: 0.2
        - 数值不一致: 0.0
        - 纯文本规格（无数字，如"散称/称重"）: 完全一致 1.0 / 包含关系 0.5 / 不一致 0.0
        """
        if not db_spec:
            return 0.2
        q_nums = set(re.findall(r'\d+(?:\.\d+)?', query_spec))
        d_nums = set(re.findall(r'\d+(?:\.\d+)?', db_spec))

        # 纯文本规格（如"散称/称重"）: 无数字可比，改为字符串直接比较
        if not q_nums or not d_nums:
            if query_spec.strip() == db_spec.strip():
                return 1.0
            if query_spec.strip() and (query_spec in db_spec or db_spec in query_spec):
                return 0.5
            return 0.0

        q_units = set(re.findall(r'[a-zA-Z]+|[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板]', query_spec))
        d_units = set(re.findall(r'[a-zA-Z]+|[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版板]', db_spec))
        if q_nums & d_nums:
            return 1.0 if (q_units & d_units) else 0.7
        return 0.0

    @classmethod
    def _name_conf_score(cls, query_core: str, db_core: str) -> float:
        """核心名（除品牌与规格）维度得分: 1 - 归一化最小编辑距离"""
        q = (query_core or '').strip()
        d = (db_core or '').strip()
        if not q and not d:
            return 1.0
        dist = cls._edit_distance(q, d)
        return max(0.0, 1.0 - dist / max(len(q), len(d), 1))

    @classmethod
    def compute_confidence(cls, query_info: Dict[str, Any], candidate: Dict[str, Any]) -> float:
        """
        计算单条候选的匹配置信度（0~1，与召回重排得分无关）

        Args:
            query_info: 订单条目归一化结果（process_single_record 的输出），
                        需含 detected_brand / normalized_spec / core_name
            candidate: 召回候选（含 detected_brand / normalized_spec / core_name）

        Returns:
            float: 置信度得分（0~1），保留 2 位小数
        """
        q_brand = (query_info.get('detected_brand') or '').strip()
        q_spec = (query_info.get('normalized_spec') or '').strip()
        q_core = (query_info.get('core_name') or '').strip()

        total_w = 0.0
        total_s = 0.0

        # 维度 1: 品牌（始终参与评分）
        total_w += cls._CONF_W_BRAND
        total_s += cls._CONF_W_BRAND * cls._brand_conf_score(
            q_brand, (candidate.get('detected_brand') or '').strip())

        # 维度 2: 规格（仅订单有规格时参与）
        if q_spec:
            total_w += cls._CONF_W_SPEC
            total_s += cls._CONF_W_SPEC * cls._spec_conf_score(
                q_spec, (candidate.get('normalized_spec') or '').strip())

        # 维度 3: 核心名编辑距离（始终参与）
        total_w += cls._CONF_W_NAME
        total_s += cls._CONF_W_NAME * cls._name_conf_score(
            q_core, (candidate.get('core_name') or '').strip())

        return round(total_s / total_w, 2) if total_w > 0 else 0.0

