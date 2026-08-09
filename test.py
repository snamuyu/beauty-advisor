import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.llm_client import llm

# # 测试1：普通对话（关闭思考模式）
# result = llm.chat(
#     system_prompt="你是一个助手",
#     user_prompt="你好，请用一句话介绍自己",
#     thinking=False,
# )
# print("普通对话:", result)

# # 测试2：JSON输出
# result = llm.chat_json(
#     system_prompt="以JSON格式返回，包含name和age字段",
#     user_prompt="我叫小明，今年25岁",
#     thinking=False,
# )
# print("JSON输出:", result)

# # 测试3：思考模式
# result = llm.chat_json(
#     system_prompt="你是美妆师，以JSON格式返回style_label字段",
#     user_prompt="成熟度0.3，量感0.7，曲直度0.4，宽窄度0.6，请判断风格",
#     thinking=True,
# )
# print("思考模式:", result)
# test.py 追加内容
import base64
import io
from PIL import Image
from core.face_analyzer import FaceAnalyzer


# 测试4：人脸检测与风格诊断
print("\n--- 测试人脸检测与风格诊断 ---")
img_path = r"F:\looks\beauty-advisor\image\test.jpg"
try:
    # 用Pillow打开图片并转为jpg的base64
    img = Image.open(img_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode()

    analyzer = FaceAnalyzer()
    face_data = analyzer.detect(img_b64)
    
    if not face_data:
        print("未检测到人脸")
    else:
        landmarks = face_data.get("landmark72", [])
        print(f"检测到 {len(landmarks)} 个关键点")
        
        if landmarks:
            # 计算四维得分
            dims = analyzer.calc_dimensions(landmarks)
            print("四维得分:", dims)
            
           # 提取人脸属性（兼容百度API返回数组格式）
            gender_raw = face_data.get("gender", {})
            face_shape_raw = face_data.get("face_shape", {})

            # 如果是列表，取第一个元素
            if isinstance(gender_raw, list):
                gender_raw = gender_raw[0] if gender_raw else {}
            if isinstance(face_shape_raw, list):
                face_shape_raw = face_shape_raw[0] if face_shape_raw else {}

            face_info = {
                "age": face_data.get("age"),
                "gender": gender_raw.get("type") if isinstance(gender_raw, dict) else str(gender_raw),
                "face_shape": face_shape_raw.get("type") if isinstance(face_shape_raw, dict) else str(face_shape_raw)
            }
            print("人脸属性:", face_info)
            
            # 构造Prompt，调用本地千问生成报告
            system_prompt = """你是一位资深美妆风格顾问，擅长根据面部特征给出专业的个人风格诊断和妆造建议。
输出内容要具体、可落地，避免空泛的建议。请分点输出：
1. 风格定位（核心风格标签）
2. 妆容建议（底妆、眉眼、唇妆的具体技巧和色系）
3. 发型建议（长度、卷度、刘海）
4. 穿搭建议（风格、版型、颜色）
5. 避雷提醒（需要避开的妆造误区）"""

            user_prompt = f"""
人脸基础信息：
- 年龄：{face_info.get('age', '未知')}岁
- 性别：{face_info.get('gender', '未知')}
- 脸型：{face_info.get('face_shape', '未知')}

四维风格数据（0~1）：
- 成熟度：{dims.get('maturity', 0.5):.2f}（越高越成熟）
- 量感：{dims.get('volume', 0.5):.2f}（越高五官越大量感）
- 曲直度：{dims.get('curvature', 0.5):.2f}（越高越曲线柔和）
- 宽窄度：{dims.get('width', 0.5):.2f}（越高脸型越窄长）
"""
            print("\n正在调用本地千问生成报告...")
            report = llm.chat(system_prompt, user_prompt)
            
            print("\n" + "="*50)
            print("风格诊断报告")
            print("="*50)
            print(report)
            
except FileNotFoundError:
    print("请准备一张照片放在对应路径下再测试")
except Exception as e:
    print(f"处理出错: {e}")