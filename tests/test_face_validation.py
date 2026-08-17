"""人脸校验逻辑测试：模拟百度返回，验证非真实人脸（卡通/低置信/模糊）会被拒绝。"""

import sys
import unittest
from pathlib import Path
from unittest import mock

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.face_analyzer import FaceAnalyzer  # noqa: E402


def _face(**overrides):
    """构造一份“合格真人脸”的百度返回，可覆盖字段模拟异常场景。"""
    face = {
        "face_token": "test_token",
        "location": {"left": 10, "top": 10, "width": 100, "height": 100, "rotation": 0},
        "face_probability": 0.99,
        "angle": {"yaw": 0, "pitch": 0, "roll": 0},
        "face_type": [
            {"type": "human", "probability": 0.99},
            {"type": "cartoon", "probability": 0.01},
        ],
        "quality": {"blur": 0.1, "illumination": 150, "completeness": 1},
        "landmark72": [{"x": 1.0, "y": 1.0}] * 72,
        "age": {"value": 25, "probability": 0.9},
        "gender": {"type": "female", "probability": 0.98},
        "face_shape": {"type": "oval", "probability": 0.85},
    }
    face.update(overrides)
    return face


class FaceValidationTest(unittest.TestCase):
    def test_valid_human_face_passes(self):
        self.assertTrue(FaceAnalyzer._is_valid_human_face(_face()))

    def test_low_face_probability_rejected(self):
        self.assertFalse(
            FaceAnalyzer._is_valid_human_face(_face(face_probability=0.5))
        )

    def test_cartoon_face_rejected(self):
        """高达这类卡通/动漫脸：face_type 主类型是 cartoon。"""
        self.assertFalse(
            FaceAnalyzer._is_valid_human_face(
                _face(
                    face_type=[
                        {"type": "human", "probability": 0.01},
                        {"type": "cartoon", "probability": 0.99},
                    ]
                )
            )
        )

    def test_missing_face_type_rejected(self):
        self.assertFalse(FaceAnalyzer._is_valid_human_face(_face(face_type=[])))

    def test_blurry_face_rejected(self):
        self.assertFalse(
            FaceAnalyzer._is_valid_human_face(_face(quality={"blur": 0.9}))
        )


class DetectFlowTest(unittest.TestCase):
    """模拟 requests.post，验证 detect() 对非真实人脸返回空字典。"""

    @staticmethod
    def _fake_post(detect_response):
        def fake_post(url, **kwargs):
            if url == FaceAnalyzer.TOKEN_URL:
                return mock.Mock(json=lambda: {"access_token": "test_token"})
            return mock.Mock(json=lambda: detect_response)

        return fake_post

    def _new_analyzer(self):
        analyzer = object.__new__(FaceAnalyzer)
        analyzer.access_token = "test_token"
        return analyzer

    def test_detect_rejects_cartoon_face(self):
        detect_response = {
            "error_code": 0,
            "result": {
                "face_num": 1,
                "face_list": [
                    _face(
                        face_type=[
                            {"type": "human", "probability": 0.01},
                            {"type": "cartoon", "probability": 0.99},
                        ]
                    )
                ],
            },
        }
        with mock.patch("requests.post", side_effect=self._fake_post(detect_response)):
            self.assertEqual(self._new_analyzer().detect("base64data"), {})

    def test_detect_accepts_valid_face(self):
        detect_response = {
            "error_code": 0,
            "result": {"face_num": 1, "face_list": [_face()]},
        }
        with mock.patch("requests.post", side_effect=self._fake_post(detect_response)):
            face = self._new_analyzer().detect("base64data")
        self.assertEqual(face["face_token"], "test_token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
