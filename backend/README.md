# 报价建议 Demo - 迁移与使用指南

## 📦 项目简介

这是一个**完全自包含、可独立迁移**的报价建议系统，支持：
- Excel 询价单上传与自动解析
- 商品智能匹配（含置信度评分）
- 人工校正备选匹配
- 历史报价与采购价格查询
- 一键导出匹配结果

整个项目所有依赖（匹配算法、预处理模块、数据库、数据文件）均内置，复制文件夹即可运行。

---

##  快速启动（3 步）

### 第 1 步：安装后端依赖

```bash
cd "Demo-Price_Recommendation"
pip install -r requirements.txt
```

**说明：**
- 需要 Python 3.9+
- `requirements.txt` 包含所有必需的 Python 包
- 可选加速包（python-calamine、pyahocorasick）未安装时会自动回退，不影响功能

### 第 2 步：安装前端依赖

```bash
cd frontend
npm install
```

**说明：**
- 需要 Node.js 16+ 和 npm
- `package.json` 已声明所有前端依赖（React、Ant Design、Vite、xlsx 等）

### 第 3 步：启动服务

**终端 1 - 启动后端（FastAPI）：**
```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**终端 2 - 启动前端（Vite）：**
```bash
cd frontend
npm run dev
```

**访问：** http://localhost:3001

---

## 📁 项目结构

```
[Demo]-Price_Recommendation/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 应用入口
│   ├── config.py               # 路径配置（自动计算，支持迁移）
│   ├── state.py                # 任务状态管理
│   ├── routers/                # API 路由
│   │   ├── upload.py           # 文件上传接口
│   │   ├── match.py            # 匹配接口
│   │   └── quote.py            # 报价查询接口
│   └── services/               # 业务逻辑
│       ├── matcher_service.py  # 匹配算法封装
│       ├── file_parser.py      # Excel 解析
│       ├── quote_service.py    # 报价数据查询
│       └── procurement_service.py  # 采购数据查询
│
├── frontend/                   # React + Vite 前端
│   ├── src/
│   │   ├── App.tsx             # 主应用组件
│   │   ├── components/         # UI 组件
│   │   │   ├── FileUpload.tsx          # 文件上传
│   │   │   ├── MatchResultTable.tsx    # 匹配结果表格
│   │   │   └── ConfidenceFilter.tsx    # 置信度筛选
│   │   ├── api/client.ts       # API 客户端
│   │   └── types/index.ts      # TypeScript 类型定义
│   ├── package.json            # npm 依赖
│   ├── vite.config.ts          # Vite 配置（代理 /api → localhost:8000）
│   └── index.html              # 入口 HTML
│
├── Matching Algorithm/         # 匹配算法模块（不修改源码，直接调用）
│   ├── matcher.py              # ProductMatcher 核心类
│   ├── service.py              # 匹配器单例服务
│   ├── batch_match.py          # 批量匹配参考实现
│   ── app.py                  # Gradio 演示界面（可选）
│
├── Pre-process/                # 商品名称预处理模块
│   └── Product_Normalizer2.0/
│       ├── normalizer/
│       │   ├── main.py         # 归一化入口
│       │   ├── config.py       # 词库配置（自动计算路径）
│       │   └── ...
│       └── Spec_words/         # 规格词库、属性词库
│
├── Database/                   # 标准产品库
│   ├── RSM_723.xlsx            # 原始产品库
│   └── RSM_723_normalized_*.xlsx  # 预处理后的产品库（自动加载最新）
│
├── 上海德立安-报价数据.xlsx    # 历史报价数据（127 条记录）
├── 上海德立安-采购数据.xlsx    # 采购价格数据（269 条记录）
── uploads/                    # 上传文件临时存储（自动创建）
├── requirements.txt            # Python 依赖清单
└── README.md                   # 本文档
```

---

## 🔧 路径自适应机制

所有文件路径均基于 `__file__` 自动计算，**支持任意目录迁移**：

| 配置文件 | 关键代码 | 作用 |
|---------|---------|------|
| `backend/config.py` | `PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` | 计算项目根目录 |
| `Matching Algorithm/service.py` | `_DB_DIR = os.path.join(os.path.dirname(...), '..', 'Database')` | 定位数据库目录 |
| `Pre-process/.../config.py` | `os.path.join(os.path.dirname(...), '..', 'Spec_words', ...)` | 定位词库文件 |

**无需修改任何代码**，复制整个文件夹到新位置即可运行。

---

## ✅ 自包含性检查

- [x] **无绝对路径**：所有路径通过 `os.path.join()` + `__file__` 动态计算
- [x] **无外部依赖**：匹配算法、预处理模块、数据库均在项目内
- [x] **数据文件内置**：报价数据、采购数据、产品库随项目复制
- [x] **前端代理配置**：Vite 开发服务器自动代理 `/api` 到本地后端
- [x] **依赖声明完整**：`requirements.txt` 和 `package.json` 包含所有必需依赖

---

##  核心功能

### 1. 文件上传与解析
- 支持 Excel 文件（.xlsx）
- 自动识别表头和商品列
- 多 Sheet 支持，用户可手动选择

### 2. 商品智能匹配
- 调用现有匹配算法（BM25 + 2-gram 双路召回）
- 返回最佳匹配 + 备选列表
- 置信度评分（品牌 0.25 + 规格 0.25 + 核心名 bigram Dice 0.5，按参与维度自动归一化）

### 3. 人工校正
- 每条结果提供下拉框选择备选匹配
- 实时切换，自动更新报价信息

### 4. 置信度筛选
- 滑块调整置信度区间
- 实时过滤显示结果

### 5. 历史报价查询
- 根据确认的商品编码查找历史报价
- 展示：单价、采购价、税率、运营公司、客户名称、报价时间、有效期
- Popover 悬浮查看详情

### 6. 采购价格查询
- 根据商品编码查找采购协议价
- 展示：含税协议价、供应商、有效期
- Popover 悬浮查看详情

### 7. 有历史记录优先
- 点击按钮将有报价或采购历史的条目排到前面
- 再次点击恢复原始顺序

### 8. 一键导出
- 导出当前页面显示的完整表单（含用户手动更换后的匹配结果）
- 文件名格式：`{原始上传文件名}_报价建议.xlsx`
- 包含列：序号、询价商品名、标准商品名、标准商品编码、历史报价信息、历史采购信息

### 9. 列宽拖拽调整
- 表头右侧拖拽手柄调整列宽
- 适合长文本列（如询价商品名）完整显示

---

## 📋 依赖清单

### Python 后端（requirements.txt）

```txt
# Web 框架
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6

# 数据处理
pandas>=1.3.0
openpyxl>=3.0.0

# 匹配算法
jieba>=0.42.1

# 可选加速（未安装时自动回退）
python-calamine>=0.2.0      # 加速 Excel 读取
pyahocorasick>=2.0.0        # 加速品牌检测
xlsxwriter>=3.0.0           # 加速 Excel 写入
```

### Node.js 前端（package.json）

主要依赖：
- React 18
- Ant Design 5
- Vite 5
- axios
- xlsx（Excel 导出）
- react-resizable（列宽拖拽）

---

## ️ 注意事项

1. **端口占用**
   - 后端默认端口：8000
   - 前端默认端口：3000
   - 如被占用，修改 `backend/config.py` 中的 `PORT` 或 `frontend/vite.config.ts` 中的 `port`

2. **Python 版本**
   - 推荐 Python 3.9+
   - 确保 `pip` 可用

3. **Node.js 版本**
   - 推荐 Node 16+
   - 确保 `npm` 可用

4. **uploads 目录**
   - 首次启动后端时自动创建
   - 用于存储上传的 Excel 文件
   - 可定期清理旧文件

5. **浏览器兼容性**
   - 推荐使用 Chrome、Edge、Firefox 最新版
   - 确保启用 JavaScript

---

## 🐛 常见问题

1. **端口占用**
   - 后端默认端口：8000
   - 前端默认端口：3001（避免与其他项目冲突）
   - 如被占用，修改 `backend/config.py` 中的 `PORT` 或 `frontend/vite.config.ts` 中的 `port`

2. **Python 版本**
   - 推荐 Python 3.9+
   - 确保 `pip` 可用

3. **Node.js 版本**
   - 推荐 Node 16+
   - 确保 `npm` 可用

4. **uploads 目录**
   - 首次启动后端时自动创建
   - 用于存储上传的 Excel 文件
   - 可定期清理旧文件

5. **浏览器兼容性**
   - 推荐使用 Chrome、Edge、Firefox 最新版
   - 确保启用 JavaScript

---

## 🐛 常见问题

### Q1: 启动后提示找不到模块？

**A:** 确保在正确的目录下执行命令：
```bash
# 后端必须在 backend/ 目录外执行
cd Demo-Price_Recommendation
pip install -r requirements.txt

# 前端必须在 frontend/ 目录内执行
cd frontend
npm install
```

### Q2: 前端无法连接后端？

**A:** 
1. 检查后端是否在 8000 端口运行：访问 http://localhost:8000/api/health
2. 查看浏览器控制台是否有 CORS 错误
3. 确认 `vite.config.ts` 中代理配置正确

### Q3: 匹配结果为空？

**A:** 
1. 检查 `Database/` 目录下是否有 `RSM_723_normalized_*.xlsx` 文件
2. 查看后端日志是否有加载错误
3. 确认上传的 Excel 文件格式正确

### Q4: 置信度显示为 0%？

**A:** 已修复。确保使用最新代码，匹配流程包含 `compute_confidence()` 调用。

### Q5: "无历史记录"不显示？

**A:** 已修复。后端返回所有编码的查询结果（包括 null），前端正确区分三种状态。

### Q6: 导出文件名为何不是预期格式？

**A:** 确保上传的文件名不含特殊字符。导出文件名格式：`{原始上传文件名}_报价建议.xlsx`

---

## 📦 打包分发

如需将项目分发给他人：

1. **清理运行时文件**
   ```bash
   # 删除 Python 缓存
   rm -rf backend/__pycache__/
   rm -rf backend/services/__pycache__/
   rm -rf backend/routers/__pycache__/
   
   # 删除前端依赖（接收方需重新安装）
   rm -rf frontend/node_modules/
   
   # 删除上传文件
   rm -rf uploads/*
   ```

2. **保留必要文件**
   - 所有 `.py`、`.tsx`、`.ts`、`.json`、`.md` 文件
   - `Database/`、`Matching Algorithm/`、`Pre-process/` 目录
   - 数据文件（报价数据、采购数据）
   - `requirements.txt`、`package.json`

3. **提供启动脚本（可选）**
   创建 `start.bat`（Windows）或 `start.sh`（Linux/Mac）：
   ```bash
   # start.sh 示例
   #!/bin/bash
   echo "Starting backend..."
   cd backend
   python -m uvicorn main:app --reload --port 8000 &
   
   echo "Starting frontend..."
   cd ../frontend
   npm run dev
   ```

---

## 📞 技术支持

如遇问题，请检查：
1. Python 和 Node.js 版本是否符合要求
2. 所有依赖是否正确安装
3. 后端和前端是否都在运行
4. 浏览器控制台和后端日志是否有错误信息

---

## 📝 更新日志

### v1.0.0 (2026-08-04)
- ✅ 初始版本发布
- ✅ 完全自包含架构，支持任意目录迁移
- ✅ 文件上传、商品匹配、人工校正、置信度筛选
- ✅ 历史报价与采购价格查询
- ✅ 有历史记录优先筛选
- ✅ 一键导出 Excel
- ✅ 列宽拖拽调整
- ✅ 路径自适应机制
- ✅ 完整依赖声明与迁移文档
