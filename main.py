from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from core.face_analyzer import FaceAnalyzer
from config import BAIDU_API_KEY, BAIDU_SECRET_KEY, LLM_CONFIG

import base64
import logging
import json
import os
from datetime import datetime

import openai

app = FastAPI(title="Beauty Advisor API", description="AI 个人风格诊断后端")
from fastapi.middleware.cors import CORSMiddleware

from api.recommend import router as recommend_router

# --- CORS 跨域支持 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源访问（开发阶段用 *，生产环境建议指定具体域名）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法 (POST, GET, etc.)
    allow_headers=["*"],  # 允许所有头部
)

# --- 配置日志 ---
LOG_DIR = "log"
os.makedirs(LOG_DIR, exist_ok=True)
# 默认用户名，后续接入用户系统后替换
CURRENT_USER = "anonymous"

# 生成日志文件名：用户名_时间.log
log_filename = f"{CURRENT_USER}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_filepath = os.path.join(LOG_DIR, log_filename)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_filepath, encoding="utf-8"),  # 写入文件
        logging.StreamHandler(),  # 同时输出到终端
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"日志文件已创建: {log_filepath}")

# logger = logging.getLogger(__name__)

# --- 初始化 FastAPI 应用 ---
# app = FastAPI(title="Beauty Advisor API", description="AI 个人风格诊断后端")
app.include_router(recommend_router)

# --- 初始化人脸分析器 ---
try:
    analyzer = FaceAnalyzer()
    logger.info("FaceAnalyzer 初始化成功")
except Exception as e:
    logger.error(f"FaceAnalyzer 初始化失败: {e}")
    raise e

# --- 配置千问大模型 ---
client = openai.OpenAI(
    api_key=LLM_CONFIG["cloud"]["api_key"],
    base_url=LLM_CONFIG["cloud"]["base_url"],
)

# --- 历史记录文件路径 ---
HISTORY_DIR = "history"
os.makedirs(HISTORY_DIR, exist_ok=True)

# --- 定义请求和响应的数据模型 ---
class ImageRequest(BaseModel):
    image_base64: str

class MakeupAdvice(BaseModel):
    area: str
    action: str
    reason: str

class HairAdvice(BaseModel):
    length: str
    curl: str
    bangs: str

class StyleReport(BaseModel):
    id: str
    timestamp: str
    face_info: dict
    dimensions: dict
    style_tag: str
    keywords: list
    celebrity_refs: list
    positioning_reason: str
    makeup_advice: list
    hair_advice: dict
    summary: str

# --- 定义风格分析的 Prompt（要求返回 JSON） ---
SYSTEM_PROMPT = """
你是一个专业的个人形象顾问。你的任务是根据用户提供的人脸检测数据和四维风格分值，生成一份详细、个性化且富有洞察力的风格诊断报告。

你必须严格按照以下 JSON 格式返回结果，不要包含任何其他内容：

{
  "style_tag": "一个精准且吸引人的风格标签，如'戏剧感甜酷少女'",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4"],
  "celebrity_refs": ["明星参考1", "明星参考2"],
  "positioning_reason": "结合年龄、脸型、四维分值，用通俗易懂的语言解释为什么她属于这个风格，200字以内",
  "makeup_advice": [
    {
      "area": "底妆",
      "action": "具体执行建议",
      "reason": "理由和避坑提示"
    },
    {
      "area": "眉眼",
      "action": "具体执行建议",
      "reason": "理由和避坑提示"
    },
    {
      "area": "唇妆",
      "action": "具体执行建议",
      "reason": "理由和避坑提示"
    }
  ],
  "hair_advice": {
    "length": "长度建议及原理",
    "curl": "卷度建议及原理",
    "bangs": "刘海建议及原理"
  },
  "summary": "一段鼓励性的总结语，像朋友一样温暖，100字以内"
}

注意：
- 建议必须结合用户的具体特征（脸型、四维分值）
- 语气专业、亲切、鼓励性
- 只返回 JSON，不要添加 markdown 代码块标记
"""

# --- 定义核心分析接口 ---
@app.post("/analyze", response_model=StyleReport)
async def analyze_style(request: ImageRequest):
    image_data = request.image_base64

    # 1. 人脸检测与四维计算
    logger.info("开始人脸检测...")
    face_data = analyzer.detect(image_data)
    if not face_data:
        raise HTTPException(status_code=400, detail="未检测到人脸或人脸检测失败")

    landmarks = face_data.get("landmark72", [])
    dimensions = analyzer.calc_dimensions(landmarks)
    logger.info(f"四维计算完成: {dimensions}")

    # 2. 构造人脸信息摘要
    face_info = {
        "age": face_data.get("age"),
        "gender": face_data.get("gender", {}).get("type"),
        "face_shape": face_data.get("face_shape", {}).get("type"),
    }

    # 3. 调用千问大模型生成风格报告
    logger.info("正在生成风格报告...")

    user_content = f"""
    请根据以下数据进行风格诊断：
    - 年龄: {face_info['age']}
    - 性别: {face_info['gender']}
    - 脸型: {face_info['face_shape']}
    - 四维风格分值: {dimensions}
    """

    try:
        response = client.chat.completions.create(
            model="qwen-max",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ]
        )
        raw_text = response.choices[0].message.content
        logger.info("风格报告生成成功")

        # 清理可能的 markdown 代码块标记
        raw_text = raw_text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        report_data = json.loads(raw_text)

    except json.JSONDecodeError as e:
        logger.error(f"大模型返回的 JSON 解析失败: {e}")
        logger.error(f"原始返回内容: {raw_text}")
        raise HTTPException(status_code=500, detail="风格报告格式异常，请重试")
    except Exception as e:
        logger.error(f"调用千问API失败: {e}")
        raise HTTPException(status_code=500, detail="风格报告生成失败")

    # 4. 生成唯一 ID 和时间戳
    record_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp = datetime.now().isoformat()

    # 5. 组装最终结果
    result = StyleReport(
        id=record_id,
        timestamp=timestamp,
        face_info=face_info,
        dimensions=dimensions,
        style_tag=report_data.get("style_tag", ""),
        keywords=report_data.get("keywords", []),
        celebrity_refs=report_data.get("celebrity_refs", []),
        positioning_reason=report_data.get("positioning_reason", ""),
        makeup_advice=report_data.get("makeup_advice", []),
        hair_advice=report_data.get("hair_advice", {}),
        summary=report_data.get("summary", ""),
    )

    # 6. 保存历史记录
    save_history(record_id, result.model_dump())
    logger.info(f"历史记录已保存: {record_id}")

    return result

# --- 保存历史记录 ---
def save_history(record_id: str, data: dict):
    filepath = os.path.join(HISTORY_DIR, f"{record_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- 查询历史记录列表 ---
@app.get("/history")
async def get_history():
    records = []
    for filename in sorted(os.listdir(HISTORY_DIR), reverse=True):
        if filename.endswith(".json"):
            filepath = os.path.join(HISTORY_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                record = json.load(f)
                records.append({
                    "id": record["id"],
                    "timestamp": record["timestamp"],
                    "style_tag": record["style_tag"],
                    "keywords": record["keywords"],
                })
    return {"total": len(records), "records": records}

# --- 查询单条历史记录 ---
@app.get("/history/{record_id}")
async def get_history_detail(record_id: str):
    filepath = os.path.join(HISTORY_DIR, f"{record_id}.json")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="记录不存在")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

# --- 根路径测试 ---
# @app.get("/")
# async def root():
#     return {"message": "Beauty Advisor API is running!"}
