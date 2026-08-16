"""
LLM 视频打标（计划 P1-5）：用 Qwen-Max 从 ASR 文本 + VL 画面分析生成人群标签。

输出结构与 services/rule_tagger.py 一致：
    face_shapes / feature_tags / pain_points / style（列表）
    difficulty（列表）/ confidence（0-1）

调用失败抛异常，由调用方回退到规则打标。
"""

import json
import os
import re
from pathlib import Path

from openai import OpenAI

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_MODEL = "qwen-max"

TAG_SCHEMA = {
    "type": "object",
    "required": ["face_shapes", "feature_tags", "pain_points", "style", "difficulty", "confidence"],
    "properties": {
        "face_shapes": {
            "type": "array", "items": {"type": "string"},
            "description": "字幕明确提到的适用脸型，如圆脸/方圆脸/鹅蛋脸/长脸/方脸/心形脸/菱形脸/梨形脸；未明确提及时为空数组",
        },
        "feature_tags": {
            "type": "array", "items": {"type": "string"},
            "description": "适用的五官特征，如肿眼泡/低山根/短下巴/塌鼻梁/嘴凸",
        },
        "pain_points": {
            "type": "array", "items": {"type": "string"},
            "description": "该视频解决的痛点，如显脸小/消肿/放大双眼/遮瑕/显气色",
        },
        "style": {
            "type": "string",
            "description": "妆容风格，如日常通勤/韩系清透/欧美浓妆/甜美可爱/御姐成熟",
        },
        "difficulty": {
            "type": "string", "enum": ["beginner", "intermediate", "advanced"],
            "description": "上手难度",
        },
        "summary": {"type": "string", "description": "一句话总结核心内容"},
        "confidence": {"type": "number", "description": "0到1的置信度"},
    },
}

TAG_SCHEMA_BLOCK = json.dumps(TAG_SCHEMA, ensure_ascii=False, indent=2)

SYSTEM_PROMPT = (
    "你是一名专业的美妆视频内容分析师。根据视频的语音转写文本和画面分析，"
    "提取该视频适用的目标人群标签。要求：只提取内容中明确提到的特征和痛点，"
    "不要过度推断；face_shapes 未明确提及时返回空数组。"
    "pain_points 必须能在文本中找到对应表述（例如'嘴唇内侧不上色'、'口红沾牙'、"
    "'肿眼泡'、'塌鼻梁'），找不到具体表述就返回空数组，不要输出泛泛的美妆痛点。"
    "请严格按照以下 JSON Schema 输出 JSON 格式结果，字段名必须完全一致：\n"
    + TAG_SCHEMA_BLOCK
)


def load_api_key() -> str:
    """读取 DASHSCOPE_API_KEY：环境变量 > beauty-advisor/.env。"""
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("DASHSCOPE_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            return {}
    return {}


def _normalize(raw: dict) -> dict:
    """把 LLM 输出规整为与 rule_tagger 一致的形状。"""
    style = raw.get("style")
    if isinstance(style, list):
        style = style[0] if style else ""
    style = style or ""
    difficulty = raw.get("difficulty") or "intermediate"
    if isinstance(difficulty, list):
        difficulty = difficulty[0] if difficulty else "intermediate"
    feature_tags = raw.get("feature_tags") or raw.get("features") or raw.get("featureTags") or []
    return {
        "face_shapes": list(raw.get("face_shapes") or []),
        "feature_tags": list(feature_tags),
        "pain_points": list(raw.get("pain_points") or raw.get("painPoints") or []),
        "style": [style] if style else [],
        "difficulty": [difficulty] if difficulty else [],
        "summary": raw.get("summary") or "",
        "confidence": float(raw.get("confidence") or 0.0),
    }


def generate_tags(asr_text: str, vl_analysis: str = "", api_key: str = "") -> dict:
    """用 Qwen-Max 生成视频人群标签；失败抛异常。"""
    key = api_key or load_api_key()
    if not key:
        raise RuntimeError("未找到 DASHSCOPE_API_KEY（环境变量或 beauty-advisor/.env）")

    user_prompt = f"语音转写文本：\n\"\"\"\n{(asr_text or '')[:8000]}\n\"\"\""
    if vl_analysis:
        user_prompt += f"\n\n画面分析：\n\"\"\"\n{vl_analysis[:3000]}\n\"\"\""

    client = OpenAI(api_key=key, base_url=DASHSCOPE_BASE_URL)
    kwargs = {
        "model": DASHSCOPE_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    try:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "video_tags", "strict": True, "schema": TAG_SCHEMA},
        }
        resp = client.chat.completions.create(**kwargs)
        raw = _extract_json(resp.choices[0].message.content)
    except Exception:
        # 模型不支持 json_schema 时退回 json_object
        kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        raw = _extract_json(resp.choices[0].message.content)
    if not raw:
        raise RuntimeError("LLM 打标返回空内容")
    return _normalize(raw)
