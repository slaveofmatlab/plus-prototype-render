# PLUS 报价申请原型 & product_match 后端

本项目是 **PLUS 报价申请系统** 的可部署原型，将 HTML 交互原型与真实的 product_match 后端服务集成在一起，通过 Render 一键部署即可在线体验完整的报价申请流程。

---

## 项目结构

```
plus-prototype-render/
├── README.md
├── render.yaml                    # Render 部署配置
├── .gitignore
└── backend/                       # 后端服务（Render 根目录）
    ├── requirements.txt
    ├── backend/
    │   ├── main.py                # FastAPI 入口，同时挂载前端静态页面
    │   ├── config.py              # 路径配置（基于 __file__ 自动计算，支持任意部署位置）
    │   ├── state.py               # 内存态任务状态管理
    │   ├── routers/
    │   │   ├── upload.py          # 文件上传 + Sheet/列选择
    │   │   ├── match.py           # 批量匹配 + 候选切换
    │   │   ├── quote.py           # 报价数据查询
    │   │   └── preprocess_match.py# 一体化上传→预处理→匹配→查价
    │   └── services/
    │       ├── file_parser.py     # Excel 解析（自动识别表头与商品名称列）
    │       ├── matcher_service.py # 匹配算法服务封装
    │       ├── preprocess_service.py # 预处理路由（普通/特殊客户分流）
    │       ├── quote_service.py   # 历史报价索引与查询
    │       └── procurement_service.py # 采购数据索引与查询
    ├── frontend/                  # PLUS 原型 HTML 页面
    │   ├── index.html             # 入口重定向
    │   ├── PRD.Quote-Request-New.html        # 桌面端-新增报价申请（向导）
    │   ├── PRD.Quote-Request-Detail.html     # 桌面端-报价申请详情
    │   ├── PRD.Quote-Request-List.html       # 桌面端-报价申请列表
    │   ├── PRD.Quote-Request-Mobile.html     # 移动端-向导+详情
    │   ├── PRD.Quote-Request-Mobile-Select-Product.html # 移动端-产品选择器
    │   └── PRD.Quote-Request-List-Mobile.html# 移动端-列表
    ├── Database/                  # 产品主数据库（标准化后）
    ├── Matching Algorithm/        # 匹配算法核心模块
    ├── Pre-process/               # 商品名称归一化模块
    │   └── Product_Normalizer2.0/
    ├── Special Orders Process/    # 特殊客户订单预处理
    │   └── XGLL/
    ├── 上海德立安-报价数据.xlsx    # 历史报价数据
    ├── 上海德立安-采购数据.xlsx    # 历史采购数据
    └── uploads/                   # 运行时上传文件临时目录
```

---

## 系统整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI 应用 (main.py)                       │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ /api/    │  │ /api/    │  │ /api/    │  │ /api/            │ │
│  │ upload   │  │ match    │  │ quote    │  │ preprocess_match │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬──────────┘ │
│       │             │             │                  │           │
│  ┌────▼─────────────▼─────────────▼──────────────────▼────────┐ │
│  │                    Services 层                              │ │
│  │  file_parser │ matcher_service │ preprocess_service         │ │
│  │  quote_service │ procurement_service                        │ │
│  └────┬─────────────┬──────────────┬──────────────────────────┘ │
│       │             │              │                             │
│  ┌────▼────┐  ┌─────▼─────┐  ┌────▼─────────────────────────┐  │
│  │ Excel   │  │ Matching  │  │ Pre-process                  │  │
│  │ Parser  │  │ Algorithm │  │ ┌─ Normal (归一化)            │  │
│  │         │  │ (BM25+    │  │ └─ Special (香格里拉预处理)   │  │
│  │         │  │  Bigram)  │  │                               │  │
│  └─────────┘  └───────────┘  └──────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  StaticFiles: frontend/ (HTML 原型页面，同域挂载)          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

前端 HTML 通过 `API_BASE_URL = ''`（空字符串）与后端同域访问，无需 CORS 配置。

---

## 核心数据流

### 一体化上传→预处理→匹配→查价 流程

这是前端使用的核心接口 `POST /api/preprocess_match`，完整处理链路如下：

```
用户上传 Excel + customer_name
        │
        ▼
  ┌─────────────────┐
  │ 1. 文件保存      │  保存到 uploads/{task_id}.xlsx
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │ 2. Excel 解析    │  自动识别表头行、商品名称列
  │    (file_parser) │  支持多 Sheet 合并
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │ 3. 客户格式判定   │  基于文件内容特征（英文类目前缀 + 含中文
  │  (detect_processing│ + 末尾括号含中文），不依赖客户名
  │   _mode)         │
  └────────┬────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
  普通客户     特殊客户(香格里拉)
     │           │
     ▼           ▼
  ┌──────────┐ ┌────────────────────────────────────┐
  │归一化处理 │ │香格里拉专用预处理                     │
  │6步清洗   │ │ 繁体→简体(OpenCC)                    │
  │智能分词  │ │ 去除英文部分                          │
  │品牌识别  │ │ 定位中文起始(124个品类关键词)          │
  │规格提取  │ │ 去除品类前缀(最长匹配+保护逻辑)        │
  │属性提取  │ │ 去除储存类型(干货/冰鲜/急冻/常温)      │
  └────┬─────┘ │ 去除国家名(~200个)                   │
       │       │ 去除 PER PKT/BTL/BAG 等包装描述        │
       │       │ 括号内品牌加"牌"后缀                   │
       │       └────────────┬─────────────────────────┘
       │                    │
       ▼                    ▼
  ┌─────────────────────────────────────────────────┐
  │ 4. 产品匹配 (ProductMatcher)                     │
  │                                                   │
  │  a. 查询预处理: 品牌检测→归一化→分词→规格提取      │
  │     →品质等级属性词摘除(核心名提取)                 │
  │  b. 双路召回:                                     │
  │     - BM25 索引 (core_tokens) → top-200 候选      │
  │     - Bigram 索引 (core_name) → top-200 候选      │
  │     取并集                                        │
  │  c. 品牌过滤: 若查询含品牌，仅保留同品牌候选        │
  │     (候选不足5条时跳过过滤，防止过拟合)              │
  │  d. 多维度重排:                                    │
  │     base = BM25×0.6 + Bigram×0.4 (归一化)         │
  │     + spec_bonus   (规格匹配, 最高+0.5)            │
  │     + attr_bonus   (属性词匹配, 最高+0.15)         │
  │     + brand_bonus  (品牌匹配, +0.35)              │
  │     + bulk_bonus   (散称匹配, +0.3)               │
  │  e. 置信度评估 + 排序:                              │
  │     品牌0.25 + 规格0.25 + 核心名0.5(Dice系数)      │
  │     候选按置信度从高到低排序                         │
  └────────────────────┬────────────────────────────┘
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ 5. 查价                                          │
  │  - 报价数据: 按产品编码查历史报价                    │
  │    (优先匹配当前客户名称中的关键词)                   │
  │  - 采购数据: 按产品编码查历史采购价                   │
  └────────────────────┬────────────────────────────┘
                       ▼
  返回完整结果: raw_name, preprocessed_name, top_match,
  alternatives[], quote, procurement
```

---

## 预处理模块详解

### 普通客户预处理 (Product_Normalizer2.0)

位于 `Pre-process/Product_Normalizer2.0/normalizer/`，是一个完整的商品名称标准化管线。

#### 6步文本清洗 (normalize.py)

| 步骤 | 操作 | 示例 |
|------|------|------|
| step1 | 全角→半角，统一乘号(×→*)，去特殊字符，合并空格 | `金龙鱼 大豆油` → `金龙鱼 大豆油` |
| step2 | 重量单位归一化(kg/斤/两/磅/盎司→g)，体积(L→mL) | `2.5kg` → `2500g` |
| step2b | 长度单位归一化(厘米→cm，毫米→mm) | `30厘米` → `30cm` |
| step2c | 统一"克/G"→g | `500G` → `500g` |
| step3 | 包装归一化("20包/箱"→"20包 箱") | `1000g*12袋` → `1000g 12袋` |
| step4 | 去除品牌名+后缀("牌"/"品牌"/"公司"等) | `金龙鱼牌大豆油` → `大豆油` |
| step5 | 去括号但保留内容 | `(特级)` → `特级` |
| step6 | 统一称重术语(散装称重/散卖→散称) | `散装称重` → `散称` |

#### 智能分词器 (tokenizer.py)

5步分词管线，采用贪心+动态规划+jieba 三级策略：

1. **基础分词**：贪心左到右扫描，优先级：数字+单位 > 纯数字 > 品牌(首字索引加速，~100候选/6134品牌) > 规格词(完整匹配) > 中文连续 > 英文连续 > 单字符
2. **深度拆分**：对 ≥2字符的中文 token 用动态规划拆分，三维代价函数(残余字符数, -最大规格词长度, 词数)。DP 失败时回退 jieba
3. **合并数字+单位**：`6000` + `g` → `6000g`
4. **去无意义 token**：`*`, `/`, `+`, `-` 等
5. **统一术语**：`称重` → `散称`

#### 品牌检测

双策略检测：
- **最高优先**：文本开头 "XX牌" 模式
- **常规**：Aho-Corasick 自动机（安装了 pyahocorasick 时）或线性扫描，取最长匹配

#### 词库

- `spec_words_dict.xlsx`：637 个规格词，17 个品类
- `detail_words_dict.xlsx`：属性/描述词库，分 11 类（品质等级、国家与地区、加工方式、处理状态等，按长度降序排列用于最长匹配）；其中「品质等级」用于核心名摘除
- `Brand_words_document.xlsx`：品牌词库（从 Excel 加载）

### 特殊客户预处理 (酒店投标格式 XGLL)

位于 `Special Orders Process/XGLL/process_orders_xgll.py`，专门处理酒店投标格式的中英双语订单描述（不限于香格里拉，凡「英文类目前缀 + 含中文 + 末尾括号含中文」的订单格式均适用）。

#### 6步处理管线

```
原始: "SNACKS MAGIC CHILI (HUANG FEI HONG) 308GM DR CHN 小食 香脆椒 (黄飞红) 308GM 干货 中国 (...)"

Step 1 - 提取中文部分: 繁体→简体(OpenCC t2s)，定位中文起始位置
Step 2 - 去后缀: 去除储存类型(干货)和国家(中国)
Step 3 - 去品类: 去除"小食"前缀(124个品类最长匹配，含保护逻辑)
Step 4 - 去包装: 去除 PER PKT/BTL/BAG 等
Step 5 - 加品牌后缀: 括号内品牌加"牌" → "(黄飞红牌)"
Step 6 - 清理空格

结果: "香脆椒 (黄飞红牌) 308GM"
```

内置数据：124 个品类关键词（含繁体变体）、~200 个国家名、4 种储存类型。

---

## 匹配算法详解

位于 `Matching Algorithm/matcher.py`，实现 **两阶段检索+多维度重排** 的产品匹配引擎。

### 数据库

使用 `Database/RSM_723_normalized_*.xlsx`（最新日期文件），约 32,514 条标准化产品。每条记录包含归一化后的名称、分词结果（JSON）、品牌、规格、核心名称、属性词等预处理字段。

### 索引构建

启动时构建两个索引：

**BM25 索引** (BM25Index)：
- 基于 `core_tokens`（归一化后的分词列表）构建倒排索引
- 标准 IDF 公式：`log((N - df + 0.5) / (df + 0.5) + 1)`
- 输入查询分词列表，返回所有匹配文档的 BM25 分数

**Bigram 索引** (BigramIndex)：
- 基于 `core_name`（去除品牌/规格后的核心名称）构建字符 2-gram 倒排索引
- 计算查询与候选的 Jaccard 相似度
- 用于召回 top-200 候选

### 检索与重排

**双路召回**：BM25 和 Bigram 各召回 top-200，取并集（~500 条候选）。

**品牌过滤**：若查询检测到品牌，仅保留同品牌候选。若同品牌候选不足 5 条，则跳过过滤（避免过度过滤导致漏匹配）。

**多维度重排**：

```
final_score = base_score
            + spec_bonus      # 规格匹配 (最高 +0.5)
            + attr_bonus      # 属性词匹配 (最高 +0.15)
            + brand_bonus     # 品牌匹配 (+0.35)
            + bulk_bonus      # 散称匹配 (+0.3)

其中 base_score = BM25_norm × 0.6 + Bigram_norm × 0.4
```

**规格相似度** (_spec_similarity)：提取数字+单位，完全匹配 +0.5，仅数字匹配 +0.4，不匹配 -0.1。

### 置信度评估 (compute_confidence)

候选排序依据（0-1 置信度），三个加权维度：

| 维度 | 权重 | 评估方式 |
|------|------|---------|
| 品牌 | 0.25 | 双方都无品牌时**不参与**；订单有品牌、候选无品牌 0.1；品牌匹配（互相包含）1.0；不一致 0.0 |
| 规格 | 0.25 | 仅订单有规格时参与；数值+单位匹配 1.0，数字匹配（单位不同）0.7，数值不一致 0.5（中性） |
| 核心名 | 0.5 | 字符 bigram 的 Dice 系数：`2×\|交集\| / (\|A\|+\|B\|)`，0~1 相似度 |

候选按**置信度**从高到低排序（原按召回重排得分 score 排序，已改为按置信度）。前端「匹配相似度」列只展示「综合分」（即置信度百分比）。

---

## API 接口

### POST /api/preprocess_match（核心接口）

前端上传 Excel 时调用的一体化接口，自动完成解析→预处理→匹配→查价全流程。

**请求**：`multipart/form-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | Excel 文件 (.xlsx/.xls) |
| customer_name | string | 客户名称（用于报价优先匹配，不用于特殊客户判定） |
| top_n | int | 返回候选数量，默认 10 |

**响应**：

```json
{
  "task_id": "uuid-string",
  "filename": "客户询价单.xlsx",
  "customer_name": "香格里拉酒店",
  "is_special": true,
  "special_label": "香格里拉",
  "total": 25,
  "results": [
    {
      "index": 0,
      "raw_name": "原始商品名",
      "preprocessed_name": "预处理后的名称",
      "preprocess_method": "special_xgll 或 normal",
      "top_match": {
        "product_code": "P001",
        "product_name": "标准产品名",
        "confidence": 0.85,
        "score": 12.5,
        "detected_brand": "金龙鱼",
        "normalized_spec": "5L×4",
        "core_name": "大豆油",
        "attributes": ["一级", "精炼"],
        "cat1": "米面油",
        "unit": "箱",
        "is_yihai": "是",
        "brand": "金龙鱼",
        "spec": "5L×4"
      },
      "alternatives": [...],
      "quote": {
        "product_name": "...",
        "unit_price": 268.00,
        "unit_price_without_tax": 237.17,
        "purchase_price": 220.00,
        "tax_rate": "13%",
        "customer_name": "...",
        "quote_time": "2026-03-15"
      },
      "procurement": {
        "procurement_price": 215.00,
        "supplier_name": "...",
        "start_time": "2026-01-01",
        "end_time": "2026-12-31"
      }
    }
  ]
}
```

### POST /api/select_alternative

用户在前端切换匹配候选时调用，重新查价。

**请求**：`application/json`

```json
{
  "task_id": "uuid-string",
  "item_index": 0,
  "selected_code": "P002"
}
```

**响应**：返回新候选的报价和采购数据。

### POST /api/upload

文件上传（分步模式），返回解析后的商品列表或 Sheet/列选择信息。

### POST /api/upload/select

用户手动选择 Sheet 和列后重新解析。

### POST /api/match

对已解析的商品列表执行批量匹配。

### GET /api/health

健康检查，返回 `{"status": "ok"}`。

### GET /api/debug/info

调试信息，返回各目录和文件的存在状态，用于排查部署问题。

---

## 前端原型页面

### 桌面端

#### 新增报价申请 (PRD.Quote-Request-New.html)

两步向导：

**Step 1 - 基础信息**：运营公司、经销商（自动带出）、报价类型（常规/临采/临客询价）、客户渠道、客户类型、客户名称（多选或临时客户手填）、项目点（多选）、报价标题（自动生成）、起止日期、客户报价单上传区。

**Step 2 - 品类与基准价**：Step 1 摘要折叠、9 大品类复选框、品类×采购基准价模式矩阵（市调价格/参考现客户价格/网站价格/采购价格）、产品明细表（支持文件导入自动对品、产品选择器弹窗、手动录入）、毛利汇总。

#### 报价申请详情 (PRD.Quote-Request-Detail.html)

接收向导数据后展示完整详情。包含：
- 状态栏（单号、单据状态、OA状态、上下单切换）
- 基础信息区（新建时可编辑）
- 品类与基准价区（品类×基准价矩阵、毛利区间、应用范围）
- 产品明细表（28列完整数据，支持行内编辑、产品选择器、导入匹配调整弹窗、批量操作、筛选、分页）
- 毛利汇总（5维度：益海直送、益海仓配、非益海直送、非益海仓配、合计）

**单据状态机**：

```
新建 ──提交──▶ 采购待确认 ──采购确认──▶ 销售待确认 ──销售确认──▶ 已审核
 │                  │                       │
 ├─作废(终止)      └─退回→新建             └─退回→采购待确认
```

#### 报价申请列表 (PRD.Quote-Request-List.html)

搜索筛选列表页，7 个默认筛选 + 5 个展开条件，支持分页（10/20/50条），点击单据跳转详情。

### 移动端

#### 向导+详情 (PRD.Quote-Request-Mobile.html)

375px 手机模拟器预览，合并向导和详情页。特色：
- 手机外框（听筒、侧键）
- 产品选择器跳转为独立页面（非弹窗）
- 草稿自动保存/恢复（sessionStorage）
- 折叠式明细卡片

#### 产品选择器 (PRD.Quote-Request-Mobile-Select-Product.html)

分栏布局（左侧品类 + 右侧产品列表），通过 sessionStorage 传递上下文和选择结果。

#### 列表 (PRD.Quote-Request-List-Mobile.html)

卡片式列表，顶部搜索（280ms 防抖模糊匹配），底部筛选面板（上滑弹出），无限滚动加载（每批20条），右下角悬浮新增按钮。

### 页面间数据传递

| 场景 | 传递方式 |
|------|---------|
| 向导→详情(桌面) | URL 参数 + `sessionStorage: quoteApplyWizardSeed:{id}` |
| 列表→详情 | URL 参数 `?id=...&docStatus=...` |
| 移动端草稿保存/恢复 | `sessionStorage: quoteApplyMobileDraft` |
| 移动端→产品选择器 | `sessionStorage: quoteProductPickerContext` |
| 产品选择器→移动端 | `sessionStorage: quoteProductPickerResult` |

---

## 部署到 Render

### 方式一：使用 render.yaml（推荐）

1. Render Dashboard → **New +** → **Blueprint**
2. 选择 `slaveofmatlab/plus-prototype-render` 仓库
3. 自动读取 `render.yaml` 创建 Web Service

### 方式二：手动创建 Web Service

1. **New +** → **Web Service**
2. 连接仓库，配置：
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

### 访问入口

- 首页自动跳转到 `/PRD.Quote-Request-New.html`
- API 健康检查：`/api/health`
- 调试信息：`/api/debug/info`

首次启动加载匹配算法和数据约需 30-60 秒。

---

## 依赖说明

| 依赖 | 用途 |
|------|------|
| fastapi + uvicorn | Web 框架 + ASGI 服务器 |
| pandas + openpyxl | 数据处理 + Excel 读写 |
| jieba | 中文分词（DP 失败时的回退方案） |
| opencc-python-reimplemented | 繁体→简体转换（香格里拉订单预处理） |
| python-calamine | 加速 Excel 读取（可选，回退 openpyxl） |
| pyahocorasick | 加速品牌检测（可选，回退线性扫描） |
| xlsxwriter | 加速 Excel 写入（可选，回退 openpyxl） |

---

## 本地开发

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 `http://localhost:8000` 即可打开原型页面。
