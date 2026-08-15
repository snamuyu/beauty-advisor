#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三周 Day 4：热度加权排序算法。

输入视频列表，根据点赞数、收藏数、播放数加权打分，返回排序后的列表。

公式：
  原始热度  raw   = 点赞*1 + 收藏*3 + 播放*0.02
  热度得分  score = log1p(raw)           # 对数压缩，避免头部视频通吃
  归一化    norm  = score / 本批最高分    # 0~1，供与相关度得分融合

最终推荐分（与 Day 3 匹配相关度融合）：
  final = relevance + heat_weight * 10 * heat_norm

用法（模块）：from services.ranking import hot_value, rank_by_heat, combine_with_relevance
命令行：
  python services/ranking.py --top 5        # 按数据库真实热度排行
  python services/ranking.py --demo         # 用内存示例数据演示算法
"""

import argparse
import math
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from db.models import Video
from db.session import SessionLocal

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# 默认热度权重：收藏价值最高（推荐视频更看重收藏），播放权重很小
DEFAULT_HEAT_WEIGHTS = {"like": 1.0, "collect": 3.0, "play": 0.02}


@dataclass
class HeatScore:
    raw: float
    log: float
    norm: float


def hot_value(video: Video, weights: dict | None = None) -> float:
    """单个视频的对数热度值（未归一化）。"""
    w = weights or DEFAULT_HEAT_WEIGHTS
    raw = (
        (video.like_count or 0) * w["like"]
        + (video.collect_count or 0) * w["collect"]
        + (video.play_count or 0) * w["play"]
    )
    return math.log1p(raw)


def rank_by_heat(videos: list[Video], weights: dict | None = None,
                 top_n: int | None = None) -> list[dict]:
    """按热度加权打分排序，返回带明细的列表。"""
    if not videos:
        return []
    w = weights or DEFAULT_HEAT_WEIGHTS
    logs = [(v, hot_value(v, w)) for v in videos]
    logs.sort(key=lambda item: -item[1])
    max_log = logs[0][1] or 1.0

    results = []
    for v, log_score in logs:
        raw = (
            (v.like_count or 0) * w["like"]
            + (v.collect_count or 0) * w["collect"]
            + (v.play_count or 0) * w["play"]
        )
        results.append({
            "video_id": v.video_id,
            "title": v.title,
            "categories": v.categories,
            "like_count": v.like_count or 0,
            "collect_count": v.collect_count or 0,
            "play_count": v.play_count or 0,
            "heat_raw": round(raw, 1),
            "heat_log": round(log_score, 3),
            "heat_norm": round(log_score / max_log, 3),
        })
    return results[:top_n] if top_n else results


def combine_with_relevance(relevance: dict, videos: list[Video],
                           heat_weight: float = 0.3,
                           weights: dict | None = None) -> list[dict]:
    """把 Day 3 的相关度得分与 Day 4 的热度融合，得到最终排序。

    Args:
        relevance: {video_id: 相关度得分（0~100 量级）}
        videos:    候选视频列表
        heat_weight: 热度权重 0~1（默认 0.3，热度满分 3 分）
    """
    heat = rank_by_heat(videos, weights)
    heat_map = {item["video_id"]: item for item in heat}
    max_heat = max((item["heat_norm"] for item in heat), default=0.0)

    merged = []
    for v in videos:
        rel = relevance.get(v.video_id, 0.0)
        h = heat_map.get(v.video_id, {})
        final = rel + heat_weight * 10.0 * (h.get("heat_norm", 0.0) / (max_heat or 1.0))
        merged.append({
            "video_id": v.video_id,
            "title": v.title,
            "categories": v.categories,
            "url": v.source_url,
            "relevance": round(rel, 2),
            "heat_norm": h.get("heat_norm", 0.0),
            "final_score": round(final, 2),
        })
    merged.sort(key=lambda item: -item["final_score"])
    return merged


def _demo_videos() -> list[Video]:
    """构造带热度的内存示例数据，演示排序算法。"""
    data = [
        ("v1", "腮红教程", 120000, 30000, 3000000),
        ("v2", "唇妆教程", 50000, 8000, 900000),
        ("v3", "修容教程", 30000, 5000, 600000),
        ("v4", "美妆教学", 2000, 100, 50000),
        ("v5", "化妆技巧", 1000, 50, 30000),
    ]
    videos = []
    for vid, cat, like, collect, play in data:
        v = Video(video_id=vid, title=f"示例视频 {vid}", categories=[cat])
        v.like_count, v.collect_count, v.play_count = like, collect, play
        videos.append(v)
    return videos


def main():
    parser = argparse.ArgumentParser(description="热度加权排序（Day 4）")
    parser.add_argument("--top", type=int, default=0, help="返回条数（0=全部）")
    parser.add_argument("--demo", action="store_true", help="用内存示例数据演示")
    args = parser.parse_args()

    if args.demo:
        videos = _demo_videos()
        print("== 示例数据热度排行 ==")
        for r in rank_by_heat(videos, top_n=args.top or None):
            print(f"  {r['title']:<12} 赞{r['like_count']:>8} 藏{r['collect_count']:>6} "
                  f"播{r['play_count']:>9} raw={r['heat_raw']:>8.1f} norm={r['heat_norm']}")
        return 0

    db = SessionLocal()
    try:
        videos = list(db.scalars(select(Video).order_by(Video.id)).all())
        results = rank_by_heat(videos, top_n=args.top or None)
        print(f"== 数据库热度排行（共 {len(videos)} 个视频）==")
        for r in results:
            print(f"  {r['title'][:35]:<38} 赞{r['like_count']:>6} 藏{r['collect_count']:>6} "
                  f"播{r['play_count']:>9} norm={r['heat_norm']}")
        if all(r["like_count"] == 0 and r["collect_count"] == 0 for r in results):
            print("\n提示：当前点赞/收藏/播放均为 0，可先运行 python fetch_heat.py 抓取 B 站真实热度。")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
