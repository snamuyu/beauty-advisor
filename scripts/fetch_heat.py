#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 B 站真实热度（点赞/收藏/播放）并更新 videos 表（Day 4 数据准备）。

数据来源：B站视频详情 API（https://api.bilibili.com/x/web-interface/view?bvid=...），
按 videos.source_url 里的 BV 号逐个查询，把 stat.like / stat.favorite / stat.view
写入 like_count / collect_count / play_count。

用法：
  python fetch_heat.py               # 全量更新
  python fetch_heat.py --dry-run     # 只预览，不写库
  python fetch_heat.py --delay 1.5   # 调整请求间隔（B站有频率限制）
"""

import argparse
import os
import re
import sys
import time

# 保证从 scripts/ 子目录运行时也能 import 项目根目录的包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from sqlalchemy import select

from db.models import Video
from db.session import SessionLocal

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

VIEW_API = "https://api.bilibili.com/x/web-interface/view"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

BVID_RE = re.compile(r"(BV[0-9A-Za-z]{10})")


def _bvid(url: str) -> str | None:
    m = BVID_RE.search(url or "")
    return m.group(1) if m else None


def fetch_stats(bvid: str, retries: int = 3) -> dict:
    """查询单个视频的播放/点赞/收藏/评论，带重试。"""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                VIEW_API, params={"bvid": bvid}, headers=HEADERS, timeout=15
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"code={data.get('code')} {data.get('message')}")
            stat = data["data"]["stat"]
            return {
                "play_count": int(stat.get("view", 0)),
                "like_count": int(stat.get("like", 0)),
                "collect_count": int(stat.get("favorite", 0)),
                "reply_count": int(stat.get("reply", 0)),
            }
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = 3 * attempt
            print(f"    [重试 {attempt}/{retries}] {bvid}: {exc}（{wait}s 后重试）")
            time.sleep(wait)
    raise RuntimeError(f"{bvid} 抓取失败：{last_err}")


def main():
    parser = argparse.ArgumentParser(description="抓取 B 站热度并更新数据库")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写库")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        videos = list(db.scalars(select(Video).order_by(Video.id)).all())
        todo = [(v, _bvid(v.source_url)) for v in videos]
        todo = [(v, b) for v, b in todo if b]
        skipped = len(videos) - len(todo)
        print(f"共 {len(videos)} 个视频，含 BV 号 {len(todo)} 个，跳过 {skipped} 个。")
        if args.dry_run:
            for v, bvid in todo:
                print(f"    [将查询] {bvid} | {v.title[:35]}")
            return 0

        ok = failed = 0
        for i, (v, bvid) in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {bvid} | {v.title[:35]} ...")
            try:
                stats = fetch_stats(bvid)
            except Exception as exc:  # noqa: BLE001
                print(f"    [失败] {exc}")
                failed += 1
                continue
            v.play_count = stats["play_count"]
            v.like_count = stats["like_count"]
            v.collect_count = stats["collect_count"]
            print(f"    [OK] 播放 {stats['play_count']} 点赞 {stats['like_count']} 收藏 {stats['collect_count']}")
            ok += 1
            time.sleep(args.delay)

        db.commit()
        print(f"\n完成：成功 {ok}，失败 {failed}。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
