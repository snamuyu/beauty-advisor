import os
import tempfile
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 从环境变量读取密钥，找不到时给出提示
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
BAIDU_API_KEY = os.getenv("BAIDU_API_KEY", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")

if not DASHSCOPE_API_KEY:
    raise ValueError("请在 .env 文件中配置 DASHSCOPE_API_KEY")

# ===== LLM 配置（从 .env 读取）=====
# provider: cloud（阿里云 DashScope，默认）或 local（本地 llama.cpp，复活 legacy 时用）
LLM_CONFIG = {
    "provider": os.getenv("LLM_PROVIDER", "cloud"),
    "cloud": {
        "api_key": os.getenv("LLM_API_KEY", ""),
        "base_url": os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model": os.getenv("LLM_MODEL", "qwen-max"),
    },
    "local": {
        "api_key": "not-needed",
        "base_url": os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8080/v1"),
        "model": os.getenv("LOCAL_LLM_MODEL", "qwen2.5"),
    },
}

# ===== 通用配置 =====
MAX_KEYFRAMES = 8
# Windows 下 /tmp 无效，改用系统临时目录
TEMP_DIR = os.path.join(tempfile.gettempdir(), "beauty-advisor")

# ===== 服务配置 =====
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# ===== 人脸检测校验阈值（防止卡通/非真实人脸蒙混通过）=====
# 人脸置信度下限，0~1，低于此值视为“不是人脸”
FACE_PROBABILITY_THRESHOLD = float(os.getenv("FACE_PROBABILITY_THRESHOLD", "0.8"))
# 真实人脸(face_type=human)判定的置信度下限
FACE_TYPE_THRESHOLD = float(os.getenv("FACE_TYPE_THRESHOLD", "0.8"))
# 人脸模糊度上限，0~1，越大越模糊
FACE_MAX_BLUR = float(os.getenv("FACE_MAX_BLUR", "0.7"))

# ===== 数据库配置 =====
# 默认 SQLite（MVP 推荐，无需安装任何数据库服务），数据库文件在 data/beauty_advisor.db
# 切换 MySQL：设置环境变量 DATABASE_URL，例如：
#   mysql+pymysql://root:password@127.0.0.1:3306/beauty_advisor?charset=utf8mb4
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "beauty_advisor.db").replace(os.sep, "/")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")
