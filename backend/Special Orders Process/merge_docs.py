import os

content = r"""# Pre-process 模块说明

## 一、功能概述

Pre-process 模块负责将从**丰厨平台**导出的「标准商品信息」表单进行结构化预处理，包括：

- 商品名称标准化（单位统一、文本清洗、品牌摘除）
- 智能分词（基于领域词库 + 动态规划 + jieba 兜底）
- 品牌自动识别
- 规格信息分离
- 属性信息识别（国家与地区、加工状态、工艺等级等）
- 核心产品名称提取

处理后的数据用于下游的**商品价格推荐**系统，通过 `core_tokens` 进行产品相似度匹配（BM25 检索）。

---

## 二、数据来源

| 来源 | 说明 |
|------|------|
| 丰厨平台 → 标准商品信息 | 导出为 `.xlsx` 文件，包含「标准产品名称」列 |
| 典型文件 | `RSM_723.xlsx`、`RSM_723 - 干调（品牌填充版）.xlsx` |

原始表单中的关键列：`标准产品名称`（系统自动识别，也支持「商品名称」「产品名称」「品名」）

> **表头自动检测**：如果第一行是数据而非表头，工具会自动尝试第 2–6 行作为表头。

---

## 三、处理流程

```
原始商品名称: "味达美牌味极鲜酱油1L/瓶"
        │
        ▼
┌─────────────────────────────────────────┐
│  阶段0: 品牌检测                         │
│  · "XX牌"模式优先 → 提取"味达美"         │
│  · 回退: Aho-Corasick 品牌库最长匹配      │
─────────────────────────────────────────┘
        │ detected_brand = "味达美"
        ▼
┌─────────────────────────────────────────┐
│  阶段1: 标准化 (normalize.py)            │
│  Step1 文本清洗: 全角→半角, ×→*, 括号统一 │
│  Step2 单位统一: 1L→1000mL, 1kg→1000g   │
│  Step3 包装标准化: 数量格式统一            │
│  Step4 品牌摘除: 移除"味达美牌"           │
│  Step5 括号处理: 去括号保留内容            │
│  Step6 称重术语: 称重/散装→散称           │
└─────────────────────────────────────────┘
        │ normalized = "味极鲜酱油1000mL/瓶"
        ▼
┌─────────────────────────────────────────┐
│  阶段2: 分词 (tokenizer.py)              │
│  2.1 基础分词: 数字+单位 > 品牌 > 中文chunk│
│  2.2 DP深度拆分: spec_words全局最优匹配    │
│  2.3 jieba兜底: 仅DP无法匹配时启用        │
│  2.4 后处理: 合并数字单位, 删除符号        │
└─────────────────────────────────────────┘
        │ tokens = ["味达美","味极鲜","酱油","1000mL","瓶"]
        ▼
┌─────────────────────────────────────────┐
│  阶段3: 规格分离 (main.py)               │
│  · 提取 normalized_spec: "1000mL 瓶"     │
│  · 提取 raw_spec: "1L 瓶"               │
│  · 生成 core_name: "味极鲜酱油"          │
│  · 生成 core_tokens: ["味极鲜","酱油"]    │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  阶段4: 属性识别 (main.py)               │
│  · 基于 detail_words_dict.xlsx 属性词表   │
│  · 贪心最长匹配，避免子串误匹配           │
│  · 只识别提取，不从名称中摘除             │
│  · 示例: "非转基因一级大豆油"             │
│    → attributes: ["非转基因", "一级"]     │
└─────────────────────────────────────────┘
```

| 步骤 | 功能 | 示例 |
|------|------|------|
| 品牌检测 | Aho-Corasick 多模匹配 | `可口可乐330ml` → 检测到"可口可乐" |
| Step1 | 全角→半角、统一符号 | `（去骨）` → `(去骨)` |
| Step2 | 单位统一为 g/mL | `6KG` → `6000g`, `500ml` → `500mL` |
| Step3 | 包装数量标准化 | `20包/箱` → `20包 箱` |
| Step4 | 移除品牌名 | `可口可乐330mL` → `330mL` |
| Step5 | 去括号保留内容 | `(去骨)` → `去骨` |
| Step6 | 称重术语统一 | `称重` → `散称` |
| 分词 | DP最优拆分 + jieba兜底 | `整火腿6000g` → `['整火腿', '6000g']` |

---

## 四、输出字段

处理后在原表基础上插入 8 列（位于商品名称列之后）：

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `normalized_name` | str | 标准化后完整名称 | 味极鲜酱油1000mL/瓶 |
| `tokens` | JSON str | 全量分词（含品牌+规格） | ["味达美","味极鲜","酱油","1000mL","瓶"] |
| `detected_brand` | str | 识别到的品牌 | 味达美 |
| `core_name` | str | 去品牌去规格的核心产品名 | 味极鲜酱油 |
| `raw_spec` | str | 原始规格（保留原单位） | 1L 瓶 |
| `normalized_spec` | str | 标准化规格（单位已统一） | 1000mL 瓶 |
| `core_tokens` | JSON str | 核心产品tokens（无品牌无规格，匹配算法核心依据） | ["味极鲜","酱油"] |
| `attributes` | JSON str | 识别到的属性词列表 | ["非转基因", "一级"] |

`process_single_record()` 返回字典还包含：`original`、`tokens_json`、`core_tokens_json`、`attributes_json`。

---

## 五、涉及文件

### 核心代码

```
Pre-process/Product_Normalizer2.0/
├── run_normalizer.py          # 命令行启动脚本
├── normalizer/
│   ├── __init__.py            # 包初始化，导出公共接口
│   ├── main.py                # 主入口: process_single_record / process_excel
│   ├── normalize.py           # 标准化器 (6步文本预处理)
│   ├── tokenizer.py           # 分词器 (DP + jieba兜底)
│   ├── config.py              # 配置加载 (词库/规则)
│   ├── utils.py               # 工具函数
│   └── test_normalizer.py     # 单元测试
└── Spec_words/
    ├── spec_words_dict.xlsx   # 规格词库 (636词, 16个分类, 底色区分)
    ├── Brand_words_document.xlsx  # 品牌库 (6131个品牌)
    ├── detail_words_dict.xlsx # 属性词库 (237词, 10个分类)
```

### 辅助脚本

```
Pre-process/
├── fill_brands.py             # 品牌字段填充
├── fill_brands_gantiao.py     # 干调品牌填充
├── extract_brands.py          # 品牌提取
└── filter_gantiao.py          # 干调数据筛选
```

### 迁移说明

本工具设计为**完全独立可迁移**：

1. **复制整个 `Product_Normalizer2.0` 文件夹**到任意位置
2. **安装依赖**: `pip install pandas openpyxl`
3. **直接运行**: 无需修改任何配置

- 所有内部路径均使用**相对于脚本位置的动态路径**
- 词库文件 (`Spec_words/`) 相对于 `normalizer/config.py` 定位
- 输入文件可以是**任意绝对路径或相对路径**
- 跨平台：Windows / macOS / Linux

---

## 六、使用说明

### 6.1 批量处理（命令行）

```bash
cd Pre-process/Product_Normalizer2.0

# 基本用法（输出文件自动命名: 原文件名_normalized_时间戳.xlsx）
python run_normalizer.py "C:\LIU QINGQING\Projects\Product_Price_Recommendation\Database\RSM_723.xlsx"

# 指定输出路径
python run_normalizer.py input.xlsx output.xlsx
```

### 6.2 Python 模块方式

```bash
cd Product_Normalizer2.0

# 处理Excel文件
python -m normalizer.main -i "products.xlsx"

# 指定输出文件
python -m normalizer.main -i "products.xlsx" -o "output.xlsx"

# 测试单个商品名称
python -m normalizer.main --name "百瑞意大利式整火腿（去骨）6KG*1条" --brand "百瑞"
```

### 6.3 单条处理（函数调用）

```python
import sys
sys.path.insert(0, 'Pre-process/Product_Normalizer2.0')

from normalizer.main import process_single_record, _init_instances, _load_brand_document

# 初始化（一次性）
brands = _load_brand_document('Pre-process/Product_Normalizer2.0/Spec_words/Brand_words_document.xlsx')
_init_instances(brands, 'WARNING')

# 处理单条
result = process_single_record("味达美牌味极鲜酱油1L/瓶", brands_sorted=brands)

print(result['detected_brand'])    # "味达美"
print(result['normalized_name'])   # "味极鲜酱油1000mL/瓶"
print(result['tokens'])            # ["味达美", "味极鲜", "酱油", "1000mL", "瓶"]
print(result['core_name'])         # "味极鲜酱油"
print(result['core_tokens'])       # ["味极鲜", "酱油"]
print(result['normalized_spec'])   # "1000mL 瓶"
print(result['raw_spec'])          # "1L 瓶"
print(result['attributes'])        # [] (该商品无属性词命中)
```

### 6.4 批量处理（函数调用）

```python
from normalizer.main import process_excel

# 处理整个Excel文件
df = process_excel(
    input_file="Database/RSM_723.xlsx",
    output_file=None,  # None=自动命名
    log_level='INFO'
)
```

### 6.5 运行测试

```bash
cd Product_Normalizer2.0
python -m pytest normalizer/test_normalizer.py -v
```

---

## 七、词库维护

### 添加规格词

在 `Spec_words/spec_words_dict.xlsx` 中添加行：

| 分类 (A列) | 词条 (B列) | 备注 (C列) |
|------------|-----------|-----------|
| 调味品 | 辣椒面 | |
| 加工/状态描述词 | 谷饲 | 谷物饲养 |

> 注意：A列（分类）和 B列（词条）均不能为空，否则不会被加载。

### 品牌库维护

在 `Spec_words/Brand_words_document.xlsx` 中增删品牌。需摘除的常见误判：
- 产地词（澳洲、澳大利亚等）
- 品种词（安格斯、大红袍等）
- 描述词（澳洲谷饲等）

### 属性词库维护

在 `Spec_words/detail_words_dict.xlsx` 中增删属性词，格式：

| 分类 (A列) | 词条 (B列) | 备注 (C列) |
|------------|-----------|-----------|
| 国家与地区 | 日本 | |
| 加工/状态描述词 | 冰冻 | |
| 加工方式 | 非转基因 | |
| 品质等级 | 特级 | |

当前属性词库包含 **10 个分类**（共 237 词）：

| 分类 | 数量 | 示例 |
|------|------|------|
| 加工方式 | 29 | 转基因、非转基因、压榨、浸出、酿造、有机 |
| 品质等级 | 14 | 一级、二级、特级、精选 |
| 处理状态 | 22 | 去皮、去骨、切块、切片、整只 |
| 来源产地 | 8 | 国产、进口、野生、养殖 |
| 包装方式 | 13 | 袋装、盒装、瓶装、真空 |
| 特殊工艺 | 12 | 手工、传统、低温、巴氏 |
| 风格样式 | 20 | 日式、法式、浓香型、家庭装 |
| 储存条件 | 7 | 常温保存、冷藏保存 |
| 国家与地区 | 88 | 中国、日本、澳洲、东南亚 |
| 加工/状态描述词 | 24 | 冰冻、冷冻、散装、杀好、切片 |

**属性识别规则：**
- 采用**贪心最长匹配**：优先匹配最长词条，避免"非转基因"被误识别为"转基因"
- **只识别不摘除**：属性词保留在 `normalized_name`、`core_name`、`tokens` 中，仅额外记录到 `attributes` 列
- 匹配区间不重叠：已匹配区间内的子串不再重复匹配

---

## 八、性能优化

| 优化项 | 技术 | 效果 |
|--------|------|------|
| 品牌检测 | Aho-Corasick 多模匹配 | 6131品牌一次扫描完成 |
| 分词器品牌匹配 | 首字索引 | 候选范围缩小 60x |
| DP词库扫描 | 首字索引 | 候选范围缩小 35x |
| Excel读取 | python-calamine (Rust) | 读取速度 5-10x |
| Excel写入 | xlsxwriter | 写入速度 2-3x |
| 批量日志 | WARNING级别 | 消除逐条日志I/O |

> 所有加速依赖均为可选，未安装时自动回退到默认实现，不影响功能。

---

## 九、依赖环境

```
Python >= 3.10
pandas
openpyxl
jieba
pyahocorasick (可选, 品牌匹配加速)
xlsxwriter (可选, 写入加速)
python-calamine (可选, 读取加速)
```

安装：
```bash
pip install pandas openpyxl jieba pyahocorasick xlsxwriter python-calamine
```

---

## 十、常见问题

**Q: 提示找不到词库文件？**
A: 确保 `Spec_words/` 文件夹与 `normalizer/` 文件夹在同一目录下。

**Q: 输出文件在哪里？**
A: 默认生成在输入文件同目录，命名为 `原文件名_normalized_时间戳.xlsx`。

**Q: 如何更新词库？**
A: 直接编辑 `Spec_words/` 下的 Excel 文件，重新运行即可生效。

**Q: 报错 "cannot be used in worksheets"？**
A: 商品名称中含有不可见控制字符，工具已自动清洗，若仍报错请检查源文件编码。

**Q: 报错 "缺少商品名称列"？**
A: 工具支持识别「商品名称/标准产品名称/产品名称/品名」四种列名，并自动检测表头行（第2-6行）。若仍失败，请确认文件含有上述列名之一。
"""

output_path = r'C:\LIU QINGQING\Projects\Product_Price_Recommendation\Pre-process\Pre-process模块说明.md'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Written to {output_path}')
