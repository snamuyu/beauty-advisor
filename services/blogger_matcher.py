"""
博主级匹配（计划 P2-13）。

把同一博主的视频人脸特征向量聚合为“博主特征”，
用户画像特征与之计算相似度，实现“找相似博主”通道。
"""

from sqlalchemy import select

from db.models import UserProfile, Video
from services.feature_vector import DIM_KEYS, vector_similarity


def build_blogger_vectors(db) -> dict:
    """按 uploader 聚合视频特征向量 → {uploader: {dims, face_shape, video_count}}。"""
    videos = db.scalars(
        select(Video).where(
            Video.uploader != "",
            Video.feature_vector.is_not(None),
        )
    ).all()
    groups: dict = {}
    for v in videos:
        dims = (v.feature_vector or {}).get("dims") or {}
        if not dims:
            continue
        g = groups.setdefault(v.uploader, {"sum": {}, "n": 0, "shapes": []})
        for k in DIM_KEYS:
            g["sum"][k] = g["sum"].get(k, 0) + float(dims.get(k, 0.5))
        g["n"] += 1
        shape = (v.feature_vector or {}).get("face_shape") or ""
        if shape:
            g["shapes"].append(shape)

    result = {}
    for name, g in groups.items():
        n = max(1, g["n"])
        shapes = g["shapes"]
        result[name] = {
            "dims": {k: g["sum"].get(k, 0) / n for k in DIM_KEYS},
            "face_shape": max(set(shapes), key=shapes.count) if shapes else "",
            "video_count": g["n"],
        }
    return result


def user_vector(profile: UserProfile | None) -> dict:
    """用户画像 → 特征向量（优先用已存 feature_vector，缺省从四维推导）。"""
    if profile is None:
        return {}
    if profile.feature_vector and profile.feature_vector.get("dims"):
        return profile.feature_vector
    return {
        "dims": {k: getattr(profile, k, 0.5) for k in DIM_KEYS},
        "face_shape": profile.face_shape or "",
    }


def match_blogger(profile: UserProfile | None, blogger_vectors: dict,
                  uploader: str) -> dict:
    """单个视频的上传者与用户画像的相似度。"""
    if not profile or not uploader:
        return {"similarity": 0.0, "distance": 1.0, "shape_hit": False}
    blogger = blogger_vectors.get(uploader)
    if not blogger:
        return {"similarity": 0.0, "distance": 1.0, "shape_hit": False}
    u = user_vector(profile)
    return vector_similarity(
        u.get("dims", {}), blogger["dims"],
        user_shape=u.get("face_shape", ""),
        other_shape=blogger.get("face_shape", ""),
    )
