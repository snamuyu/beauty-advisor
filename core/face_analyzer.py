# core/face_analyzer.py
import requests
import numpy as np
import logging
from config import (
    BAIDU_API_KEY,
    BAIDU_SECRET_KEY,
    FACE_MAX_BLUR,
    FACE_PROBABILITY_THRESHOLD,
    FACE_TYPE_THRESHOLD,
)

logger = logging.getLogger(__name__)

class FaceAnalyzer:
    """人脸检测与四维特征计算引擎"""

    DETECT_URL = "https://aip.baidubce.com/rest/2.0/face/v3/detect"
    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"

    def __init__(self):
        self.access_token = self._get_token()

    def _get_token(self):
        """获取百度AI的access_token"""
        params = {
            "grant_type": "client_credentials",
            "client_id": BAIDU_API_KEY,
            "client_secret": BAIDU_SECRET_KEY,
        }
        try:
            resp = requests.post(self.TOKEN_URL, params=params).json()
            return resp["access_token"]
        except Exception as e:
            logger.error(f"获取百度Token失败: {e}")
            raise

    def detect(self, image_base64: str) -> dict:
        """
        调用人脸检测，返回包含landmark和人脸属性的完整信息
        """
        params = {"access_token": self.access_token}
        data = {
            "image": image_base64,
            "image_type": "BASE64",
            "face_field": "landmark,age,gender,face_shape,face_type,quality",
            "max_face_num": 1,
        }
        resp = requests.post(self.DETECT_URL, params=params, data=data).json()

        if resp.get("error_code") != 0:
            logger.error(f"人脸检测失败: {resp.get('error_msg')}")
            return {}

        face_list = resp.get("result", {}).get("face_list", [])
        if not face_list:
            return {}

        # 只接受置信度达标的真实人脸，卡通脸/低置信/模糊图一律拒绝
        face = face_list[0]
        if not self._is_valid_human_face(face):
            logger.warning(
                "检测结果未通过真实人脸校验: face_probability=%s, face_type=%s, blur=%s",
                face.get("face_probability"),
                face.get("face_type"),
                (face.get("quality") or {}).get("blur"),
            )
            return {}
        return face

    @staticmethod
    def _is_valid_human_face(face: dict) -> bool:
        """校验是否为置信度达标的真实人脸，拒绝卡通脸/低置信/模糊图。"""
        # 1. 人脸置信度
        prob = face.get("face_probability")
        if prob is None or prob < FACE_PROBABILITY_THRESHOLD:
            return False

        # 2. 必须是真实人脸（human），卡通/高达这类 stylized 脸会判为 cartoon
        face_types = face.get("face_type") or []
        if not face_types:
            return False
        best_type = max(face_types, key=lambda t: t.get("probability", 0))
        if (
            best_type.get("type") != "human"
            or best_type.get("probability", 0) < FACE_TYPE_THRESHOLD
        ):
            return False

        # 3. 模糊度（0 清晰 ~ 1 模糊）
        quality = face.get("quality") or {}
        if quality.get("blur", 0) > FACE_MAX_BLUR:
            return False

        return True

    @staticmethod
    def calc_dimensions(landmarks: list) -> dict:
        """
        根据72点landmark计算四维得分
        """
        if not landmarks or len(landmarks) < 72:
            return {"maturity": 0.5, "volume": 0.5, "curvature": 0.5, "width": 0.5}

        # 将list转为numpy数组方便计算
        points = [np.array([p['x'], p['y']]) for p in landmarks]

        # 1. 成熟度：中庭比例
        brow = np.mean([points[21], points[22]], axis=0)
        nose_bottom = np.mean([points[31], points[32], points[33], points[34], points[35]], axis=0)
        chin = points[8]
        forehead = np.mean([points[0], points[16]], axis=0)

        mid_face = abs(nose_bottom[1] - brow[1])
        full_face = abs(chin[1] - forehead[1])
        mid_ratio = mid_face / full_face if full_face > 0 else 0.5
        maturity = np.clip(mid_ratio * 1.5, 0, 1)

        # 2. 量感：眼睛大小占比
        left_eye_w = abs(points[39][0] - points[36][0])
        face_w = abs(points[0][0] - points[16][0])
        eye_ratio = left_eye_w / face_w if face_w > 0 else 0.1
        volume = np.clip(eye_ratio / 0.2, 0, 1)

        # 3. 曲直度：下颌角度
        jaw_left = points[4]
        jaw_right = points[12]
        vec_l = jaw_left - chin
        vec_r = jaw_right - chin
        cos_angle = np.dot(vec_l, vec_r) / (np.linalg.norm(vec_l) * np.linalg.norm(vec_r) + 1e-8)
        jaw_angle = np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))
        curvature = np.clip((jaw_angle - 60) / 60, 0, 1)

        # 4. 宽窄度：面部长宽比
        face_h = abs(points[8][1] - forehead[1])
        width_ratio = face_h / face_w if face_w > 0 else 1.5
        width = np.clip((width_ratio - 1.0) / 0.8, 0, 1)

        return {
            "maturity": float(np.clip(maturity, 0, 1)),
            "volume": float(np.clip(volume, 0, 1)),
            "curvature": float(np.clip(curvature, 0, 1)),
            "width": float(np.clip(width, 0, 1)),
        }
