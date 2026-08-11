# PLUS 报价申请原型 + product_match 后端

本项目用于在 Render 部署 PLUS 报价申请 HTML 原型，并接入真实的 `product_match` 后端服务。

## 项目结构

```
plus-prototype-render/
├── README.md          # 本文件
├── render.yaml        # Render 部署配置
├── .gitignore
└── backend/           # 后端服务目录（Render 根目录）
    ├── requirements.txt
    ├── backend/
    │   └── main.py    # FastAPI 入口，同时挂载前端静态页面
    ├── frontend/      # PLUS 原型 HTML 页面
    │   ├── index.html
    │   ├── PRD.Quote-Request-New.html
    │   ├── PRD.Quote-Request-Detail.html
    │   ├── PRD.Quote-Request-List.html
    │   ├── PRD.Quote-Request-Mobile.html
    │   ├── PRD.Quote-Request-Mobile-Select-Product.html
    │   └── PRD.Quote-Request-List-Mobile.html
    ├── Database/                          # 匹配数据库
    ├── Matching Algorithm/                # 匹配算法
    ├── Pre-process/Product_Normalizer2.0/ # 产品归一化
    ├── Special Orders Process/XGLL/       # 特殊订单处理
    ├── 上海德立安-报价数据.xlsx
    └── 上海德立安-采购数据.xlsx
```

## 部署到 Render

### 方式一：使用 render.yaml（推荐）

1. 在 [Render Dashboard](https://dashboard.render.com/) 点击 **New +** → **Blueprint**。
2. 选择 `slaveofmatlab/plus-prototype-render` 仓库。
3. Render 会自动读取 `render.yaml` 创建 Web Service。
4. 等待部署完成，访问分配的 `.onrender.com` 域名即可。

### 方式二：手动创建 Web Service

1. 点击 **New +** → **Web Service**。
2. 选择 `slaveofmatlab/plus-prototype-render` 仓库（私有仓库需先授权）。
3. 填写配置：
   - **Name**: `plus-prototype-render`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. 点击 **Create Web Service** 等待部署。

## 访问入口

- 默认首页会自动跳转到：`/PRD.Quote-Request-New.html`
- API 健康检查：`/api/health`

## 关键说明

- 前端通过 `API_BASE_URL = ''` 与后端同域，无需额外配置 CORS。
- 所有数据文件（`Database/`、`Matching Algorithm/`、`Pre-process/`、`Special Orders Process/`、报价/采购 Excel）均已包含在仓库中，部署时会随代码一起拉取。
- 启动时会加载匹配算法、报价数据和采购数据，首次启动可能需要 30-60 秒。
