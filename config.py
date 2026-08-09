import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

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