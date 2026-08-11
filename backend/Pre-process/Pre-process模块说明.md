# Pre-process 模块说明

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
    ├── spec_words_dict.xlsx       # 规格词库 (637词, 17个分类)
    ├── Brand_words_document.xlsx  # 品牌库 (6131个品牌)
    └── detail_words_dict.xlsx     # 属性词库 (239词, 10个分类)
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

预处理模块依赖 `Spec_words/` 目录下的 3 个 Excel 词库文件，它们分别在预处理流程的不同阶段发挥作用。词库更新后无需修改任何代码，重新运行即可自动生效。

### 7.1 spec_words_dict.xlsx — 规格词库

**存放内容：** 商品名称中的常见产品词和规格相关词汇，按分类组织。

**文件结构：**

| 列 | 说明 | 是否必填 |
|----|------|---------|
| A列 | 分类名称 | 必填（不能为空） |
| B列 | 词条 | 必填（不能为空） |
| C列 | 备注 | 可选 |

第 1 行为表头，从第 2 行开始读取数据。A列和B列均不能为空，否则该行不会被加载。

**当前规模：** 17 个分类，共 637 词。

**在预处理中的作用：** 用于分词阶段（tokenizer.py）的动态规划（DP）深度拆分。分词器会扫描商品名称，尝试用词库中的词条进行最长匹配，将名称拆分为有意义的 token。例如"整火腿"在词库中，所以`整火腿6000g`会被正确拆分为`["整火腿", "6000g"]`，而不是被 jieba 错误切分。

**什么情况下需要新增：**
- 预处理后查看 `tokens` 列，发现某个商品名被**错误拆分**（如一个完整的产品名被拆成了不相关的碎片）
- 某类产品名称反复出现**相同的错误分词**结果
- 新增了一类商品，现有词库中没有对应的产品词

**如何新增：**
1. 打开 `Spec_words/spec_words_dict.xlsx`
2. 在对应分类的最后一行下方新增一行，或新建一个分类
3. 填写 A列（分类）和 B列（词条），C列备注可选
4. 保存即可，重新运行预处理自动生效

> **注意**：不要添加过于宽泛或通用的词（如单字"鱼"、"肉"），否则可能导致分词时误匹配，把本应整体的名称拆散。

---

### 7.2 Brand_words_document.xlsx — 品牌库

**存放内容：** 所有需要识别和摘除的品牌名称，每行一个品牌。

**文件结构：**

| 列 | 说明 |
|----|------|
| A列 | 品牌名称（每行一个，不含"牌"字后缀） |

第 1 行为表头，从第 2 行开始读取。空值、"无"、"nan" 会被自动跳过。

**当前规模：** 6131 个品牌。

**在预处理中的作用：** 用于预处理最先执行的品牌检测阶段（阶段0）。系统通过两种方式识别品牌：
1. **"XX牌"模式**：商品名中出现"品牌名+牌"时直接提取（如"味达美牌"→品牌为"味达美"）
2. **Aho-Corasick 多模匹配**：用整个品牌库对商品名做最长匹配扫描

检测到品牌后，品牌名会从商品名中摘除，单独存入 `detected_brand` 列，不参与后续的 `core_tokens`，避免品牌名干扰产品相似度匹配。

**什么情况下需要新增：**
- 商品库中出现了**新的品牌**，预处理后 `detected_brand` 列为空，但商品名中确实包含品牌信息
- 品牌库中的某个品牌名**被误判**（如产地词"澳洲"、品种词"安格斯"被当成品牌），需要删除或修正

**如何新增：**
1. 打开 `Spec_words/Brand_words_document.xlsx`
2. 在 A列末尾追加新行，填入品牌名称（**不加"牌"字**，如填"味达美"而非"味达美牌"）
3. 保存即可

**如何删除/修正误判品牌：**
1. 在 A列中找到误判的品牌名，删除该行或将内容清空
2. 保存即可

> **注意**：品牌库中的词会优先于 spec_words 被匹配，所以如果一个词既是品牌又是产品名，需要谨慎处理，避免正确产品名被误摘除。

---

### 7.3 detail_words_dict.xlsx — 属性词库

**存放内容：** 描述商品属性的修饰词，如加工方式、品质等级、产地国家等。

**文件结构：**

| 列 | 说明 | 是否必填 |
|----|------|---------|
| A列 | 分类名称 | 必填（不能为空） |
| B列 | 词条 | 必填（不能为空） |
| C列 | 备注 | 可选 |

第 1 行为表头，从第 2 行开始读取。

**当前规模：** 10 个分类，共 239 词。

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
| 加工/状态描述词 | 26 | 冰冻、冷冻、散装、杀好、切片 |

**在预处理中的作用：** 用于属性识别阶段（阶段4）。系统对商品名做贪心最长匹配，将命中的属性词提取到 `attributes` 列。**属性词只识别不摘除**——它们保留在 `normalized_name`、`core_name`、`tokens` 中，仅额外记录到 `attributes` 列，供下游系统参考。

**什么情况下需要新增：**
- 商品库中出现了新的属性描述词，但 `attributes` 列未能识别出来
- 某个属性词被**错误识别**（如产品名中的字被误判为属性词），需要删除

**如何新增：**
1. 打开 `Spec_words/detail_words_dict.xlsx`
2. 在对应分类下新增一行，填写 A列（分类）和 B列（词条）
3. 如果是全新的分类，在 A列填入新分类名即可
4. 保存即可

> **注意**：属性词采用最长匹配，所以如果存在包含关系的词条（如"非转基因"和"转基因"），应确保长词条也在词库中，系统会优先匹配更长的词条。

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
