# core/video_tagger.py
import json
import logging
from llm_client import llm

logger = logging.getLogger(__name__)

TAGGER_SYSTEM_PROMPT = """你是一个专业的美妆视频内容分析师。
你的任务是根据视频字幕内容，提取该视频适用的目标人群标签。

请严格以JSON格式返回以下字段：
{
    "face_shapes": ["适用脸型，如'圆脸'、'方圆脸'、'鹅蛋脸'等，可多选"],
    "feature_tags": ["适用五官特征，如'肿眼泡'、'低山根'、'短下巴'等，可多选"],
    "pain_points": ["该视频解决的痛点，如'显脸小'、'消肿'、'放大双眼'等，可多选"],
    "style": "妆容风格，如'日常通勤'、'韩系清透'、'欧美浓妆'等",
    "difficulty": "难度等级：beginner/intermediate/advanced",
    "summary": "一句话总结该视频的核心内容",
    "confidence": 0.0到1.0的置信度
}

注意：
- 只提取字幕中明确提到的特征和痛点，不要过度推断
- 如果字幕中没有明确提及适用脸型，face_shapes 返回空数组
- confidence 反映你对标签准确性的信心"""


def generate_video_tags(asr_text: str, vl_analysis: str = "") -> dict:
    """
    根据ASR字幕文本（和可选的VL视觉分析结果），生成视频标签

    Args:
        asr_text: 视频字幕文本（Whisper转写结果）
        vl_analysis: 可选，Qwen-VL对关键帧的视觉分析文本

    Returns:
        结构化标签 dict
    """
    user_prompt = f"""请根据以下美妆视频的字幕内容，提取适用人群标签。

字幕内容：
\"\"\"
{asr_text}
\"\"\""""

    if vl_analysis:
        user_prompt += f"""

画面分析补充信息（由视觉模型提供）：
\"\"\"
{vl_analysis}
\"\"\""""

    result = llm.chat_json(
        system_prompt=TAGGER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        thinking=False,  # 标签提取是简单任务，关闭思考模式提速
    )

    if not result:
        logger.warning(f"视频标签生成失败，ASR文本长度: {len(asr_text)}")
        return _empty_tags()

    # 过滤低置信度标签
    if result.get("confidence", 0) < 0.3:
        logger.warning(f"标签置信度过低: {result.get('confidence')}")

    return result


def batch_generate_tags(video_scripts: list[dict]) -> list[dict]:
    """
    批量生成视频标签（供 Celery 异步任务调用）

    Args:
        video_scripts: [{"video_id": "BV1xx", "asr_text": "...", "vl_analysis": "..."}]

    Returns:
        带标签的视频列表
    """
    results = []
    for item in video_scripts:
        try:
            tags = generate_video_tags(
                asr_text=item["asr_text"],
                vl_analysis=item.get("vl_analysis", ""),
            )
            results.append({
                "video_id": item["video_id"],
                "tags": tags,
                "status": "success",
            })
        except Exception as e:
            logger.error(f"视频 {item['video_id']} 标签生成失败: {e}")
            results.append({
                "video_id": item["video_id"],
                "tags": _empty_tags(),
                "status": "error",
                "error": str(e),
            })
    return results


def _empty_tags() -> dict:
    return {
        "face_shapes": [],
        "feature_tags": [],
        "pain_points": [],
        "style": "",
        "difficulty": "",
        "summary": "",
        "confidence": 0.0,
    }
