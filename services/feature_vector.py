"""
连续人脸特征向量（计划 P2-12/13）。

统一向量空间：[成熟度, 量感, 曲直度, 宽窄度]（四个 0-1 连续维度）+ 离散脸型。
- 用户端：由 user_profiles 的 dimensions + face_shape 推导
- 视频/博主端：对视频关键帧做百度人脸检测（72 点 landmark），
  用与用户相同的 calc_dimensions 计算四维，再按博主聚合

相似度：加权 RMS 距离（0-1 归一化）+ 脸型命中加成。
"""

import base64
import time
from pathlib import Path

import numpy as np

from core.face_analyzer import FaceAnalyzer

DIM_KEYS = ["maturity", "volume", "curvature", "width"]
DIM_WEIGHTS = {"maturity": 1.0, "volume": 1.0, "curvature": 1.2, "width": 1.0}

FACE_EN_TO_CN = {
    "heart": "心形脸",
    "square": "方脸",
    "oval": "鹅蛋脸",
    "round": "圆脸",
    "long": "长脸",
    "oblong": "长脸",
    "diamond": "菱形脸",
    "triangle": "梨形脸",
}


def normalize_shape(shape: str) -> str:
    """把英文/中文脸型统一为中文标签。"""
    shape = (shape or "").strip().lower()
    if not shape:
        return ""
    return FACE_EN_TO_CN.get(shape, shape)


def dims_to_vector(dims: dict) -> list[float]:
    """四维字典 → 向量列表（缺省 0.5）。"""
    return [float(dims.get(k, 0.5)) for k in DIM_KEYS]


def vector_similarity(user_dims: dict, other_dims: dict,
                      user_shape: str = "", other_shape: str = "") -> dict:
    """加权 RMS 相似度（0-1）+ 脸型命中加成。"""
    u = np.array(dims_to_vector(user_dims))
    v = np.array(dims_to_vector(other_dims))
    w = np.array([DIM_WEIGHTS[k] for k in DIM_KEYS], dtype=float)
    dist = float(np.sqrt(np.sum(w * (u - v) ** 2) / np.sum(w)))
    sim = max(0.0, 1.0 - dist)
    shape_hit = normalize_shape(user_shape) and normalize_shape(user_shape) == normalize_shape(other_shape)
    if shape_hit:
        sim = min(1.0, sim + 0.15)
    return {
        "similarity": round(sim, 3),
        "distance": round(dist, 3),
        "shape_hit": shape_hit,
    }


def landmarks_to_vector(landmarks: list, face_shape: str = "") -> dict:
    """百度 72 点 landmark → 四维向量 + 脸型。"""
    if not landmarks or len(landmarks) < 72:
        return {}
    dims = FaceAnalyzer.calc_dimensions(landmarks)
    dims = {k: float(np.clip(dims.get(k, 0.5), 0, 1)) for k in DIM_KEYS}
    return {"dims": dims, "face_shape": normalize_shape(face_shape)}


def detect_frames_vector(frames_dir: Path, analyzer: FaceAnalyzer,
                         max_frames: int = 4) -> dict | None:
    """对关键帧抽样做人脸检测，返回平均向量；无人脸返回 None。"""
    jpgs = sorted(frames_dir.glob("*.jpg")) if frames_dir.is_dir() else []
    if not jpgs:
        return None
    step = max(1, len(jpgs) // max_frames)
    picked = jpgs[::step][:max_frames]

    results = []
    for img in picked:
        for attempt in range(2):  # QPS 限流时重试一次
            try:
                b64 = base64.b64encode(img.read_bytes()).decode("ascii")
                face = analyzer.detect(b64)
                if not face:  # 百度返回错误（限流/无人脸）
                    time.sleep(1.5)
                    continue
                landmarks = face.get("landmark72") or face.get("landmark") or []
                shape = (
                    (face.get("face_shape") or {}).get("type", "")
                    if isinstance(face.get("face_shape"), dict)
                    else ""
                )
                vec = landmarks_to_vector(landmarks, shape)
                if vec:
                    results.append(vec)
                break
            except Exception:  # noqa: BLE001
                time.sleep(1.5)
                continue
        time.sleep(0.6)  # 百度免费接口 QPS 约 2 次/秒
    if not results:
        return None

    avg = {k: float(np.mean([r["dims"][k] for r in results])) for k in DIM_KEYS}
    shapes = [r["face_shape"] for r in results if r["face_shape"]]
    majority = max(set(shapes), key=shapes.count) if shapes else ""
    return {"dims": avg, "face_shape": majority, "frames_used": len(results)}
