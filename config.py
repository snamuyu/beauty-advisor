import os
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
LLM_CONFIG = {
    "cloud": {
        "api_key": os.getenv("LLM_API_KEY", ""),
        "base_url": os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    }
}

# ===== 通用配置 =====
MAX_KEYFRAMES = 8
TEMP_DIR = "/tmp/beauty-advisor"

# ===== 数据库配置（第三周 Day 1）=====
# 默认 SQLite（MVP 推荐，无需安装任何数据库服务），数据库文件在 data/beauty_advisor.db
# 切换 MySQL：设置环境变量 DATABASE_URL，例如：
#   mysql+pymysql://root:password@127.0.0.1:3306/beauty_advisor?charset=utf8mb4
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "beauty_advisor.db").replace(os.sep, "/")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")
