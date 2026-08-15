#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三周 Day 3：基础匹配逻辑（无向量库，纯代码 + SQLite）。

根据用户画像（face_shape / pain_points / 风格 / 关键词）从 videos 表
找出最匹配的视频，按综合得分排序，返回 Top N。

得分构成：
  - 标签匹配：脸型命中 +30，痛点命中 +30（按比例），风格命中 +10
  - 关键词匹配：用户风格关键词在视频文本中的命中 +20（上限）
  - 分类相关：脸型 → 推荐分类映射命中 +15
  - 热度加权：点赞/收藏/播放的对数归一化，Day 4 会细化

用法（模块）：from services.matching_engine import recommend_videos
命令行：
  python services/matching_engine.py --profile 20260731_010812 --top 5
  python services/matching_engine.py --face heart --pain 显脸小 消肿 --top 5
"""

import argparse
import math
import os
import sys
from dataclasses import dataclass

# 保证无论以 python services/matching_engine.py 还是模块方式调用，
# 都能 import 到项目根目录下的 db 包和 config。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from db.models import UserProfile, Video
from db.session import SessionLocal
from services.ranking import hot_value

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# 百度人脸检测返回的英文脸型 → 中文标签
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

# 脸型 → 最相关的视频分类（领域经验映射）
FACE_SHAPE_CATEGORIES = {
    "心形脸": ["修容教程", "腮红教程", "约会妆教程", "唇妆教程"],
    "圆脸": ["修容教程", "腮红教程", "新手底妆"],
    "方脸": ["修容教程", "美妆教学"],
    "鹅蛋脸": ["化妆技巧", "美妆教学", "唇妆教程"],
    "长脸": ["修容教程", "化妆技巧"],
    "菱形脸": ["修容教程", "腮红教程"],
    "梨形脸": ["修容教程", "化妆技巧"],
}

# 风格标签 → 偏好的视频分类
STYLE_CATEGORY_HINTS = {
    "甜美": ["腮红教程", "约会妆教程", "唇妆教程"],
    "可爱": ["腮红教程", "约会妆教程", "唇妆教程"],
    "少女": ["腮红教程", "约会妆教程", "唇妆教程"],
    "御姐": ["修容教程", "美妆教学", "口红试色"],
    "成熟": ["修容教程", "美妆教学", "口红试色"],
    "欧美": ["修容教程", "美妆教学", "化妆技巧"],
    "混血": ["修容教程", "化妆技巧"],
    "韩系": ["新手底妆", "化妆技巧", "腮红教程"],
    "清透": ["新手底妆", "化妆技巧"],
    "复古": ["口红试色", "唇妆教程"],
    "日常": ["化妆技巧", "新手底妆"],
}


@dataclass
class VideoScore:
    total: float
    tag: float
    keyword: float
    category: float
    hot: float
    reasons: list


def _norm_face_shape(shape: str) -> str:
    shape = (shape or "").strip()
    return FACE_EN_TO_CN.get(shape.lower(), shape)


def _text_overlap(a: str, b: str) -> bool:
    """判断 a 与 b 是否有连续两字的重叠（中文风格词匹配用）。"""
    if not a or not b:
        return False
    a = a.replace(" ", "")
    b = b.replace(" ", "")
    return any(a[i : i + 2] in b for i in range(len(a) - 1) if a[i : i + 2].strip())


def _video_text(v: Video) -> str:
    """用于关键词命中的视频文本窗口。"""
    parts = [v.title or "", v.summary or ""]
    parts += list(v.steps or [])
    parts += list(v.tips or [])
    parts += list(v.keywords or [])
    parts.append((v.asr_text or "")[:8000])
    return " ".join(parts)


def score_video(v: Video, profile: UserProfile | None = None,
                face_shape: str = "", pain_points: list | None = None,
                style_tag: str = "", keywords: list | None = None,
                hot_weight: float = 0.3) -> VideoScore:
    """计算单个视频与用户画像的匹配得分。"""
    reasons: list[str] = []
    tags = v.tags or {}
    face_cn = _norm_face_shape(face_shape or (profile.face_shape if profile else ""))
    pains = list(pain_points or (profile.pain_points if profile else []) or [])
    style = style_tag or (profile.style_tag if profile else "") or ""
    kws = list(keywords or (profile.keywords if profile else []) or [])

    # 1. 标签匹配（最高权重）
    tag = 0.0
    video_faces = tags.get("face_shapes") or []
    if face_cn and face_cn in video_faces:
        tag += 30
        reasons.append(f"脸型匹配：{face_cn}")
    video_pains = tags.get("pain_points") or []
    if pains and video_pains:
        hit = [p for p in pains if p in video_pains]
        tag += 30 * len(hit) / len(pains)
        if hit:
            reasons.append("痛点匹配：" + "、".join(hit))
    video_styles = tags.get("style") or []
    if style and any(_text_overlap(style, s) for s in video_styles):
        tag += 10
        reasons.append(f"风格匹配：{style} → {video_styles}")

    # 2. 关键词匹配（用户关键词命中视频文本）
    keyword = 0.0
    haystack = _video_text(v)
    if kws:
        hit_kws = [k for k in kws if k and k in haystack]
        keyword = min(20.0, 10.0 * len(hit_kws))
        if hit_kws:
            reasons.append("关键词命中：" + "、".join(hit_kws))

    # 3. 分类相关（脸型 + 风格 → 分类映射）
    category = 0.0
    cat_hits = set()
    if face_cn:
        cat_hits |= set(FACE_SHAPE_CATEGORIES.get(face_cn, [])) & set(v.categories or [])
    for token in STYLE_CATEGORY_HINTS:
        if style and token in style:
            cat_hits |= set(STYLE_CATEGORY_HINTS[token]) & set(v.categories or [])
    if cat_hits:
        category += 15.0
        reasons.append("分类相关：" + "、".join(sorted(cat_hits)))

    # 4. 热度加权（Day 4 细化，这里先给基础版）
    hot = 10.0 * hot_weight  # 热度满分
    return VideoScore(
        total=tag + keyword + category + hot,
        tag=tag,
        keyword=keyword,
        category=category,
        hot=hot,
        reasons=reasons,
    )


def recommend_videos(db, profile: UserProfile | None = None,
                     face_shape: str = "", pain_points: list | None = None,
                     style_tag: str = "", keywords: list | None = None,
                     top_n: int = 5, hot_weight: float = 0.3) -> list[dict]:
    """返回 Top N 匹配视频（每个包含得分明细与匹配理由）。"""
    videos = list(db.scalars(select(Video).order_by(Video.id)).all())
    if not videos:
        return []

    # 先算热度归一化
    hot_values = [hot_value(v) for v in videos]
    max_hot = max(hot_values) if hot_values else 1.0
    max_hot = max_hot or 1.0

    results = []
    for v, hv in zip(videos, hot_values):
        s = score_video(
            v, profile=profile,
            face_shape=face_shape, pain_points=pain_points,
            style_tag=style_tag, keywords=keywords,
            hot_weight=hot_weight,
        )
        hot_norm = (hv / max_hot) if max_hot else 0.0
        total = s.total - s.hot + hot_weight * 10.0 * hot_norm
        results.append({
            "video_id": v.video_id,
            "title": v.title,
            "categories": v.categories,
            "summary": v.summary,
            "url": v.source_url,
            "score": round(total, 2),
            "tag_score": round(s.tag, 1),
            "keyword_score": round(s.keyword, 1),
            "category_score": round(s.category, 1),
            "hot_score": round(hot_weight * 10.0 * hot_norm, 2),
            "tags": v.tags or {},
            "reasons": s.reasons,
        })

    results.sort(key=lambda r: -r["score"])
    return results[:top_n]


def main():
    parser = argparse.ArgumentParser(description="根据用户画像推荐 Top N 视频（Day 3）")
    parser.add_argument("--profile", default="", help="从 user_profiles 读取画像（record_id）")
    parser.add_argument("--face", default="", help="脸型（英文或中文，如 heart / 心形脸）")
    parser.add_argument("--pain", nargs="*", default=[], help="痛点，如 显脸小 消肿")
    parser.add_argument("--style", default="", help="风格标签，如 甜美灵动少女")
    parser.add_argument("--keywords", nargs="*", default=[], help="关键词")
    parser.add_argument("--top", type=int, default=5, help="返回条数")
    parser.add_argument("--hot-weight", type=float, default=0.3, help="热度权重 0~1")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        profile = None
        if args.profile:
            profile = db.scalar(
                select(UserProfile).where(UserProfile.record_id == args.profile)
            )
            if not profile:
                print(f"未找到画像：{args.profile}")
                return 1
            print(f"画像：{profile.style_tag} | 脸型 {profile.face_shape} | 关键词 {profile.keywords}")

        results = recommend_videos(
            db, profile=profile,
            face_shape=args.face, pain_points=args.pain,
            style_tag=args.style, keywords=args.keywords,
            top_n=args.top, hot_weight=args.hot_weight,
        )
        print(f"\nTop {len(results)} 匹配视频：")
        for i, r in enumerate(results, 1):
            print(f"\n{i}. [{r['score']}] {r['title']}")
            print(f"   分类：{'/'.join(r['categories'])} | URL：{r['url']}")
            print(f"   得分明细：标签 {r['tag_score']} + 关键词 {r['keyword_score']}"
                  f" + 分类 {r['category_score']} + 热度 {r['hot_score']}")
            print(f"   理由：{('；'.join(r['reasons']) or '暂无强匹配')}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
