"""FastAPI 应用入口"""
import sys
import os
import logging

# 自动将项目根目录加入路径（基于当前文件位置计算，支持迁移）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers import upload, match, quote, preprocess_match
from backend.services.matcher_service import get_matcher
from backend.services.quote_service import init_quote_data
from backend.services.procurement_service import init_procurement_data

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="报价建议 Demo", version="1.0.0")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(match.router, prefix="/api", tags=["match"])
app.include_router(quote.router, prefix="/api", tags=["quote"])
app.include_router(preprocess_match.router, prefix="/api", tags=["preprocess_match"])

# 挂载前端静态页面（部署到 Render 后与后端同域名，避免跨域）
frontend_dir = os.path.join(project_root, "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    logger.info(f"已挂载前端静态文件: {frontend_dir}")
else:
    logger.warning(f"未找到前端目录: {frontend_dir}")


@app.on_event("startup")
async def startup_event():
    logger.info("=== 报价建议 Demo 启动 ===")
    logger.info("正在初始化匹配算法...")
    try:
        get_matcher()
        logger.info("匹配算法初始化完成")
    except Exception as e:
        logger.error(f"匹配算法初始化失败: {e}")

    logger.info("正在加载报价数据...")
    try:
        init_quote_data()
        logger.info("报价数据加载完成")
    except Exception as e:
        logger.error(f"报价数据加载失败: {e}")

    logger.info("正在加载采购数据...")
    try:
        init_procurement_data()
        logger.info("采购数据加载完成")
    except Exception as e:
        logger.error(f"采购数据加载失败: {e}")

    logger.info("=== 服务就绪 ===")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "报价建议 Demo 运行中"}


@app.get("/api/debug/info")
async def debug_info():
    """调试信息：检查目录和文件是否可用"""
    from backend.config import PROJECT_ROOT, UPLOAD_DIR, QUOTE_DATA_FILE, PROCUREMENT_DATA_FILE, MATCHING_ALGORITHM_DIR, PREPROCESS_DIR, DATABASE_DIR
    import os
    
    info = {
        "project_root": PROJECT_ROOT,
        "upload_dir": UPLOAD_DIR,
        "upload_dir_exists": os.path.isdir(UPLOAD_DIR),
        "upload_dir_writable": os.access(UPLOAD_DIR, os.W_OK) if os.path.isdir(UPLOAD_DIR) else False,
        "files": {
            "quote_data": os.path.isfile(QUOTE_DATA_FILE),
            "procurement_data": os.path.isfile(PROCUREMENT_DATA_FILE),
        },
        "dirs": {
            "matching_algorithm": os.path.isdir(MATCHING_ALGORITHM_DIR),
            "preprocess": os.path.isdir(PREPROCESS_DIR),
            "database": os.path.isdir(DATABASE_DIR),
        }
    }
    
    # 检查 frontend 目录
    frontend_dir = os.path.join(PROJECT_ROOT, "frontend")
    info["frontend_dir"] = frontend_dir
    info["frontend_exists"] = os.path.isdir(frontend_dir)
    
    return info
