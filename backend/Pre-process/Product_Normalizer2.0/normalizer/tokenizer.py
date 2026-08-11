# -*- coding: utf-8 -*-
"""
分词器模块 - 将标准化后的商品名称切分为tokens

核心策略：
1. 优先最长匹配规格词库中的词
2. 数字+单位合并为一个token
3. 删除无意义符号token
4. 散称→称重 术语统一
5. 中文文本深度拆分
"""

import re
import logging
from collections import defaultdict
from typing import List, Tuple
from . import config
from . import utils


class ProductTokenizer:
    """
    商品名称分词器
    
    根据数字、单位、品牌、规格词、中文词进行token切分
    优先使用最长匹配策略
    """
    
    def __init__(self, brands: List[str] = None, spec_words: List[str] = None,
                 log_level: str = None):
        """
        初始化分词器
        
        Args:
            brands: 品牌列表
            spec_words: 规格词库 (如不传则使用config中的默认词库)
            log_level: 日志级别
        """
        self.logger = utils.setup_logger('ProductTokenizer', log_level)
        self.brands = brands or []
        self.spec_words = spec_words or config.SPEC_WORDS
        
        # 按长度降序排序，确保最长匹配优先
        self.spec_words_sorted = sorted(self.spec_words, key=len, reverse=True)
        self.brands_sorted = sorted(self.brands, key=len, reverse=True)
        
        # 构建规格词的set用于快速查找
        self.spec_words_set = set(self.spec_words)
        
        # 性能优化：按首字索引品牌（避免每次遍历全部6134个品牌）
        self.brands_by_first_char = defaultdict(list)
        for brand in self.brands_sorted:  # 已按长度降序，保证最长匹配优先
            if brand:
                self.brands_by_first_char[brand[0]].append(brand)
        
        # 性能优化：按首字索引规格词（避免DP中遍历全部549个词）
        self.spec_by_first_char = defaultdict(list)
        for word in self.spec_words_sorted:  # 已按长度降序
            if word:
                self.spec_by_first_char[word[0]].append(word)
        
        # 合法单字白名单：这些单字可以独立作为token，不算残余
        self._legal_single_chars = {
            # 大小描述
            '大', '中', '小',
            # 常见食品单字
            '米', '粉', '糖', '盐', '油', '酱', '醋', '茶', '酒',
            '肉', '鱼', '虾', '蛋', '奶', '豆', '面', '饭',
            '瓜', '果', '菜', '花', '叶', '根', '茎',
            # 形态/加工
            '块', '片', '条', '粒', '丝', '丁', '末', '浆', '汁',
            '丸', '糕', '饼', '冻', '干', '鲜', '熟', '生', '泡',
            # 包装/形态
            '箱', '包', '袋', '瓶', '罐', '盒', '桶', '杯', '碗', '盘',
            # 其他常见
            '个', '只', '份', '组', '套', '排', '串', '把', '张',
            '号', '型', '级', '等', '装', '味', '香', '辣',
            # 括号/容器相关
            '口',
        }
        
        self.logger.info(f"初始化分词器，品牌数: {len(self.brands)}, 规格词数: {len(self.spec_words)}")
    
    def tokenize(self, normalized_name: str) -> List[str]:
        """
        将标准化后的商品名称切分为tokens
        
        处理流程:
        1. 基础分词 (数字/单位/品牌/规格词/中文)
        2. 深度拆分中文词组
        3. 合并相邻的数字+单位
        4. 删除无意义符号
        5. 术语统一 (散称→称重)
        
        Args:
            normalized_name: 标准化后的商品名称
            
        Returns:
            List[str]: token列表
        """
        if not normalized_name or not isinstance(normalized_name, str):
            return []
        
        text = normalized_name.strip()
        
        # Step 1: 基础分词
        raw_tokens = self._basic_tokenize(text)
        self.logger.debug(f"基础分词结果: {raw_tokens}")
        
        # Step 2: 深度拆分中文词组
        split_tokens = self._deep_split_chinese(raw_tokens)
        self.logger.debug(f"深度拆分后: {split_tokens}")
        
        # Step 3: 合并数字+单位
        merged_tokens = self._merge_number_units(split_tokens)
        self.logger.debug(f"合并后结果: {merged_tokens}")
        
        # Step 4: 删除无意义符号
        cleaned_tokens = self._remove_meaningless_tokens(merged_tokens)
        self.logger.debug(f"清理后结果: {cleaned_tokens}")
        
        # Step 5: 术语统一
        final_tokens = self._unify_terms(cleaned_tokens)
        self.logger.debug(f"术语统一后: {final_tokens}")
        
        return final_tokens
    
    def _basic_tokenize(self, text: str) -> List[str]:
        """
        基础分词 - 按规则切分文本
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 原始token列表
        """
        tokens = []
        position = 0
        
        while position < len(text):
            # 跳过空格
            if text[position].isspace():
                position += 1
                continue
            
            # 尝试匹配各种模式
            token, end_pos = self._match_token(text, position)
            
            if token:
                tokens.append(token)
                position = end_pos
            else:
                # 如果无法匹配，单字符前进
                tokens.append(text[position])
                position += 1
        
        return tokens
    
    def _match_token(self, text: str, position: int) -> Tuple[str, int]:
        """
        在指定位置尝试匹配token
        
        匹配优先级:
        1. 数字+单位 (如: 6000g, 500mL)
        2. 数字+中文单位 (如: 1包, 12袋)
        3. 纯数字
        4. 品牌 (最长匹配)
        5. 规格词 (最长匹配)
        6. 连续中文字符
        7. 英文字母
        8. 其他字符
        
        Args:
            text: 完整文本
            position: 当前位置
            
        Returns:
            Tuple[str, int]: (匹配到的token, 结束位置)
        """
        remaining = text[position:]
        
        # 1. 尝试匹配数字+单位 (如: 6000g, 500mL, 30cm, 10mm)
        match = re.match(r'^(\d+(?:\.\d+)?(?:g|mL|kg|ml|L|斤|两|克|磅|盎司|lb|oz|cm|mm|dm|m))', 
                        remaining, re.IGNORECASE)
        if match:
            return match.group(1), position + match.end()
        
        # 2. 尝试匹配数字+中文单位 (如: 1包, 12袋)
        match = re.match(r'^(\d+(?:\.\d+)?[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版])', 
                        remaining)
        if match:
            return match.group(1), position + match.end()
        
        # 3. 尝试匹配纯数字
        match = re.match(r'^(\d+(?:\.\d+)?)', remaining)
        if match:
            return match.group(1), position + match.end()
        
        # 4. 尝试匹配品牌 (最长匹配，方案C：单字品牌需检查是否截断产品名)
        #    性能优化：通过首字索引缩小搜索范围（6134 → 平均~100）
        candidates = self.brands_by_first_char.get(remaining[0], []) if remaining else []
        for brand in candidates:
            if remaining.startswith(brand):
                # 方案C：如果品牌是单字，检查匹配后剩余部分是否以非词库单字开头
                if len(brand) == 1 and len(remaining) > 1:
                    next_char = remaining[len(brand)]
                    # 如果下一个字符是中文且不在词库中，跳过此品牌匹配
                    if '\u4e00' <= next_char <= '\u9fff' and next_char not in self.spec_words_set:
                        continue
                return brand, position + len(brand)
        
        # 5. 规格词匹配已移至_deep_split_chinese的DP算法中处理
        #    不再在基础分词中贪心匹配，而是让全局DP找最优拆分
        
        # 5b. 尝试匹配规格词 (只有当它覆盖整个剩余中文序列时才匹配)
        #     否则留给_deep_split_chinese的DP处理
        chinese_match = re.match(r'^([\u4e00-\u9fff]+)', remaining)
        if chinese_match:
            chinese_text = chinese_match.group(1)
            # 检查是否有spec word完全覆盖这个中文序列
            if chinese_text in self.spec_words_set:
                return chinese_text, position + len(chinese_text)
        # 如果不完全覆盖，不在此处匹配spec words，交给DP处理
        
        # 6. 尝试匹配连续中文字符
        match = re.match(r'^([\u4e00-\u9fff]+)', remaining)
        if match:
            return match.group(1), position + match.end()
        
        # 7. 尝试匹配英文字母
        match = re.match(r'^([a-zA-Z]+)', remaining)
        if match:
            return match.group(1), position + match.end()
        
        # 8. 匹配其他字符 (包括符号)
        if remaining:
            return remaining[0], position + 1
        
        return None, position
    
    def _deep_split_chinese(self, tokens: List[str]) -> List[str]:
        """
        深度拆分中文词组
        
        对于较长的中文token，尝试使用规格词库进行拆分
        例如: "厘米平底锅口" -> ["厘米", "平底锅", "口"]
        
        Args:
            tokens: 原始token列表
            
        Returns:
            List[str]: 拆分后的token列表
        """
        result = []
        
        for token in tokens:
            # 只处理纯中文且长度>=2的token
            if self._is_chinese_token(token) and len(token) >= 2:
                split_result = self._split_chinese_text(token)
                result.extend(split_result)
            else:
                result.append(token)
        
        return result
    
    def _is_chinese_token(self, token: str) -> bool:
        """判断token是否为纯中文"""
        return all('\u4e00' <= c <= '\u9fff' for c in token)
    
    def _split_chinese_text(self, text: str) -> List[str]:
        """
        拆分中文文本为更小的词
        
        设计原则：
        - DP为主：基于spec_words词库的全局最优拆分
        - jieba为兜底：仅当DP无法匹配词库、或jieba的词库命中数明确更多时才采用
        
        决策流程：
        1. 整个文本是规格词 → 保持完整
        2. DP拆分成功且无孤字 → 直接采用
        3. DP有孤字 → 与jieba比较spec_words命中数，选更优者
        4. DP完全无法拆分 → jieba兜底
        
        Args:
            text: 中文文本
            
        Returns:
            List[str]: 拆分后的token列表（可能是完整文本）
        """
        # 如果整个文本就是一个spec word，直接返回，不拆分
        if text in self.spec_words_set:
            return [text]
        
        # 先尝试DP拆分
        dp_tokens = self._try_split(text)
        
        # DP完全无法拆分（结果等于原文），直接用jieba兜底
        if dp_tokens == [text]:
            jieba_tokens = self._jieba_split(text)
            if jieba_tokens and jieba_tokens != [text]:
                return jieba_tokens
            return [text]
        
        # 检查DP结果是否有孤字（不在词库且不在白名单的单字）
        has_orphan = any(
            len(t) == 1 
            and '\u4e00' <= t <= '\u9fff' 
            and t not in self.spec_words_set
            and t not in self._legal_single_chars
            for t in dp_tokens
        )
        
        if not has_orphan:
            # DP拆分干净，直接采用
            return dp_tokens
        
        # DP有孤字 → 与jieba比较，选spec_words命中更多的
        dp_hits = self._count_spec_hits(dp_tokens)
        jieba_tokens = self._jieba_split(text)
        
        if jieba_tokens and jieba_tokens != [text]:
            jieba_hits = self._count_spec_hits(jieba_tokens)
            if jieba_hits > dp_hits:
                # jieba词库命中明确更多，采用jieba
                return jieba_tokens
        
        # DP命中数 >= jieba，信任DP（即使有孤字，核心词已匹配）
        return dp_tokens
    
    def _count_spec_hits(self, tokens: List[str]) -> int:
        """
        计算token列表中spec_words的命中数
        
        计分规则：
        - 完整匹配spec_words: +2（核心指标）
        - 匹配_legal_single_chars: +1（合法单字也算有效）
        
        Args:
            tokens: token列表
            
        Returns:
            int: 命中得分
        """
        score = 0
        for t in tokens:
            if t in self.spec_words_set:
                score += 2
            elif len(t) == 1 and t in self._legal_single_chars:
                score += 1
        return score
    
    def _jieba_split(self, text: str) -> List[str]:
        """
        使用jieba进行中文分词作为兜底方案
        
        Args:
            text: 中文文本
            
        Returns:
            List[str]: jieba分词结果
        """
        try:
            import jieba
            # 使用精确模式分词
            words = list(jieba.cut(text, cut_all=False))
            # 过滤空字符串
            return [w for w in words if w.strip()]
        except ImportError:
            # jieba未安装，返回原文
            return [text]
    
    def _try_split(self, text: str) -> List[str]:
        """
        用动态规划找到全局最优的拆分方案
        
        代价函数为3维元组：(残余字符数, -最大spec_word长度, 匹配词数)
        
        核心思想：
        1. 残余字符数最少（最重要）
        2. 最大spec_word长度最长（优先使用更长的spec_word，如"玉米粒"优于"玉米"+"粒"）
        3. 匹配词数最少（在同等条件下，用更少词完成覆盖）
        
        例如 "金糯玉米粒"：
        - ["金糯", "玉米", "粒"] → 残余0，最大spec_word=2("玉米")，2个词
        - ["金糯", "玉米粒"] → 残余0，最大spec_word=3("玉米粒")，1个词 ✓
        两者残余相同，但"玉米粒"方案最大spec_word更长(3>2)，选"玉米粒"
        
        Args:
            text: 中文文本
            
        Returns:
            List[str]: 最优拆分后的token列表
        """
        n = len(text)
        if n == 0:
            return []
        
        # 构建按位置索引的词库：word_at_pos[i] = 在位置i能匹配的所有词（按长度降序）
        # 性能优化：通过首字索引缩小候选范围（549 → 平均~15）
        word_at_pos = [[] for _ in range(n)]
        for i in range(n):
            for word in self.spec_by_first_char.get(text[i], []):
                wlen = len(word)
                if i + wlen <= n and text[i:i+wlen] == word:
                    word_at_pos[i].append(word)
        
        # DP: dp[i] = (残余字符数, -最大spec_word长度, 匹配词数)
        # 优先级：
        # 1. 残余字符数最少（最重要）
        # 2. 最大spec_word长度最长（优先使用更长的spec_word进行匹配）
        # 3. 匹配词数最少（在同等条件下，用更少词完成覆盖）
        INF = float('inf')
        dp = [(INF, 0, 0)] * (n + 1)
        dp[n] = (0, 0, 0)
        # choice[i] = 在位置i的最优选择
        choice = [None] * (n + 1)
        
        for i in range(n - 1, -1, -1):
            # 选择1: 跳过当前字符（作为残余）
            skip_res, skip_neg_max_sw, skip_neg_w = dp[i + 1]
            skip_cost = (1 + skip_res, skip_neg_max_sw, skip_neg_w)
            
            # 选择2: 匹配一个词
            best_word = None
            best_word_cost = (INF, 0, 0)
            for word in word_at_pos[i]:
                wlen = len(word)
                res, neg_max_sw, neg_w = dp[i + wlen]
                # 计算新路径的最大spec_word长度
                if word in self.spec_words_set:
                    new_max_sw = max(wlen, -neg_max_sw) if neg_max_sw != 0 else wlen
                else:
                    new_max_sw = -neg_max_sw  # 保持原最大值
                new_neg_max_sw = -new_max_sw
                cost = (res, new_neg_max_sw, neg_w + 1)
                if cost < best_word_cost:
                    best_word_cost = cost
                    best_word = word
            
            if skip_cost <= best_word_cost:
                dp[i] = skip_cost
                choice[i] = ('skip', 1)
            else:
                dp[i] = best_word_cost
                choice[i] = ('word', best_word, len(best_word))
        
        # 回溯构建结果
        result = []
        pos = 0
        while pos < n:
            if choice[pos] is None:
                break
            if choice[pos][0] == 'word':
                _, word, wlen = choice[pos]
                result.append(word)
                pos += wlen
            else:
                # 收集连续跳过字符
                residual = []
                while pos < n and choice[pos][0] == 'skip':
                    residual.append(text[pos])
                    pos += 1
                if residual:
                    result.append(''.join(residual))
        
        return result
    
    def _merge_number_units(self, tokens: List[str]) -> List[str]:
        """
        合并相邻的数字和单位token
        
        规则:
        - ['6000', 'g'] -> ['6000g']
        - ['1', '包'] -> ['1包']
        - ['500', 'mL'] -> ['500mL']
        
        Args:
            tokens: 原始token列表
            
        Returns:
            List[str]: 合并后的token列表
        """
        if not tokens:
            return tokens
        
        merged = []
        i = 0
        
        while i < len(tokens):
            current = tokens[i]
            
            # 检查是否可以和下一个token合并
            if i + 1 < len(tokens):
                next_token = tokens[i + 1]
                
                # 数字 + 英文单位 合并 (g, mL, kg, L, cm, mm, dm, m)
                if (re.match(r'^\d+(?:\.\d+)?$', current) and 
                    re.match(r'^(?:g|mL|kg|ml|L|cm|mm|dm|m)$', next_token, re.IGNORECASE)):
                    merged.append(current + next_token)
                    i += 2
                    continue
                
                # 数字 + 中文单位 合并
                if (re.match(r'^\d+(?:\.\d+)?$', current) and 
                    re.match(r'^[包瓶袋盒罐桶件支条根个片块粒双组套份杯提张把串排版]$', next_token)):
                    merged.append(current + next_token)
                    i += 2
                    continue
            
            merged.append(current)
            i += 1
        
        return merged
    
    def _remove_meaningless_tokens(self, tokens: List[str]) -> List[str]:
        """
        删除无意义的符号token
        
        如: *, /, +, - 等
        
        Args:
            tokens: token列表
            
        Returns:
            List[str]: 清理后的token列表
        """
        return [t for t in tokens if t not in config.MEANINGLESS_TOKENS]
    
    def _unify_terms(self, tokens: List[str]) -> List[str]:
        """
        术语统一
        
        如: 称重 → 散称
        
        Args:
            tokens: token列表
            
        Returns:
            List[str]: 术语统一后的token列表
        """
        result = []
        for token in tokens:
            if token in config.WEIGHING_TERMS:
                result.append(config.WEIGHING_TERMS[token])
            else:
                result.append(token)
        return result


def tokenize_text(normalized_name: str, brands: List[str] = None,
                 tokenizer: ProductTokenizer = None) -> List[str]:
    """
    便捷函数: 对标准化后的文本进行分词
    
    Args:
        normalized_name: 标准化后的文本
        brands: 品牌列表
        tokenizer: 分词器实例
        
    Returns:
        List[str]: token列表
    """
    if tokenizer is None:
        tokenizer = ProductTokenizer(brands=brands)
    
    return tokenizer.tokenize(normalized_name)


def tokens_to_json(tokens: List[str]) -> str:
    """
    将token列表转换为JSON字符串
    
    Args:
        tokens: token列表
        
    Returns:
        str: JSON字符串
    """
    import json
    return json.dumps(tokens, ensure_ascii=False)
