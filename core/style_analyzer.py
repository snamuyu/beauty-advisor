# core/style_analyzer.py
import logging
from typing import Optional
from core.llm_client import llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位资深美妆造型师，拥有10年以上面部美学分析经验。
你的任务是根据用户的面部四维量化数据，精准分析其面部风格特征，并给出专业的化妆建议。

分析维度说明：
- 成熟度：0=幼态圆润（短中庭、圆眼、饱满苹果肌），1=成熟锐利（长中庭、狭长眼、骨骼感强）
- 量感：0=淡颜系（五官小巧留白多），1=浓颜系（五官大留白少）
- 曲直度：0=曲线柔和（圆脸、圆眼、弯眉），1=直线硬朗（方脸、锐角眼、平眉）
- 宽窄度：0=窄脸精致，1=宽脸大气

请严格以JSON格式返回以下字段：
{
    "style_label": "风格标签，如'甜酷风'、'清冷御姐'、'邻家甜妹'等",
    "face_shape": "几何脸型，如'方圆脸'、'鹅蛋脸'、'菱形脸'等",
    "strengths": ["面部优势1", "面部优势2", "面部优势3"],
    "makeup_tips": ["化妆建议1", "化妆建议2", "化妆建议3"],
    "pain_points": ["可能需要修饰的点1", "可能需要修饰的点2"],
    "reference_celebrities": ["风格参考明星1", "风格参考明星2"],
    "confidence": 0.85
}"""


def analyze_face_style(dimensions: dict) -> dict:
    """
    根据四维得分，调用本地千问进行风格分析

    Args:
        dimensions: {
            "maturity": 0.3,   # 成熟度 0-1
            "volume": 0.7,     # 量感 0-1
            "curvature": 0.4,  # 曲直度 0-1
            "width": 0.6       # 宽窄度 0-1
        }

    Returns:
        风格分析结果 dict
    """
    user_prompt = f"""请分析以下面部四维数据，给出风格定位和化妆建议：

- 成熟度：{dimensions['maturity']:.2f}
- 量感：{dimensions['volume']:.2f}
- 曲直度：{dimensions['curvature']:.2f}
- 宽窄度：{dimensions['width']:.2f}

请综合分析这四个维度的组合特征，给出精准的风格判断。"""

    result = llm.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        thinking=True,  # 风格分析需要推理，开启思考模式
    )

    if not result:
        logger.warning("风格分析返回空结果，使用降级规则匹配")
        return _fallback_rule_match(dimensions)

    return result


def _fallback_rule_match(dimensions: dict) -> dict:
    """降级方案：当本地千问不可用时，使用简单规则匹配"""
    maturity = dimensions["maturity"]
    volume = dimensions["volume"]
    curvature = dimensions["curvature"]
    width = dimensions["width"]

    if maturity < 0.4 and curvature < 0.4:
        style = "甜妹风"
    elif maturity > 0.6 and curvature > 0.6:
        style = "冷感御姐"
    elif maturity > 0.6 and volume > 0.6:
        style = "明艳大气"
    elif maturity < 0.4 and volume > 0.6:
        style = "混血感"
    else:
        style = "气质通勤"

    return {
        "style_label": style,
        "face_shape": "待AI分析",
        "strengths": ["待AI分析"],
        "makeup_tips": ["待AI分析"],
        "pain_points": [],
        "reference_celebrities": [],
        "confidence": 0.5,
    }