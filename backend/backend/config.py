import os

# Demo 项目根目录（自动基于当前文件位置计算，支持迁移）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 匹配算法目录（迁移后放在项目根目录内）
MATCHING_ALGORITHM_DIR = os.path.join(PROJECT_ROOT, "Matching Algorithm")

# Pre-process 模块目录（归一化，迁移后放在项目根目录内）
PREPROCESS_DIR = os.path.join(PROJECT_ROOT, "Pre-process", "Product_Normalizer2.0")

# 数据库目录（迁移后放在项目根目录内）
DATABASE_DIR = os.path.join(PROJECT_ROOT, "Database")

# 报价数据文件
QUOTE_DATA_FILE = os.path.join(PROJECT_ROOT, "上海德立安-报价数据.xlsx")

# 采购数据文件
PROCUREMENT_DATA_FILE = os.path.join(PROJECT_ROOT, "上海德立安-采购数据.xlsx")

# 上传文件临时存储
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 后端服务配置
HOST = "0.0.0.0"
PORT = 8000
