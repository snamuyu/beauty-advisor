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
from services.blogger_matcher import build_blogger_vectors, match_blogger
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

# 四维特征（成熟度/量感/曲直度/宽窄度）→ 分类偏好（P0-3）
# 规则：(标识, 命中条件, 偏好分类, 理由)
DIMENSION_CATEGORY_HINTS = [
    ("maturity_low", lambda p: p.maturity < 0.4,
     ["腮红教程", "约会妆教程", "唇妆教程"], "成熟度低 → 甜美/少女系"),
    ("maturity_high", lambda p: p.maturity >= 0.7,
     ["修容教程", "美妆教学", "口红试色"], "成熟度高 → 御姐/成熟系"),
    ("curvature_high", lambda p: p.curvature > 0.6,
     ["修容教程", "美妆教学", "化妆技巧"], "曲直度高 → 立体/欧美系"),
    ("curvature_low", lambda p: p.curvature < 0.4,
     ["修容教程", "化妆技巧"], "曲直度低 → 硬朗轮廓系"),
    ("width_high", lambda p: p.width >= 0.7,
     ["修容教程", "美妆教学", "口红试色"], "宽窄度高 → 大气/御姐系"),
    ("volume_low", lambda p: p.volume < 0.4,
     ["新手底妆", "化妆技巧"], "量感低 → 清透自然系"),
]

# 分类别名归一化：把不同平台的同类内容（如小红书“口红试色”↔B站“唇妆教程”）映射到同一分类族，
# 让图文笔记也能参与匹配，避免推荐结果里全是 B 站视频。
CATEGORY_SYNONYMS = {
    "口红试色": ["唇妆教程"],
    "眼影画法": ["化妆技巧", "眼妆教程"],
    "眼妆教程": ["化妆技巧"],
    "新手化妆": ["新手底妆", "化妆技巧"],
    "日常妆容": ["化妆技巧"],
}


def _normalized_categories(categories) -> set:
    """把视频分类展开成含同义词的集合，便于跨平台匹配。"""
    cats = set(categories or [])
    for c in list(cats):
        cats.update(CATEGORY_SYNONYMS.get(c, []))
    return cats


def _platform_of(result: dict) -> str:
    """按链接判断内容平台，用于推荐列表的平台均衡。"""
    url = result.get("url") or ""
    if "xiaohongshu" in url:
        return "xhs"
    if "bilibili" in url:
        return "bili"
    return "other"


def _balance_platforms(results: list[dict], top_n: int) -> list[dict]:
    """平台多样性：纯分数排序容易让单一平台刷屏（库里小红书占 91%），
    限制单平台最多占约 60%，保证其他平台（有合格候选时）也有位置。"""
    if len(results) <= 1 or top_n <= 1:
        return results[:top_n]
    max_per_platform = max(1, math.ceil(top_n * 0.6))
    counts: dict[str, int] = {}
    final: list[dict] = []
    for result in results:
        platform = _platform_of(result)
        if counts.get(platform, 0) >= max_per_platform:
            continue
        counts[platform] = counts.get(platform, 0) + 1
        final.append(result)
        if len(final) >= top_n:
            break
    return final


# 匹配强度分级阈值（P0-4，0-1 归一化分数；可按数据质量调整）
STRONG_THRESHOLD = 0.45
MEDIUM_THRESHOLD = 0.25


@dataclass
class VideoScore:
    total: float
    tag: float
    keyword: float
    category: float
    dim: float
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
    parts += list(v.categories or [])
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
    video_cats = _normalized_categories(v.categories or [])
    face_cn = _norm_face_shape(face_shape or (profile.face_shape if profile else ""))
    pains = list(pain_points or (profile.pain_points if profile else []) or [])
    style = style_tag or (profile.style_tag if profile else "") or ""
    kws = list(keywords or (profile.keywords if profile else []) or [])

    # 1. 标签匹配（归一化到 0-1，满分 70）
    tag_raw = 0.0
    video_faces = tags.get("face_shapes") or []
    if face_cn and face_cn in video_faces:
        tag_raw += 30
        reasons.append(f"脸型匹配：{face_cn}")
    video_pains = tags.get("pain_points") or []
    if pains and video_pains:
        hit = [p for p in pains if p in video_pains]
        tag_raw += 30 * len(hit) / len(pains)
        if hit:
            reasons.append("痛点匹配：" + "、".join(hit))
    video_styles = tags.get("style") or []
    if style and any(_text_overlap(style, s) for s in video_styles):
        tag_raw += 10
        reasons.append(f"风格匹配：{style} → {video_styles}")
    tag = min(1.0, tag_raw / 70.0)

    # 2. 关键词匹配（归一化到 0-1，满分 20）
    haystack = _video_text(v)
    hit_kws: list = []
    if kws:
        hit_kws = [k for k in kws if k and k in haystack]
        if hit_kws:
            reasons.append("关键词命中：" + "、".join(hit_kws))
    keyword = min(1.0, (10.0 * len(hit_kws)) / 20.0)

    # 3. 分类相关（脸型 + 风格 → 分类映射，归一化到 0-1）
    cat_hits = set()
    if face_cn:
        cat_hits |= set(FACE_SHAPE_CATEGORIES.get(face_cn, [])) & video_cats
    for token in STYLE_CATEGORY_HINTS:
        if style and token in style:
            cat_hits |= set(STYLE_CATEGORY_HINTS[token]) & video_cats
    if cat_hits:
        reasons.append("分类相关：" + "、".join(sorted(cat_hits)))
    category = 1.0 if cat_hits else 0.0

    # 4. 四维特征参与匹配（P0-3）：命中偏好分类的规则越多，得分越高（满分 3 条封顶）
    dim_raw = 0
    if profile:
        for _name, cond, cats, reason in DIMENSION_CATEGORY_HINTS:
            if cond(profile) and set(cats) & video_cats:
                dim_raw += 1
                reasons.append(reason)
    dim = min(1.0, dim_raw / 3.0)

    # 5. 热度占位（0-1；推荐函数里按库内归一化后的 hot_norm 替换）
    hot = hot_weight
    relevance = 0.40 * tag + 0.25 * keyword + 0.20 * category + 0.15 * dim
    return VideoScore(
        total=(1 - hot_weight) * relevance + hot_weight,
        tag=tag,
        keyword=keyword,
        category=category,
        dim=dim,
        hot=hot,
        reasons=reasons,
    )


def recommend_videos(db, profile: UserProfile | None = None,
                     face_shape: str = "", pain_points: list | None = None,
                     style_tag: str = "", keywords: list | None = None,
                     top_n: int = 5, hot_weight: float = 0.3,
                     blogger_weight: float = 0.0) -> list[dict]:
    """返回 Top N 匹配视频（每个包含得分明细与匹配理由）。"""
    # P2-14 接口预留：博主相似度权重（P2-13 实现前恒为 0）
    blogger_weight = max(0.0, min(1.0, blogger_weight))
    relevance_weight = max(0.0, 1.0 - hot_weight - blogger_weight)
    videos = list(db.scalars(select(Video).order_by(Video.id)).all())
    if not videos:
        return []

    # P2-13：博主相似度通道（blogger_weight>0 时启用）
    blogger_map = build_blogger_vectors(db) if (profile and blogger_weight > 0) else {}

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
        relevance = 0.40 * s.tag + 0.25 * s.keyword + 0.20 * s.category + 0.15 * s.dim
        if relevance <= 0:
            continue  # P0-1：相关度为零的视频直接排除，热度不能“空降”
        hot_norm = (hv / max_hot) if max_hot else 0.0
        blogger_sim = 0.0
        blogger_uploader = ""
        if blogger_map:
            m = match_blogger(profile, blogger_map, v.uploader or "")
            blogger_sim = m["similarity"]
            if blogger_sim >= 0.55:
                blogger_uploader = v.uploader or ""
                s.reasons.append(
                    f"博主相似：{blogger_uploader}（脸型相似度 {blogger_sim * 100:.1f}%）"
                )
        total = (
            relevance_weight * relevance
            + hot_weight * hot_norm
            + blogger_weight * blogger_sim
        )
        if total >= STRONG_THRESHOLD:
            strength = "strong"
            strength_cn = "强匹配"
        elif total >= MEDIUM_THRESHOLD:
            strength = "medium"
            strength_cn = "一般"
        else:
            strength = "weak"
            strength_cn = "弱匹配"
        results.append({
            "video_id": v.video_id,
            "title": v.title,
            "categories": v.categories,
            "summary": v.summary,
            "url": v.source_url,
            "score": round(total, 2),
            "match_strength": strength,
            "match_strength_cn": strength_cn,
            "tag_score": round(s.tag, 2),
            "keyword_score": round(s.keyword, 2),
            "category_score": round(s.category, 2),
            "dim_score": round(s.dim, 2),
            "hot_score": round(hot_weight * hot_norm, 2),
            "blogger_score": round(blogger_weight * blogger_sim, 2),
            "blogger_similarity": round(blogger_sim, 3),
            "uploader": v.uploader or "",
            "tags": v.tags or {},
            "reasons": s.reasons,
        })

    results.sort(key=lambda r: -r["score"])
    return _balance_platforms(results, top_n)


def main():
    parser = argparse.ArgumentParser(description="根据用户画像推荐 Top N 视频（Day 3）")
    parser.add_argument("--profile", default="", help="从 user_profiles 读取画像（record_id）")
    parser.add_argument("--user-id", default="", help="从 user_profiles 读取画像（user_id，取最新一条）")
    parser.add_argument("--face", default="", help="脸型（英文或中文，如 heart / 心形脸）")
    parser.add_argument("--pain", nargs="*", default=[], help="痛点，如 显脸小 消肿")
    parser.add_argument("--style", default="", help="风格标签，如 甜美灵动少女")
    parser.add_argument("--keywords", nargs="*", default=[], help="关键词")
    parser.add_argument("--top", type=int, default=5, help="返回条数")
    parser.add_argument("--hot-weight", type=float, default=0.3, help="热度权重 0~1")
    parser.add_argument("--blogger-weight", type=float, default=0.0,
                        help="博主相似度权重 0~1（P2-13 预留，当前恒为 0）")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        profile = None
        if args.profile or args.user_id:
            stmt = (
                select(UserProfile).where(UserProfile.record_id == args.profile)
                if args.profile
                else select(UserProfile)
                .where(UserProfile.user_id == args.user_id)
                .order_by(UserProfile.id.desc())
            )
            profile = db.scalar(stmt)
            if not profile:
                print(f"未找到画像：{args.profile or args.user_id}")
                return 1
            print(f"画像（{profile.record_id}）：{profile.style_tag} | 脸型 {profile.face_shape} | 关键词 {profile.keywords}")

        results = recommend_videos(
            db, profile=profile,
            face_shape=args.face, pain_points=args.pain,
            style_tag=args.style, keywords=args.keywords,
            top_n=args.top, hot_weight=args.hot_weight,
            blogger_weight=args.blogger_weight,
        )
        print(f"\nTop {len(results)} 匹配视频：")
        for i, r in enumerate(results, 1):
            print(f"\n{i}. [{r['score']}] {r['title']}")
            print(f"   分类：{'/'.join(r['categories'])} | URL：{r['url']}")
            print(f"   匹配强度：{r['match_strength_cn']}（{r['match_strength']}）")
            print(f"   得分明细：标签 {r['tag_score']} + 关键词 {r['keyword_score']}"
                  f" + 分类 {r['category_score']} + 四维 {r['dim_score']}"
                  f" + 热度 {r['hot_score']}")
            print(f"   理由：{('；'.join(r['reasons']) or '暂无强匹配')}")
            if r["match_strength"] == "weak":
                print("   ⚠️ 弱匹配：该结果参考价值有限，建议结合人工判断")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
