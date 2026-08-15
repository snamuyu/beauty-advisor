#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用规则标签填充 videos.tags（Day 3 数据准备）。

在 LLM 版 video_tagger 跑通之前，先用关键词规则从视频文本里提取
适用脸型/特征/痛点/风格/难度标签，写入数据库。

用法：python tag_videos.py [--dry-run] [--force]
"""

import argparse
import os
import sys

# 保证从 scripts/ 子目录运行时也能 import 项目根目录的包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from db.models import Video
from db.session import SessionLocal
from services.rule_tagger import extract_tags

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main():
    parser = argparse.ArgumentParser(description="规则标签填充 videos.tags")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    parser.add_argument("--force", action="store_true", help="已打标也重新计算")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        videos = db.scalars(select(Video).order_by(Video.id)).all()
        updated = skipped = 0
        for v in videos:
            if v.tags and not args.force:
                skipped += 1
                continue
            tags = extract_tags(v.title, v.summary, v.asr_text)
            print(
                f"    [{'将打标' if args.dry_run else '打标'}] {v.video_id[:30]}"
                f" 脸型={tags['face_shapes']} 痛点={tags['pain_points']} 风格={tags['style']}"
            )
            if not args.dry_run:
                v.tags = tags
                updated += 1
        if not args.dry_run:
            db.commit()
        print(f"\n完成：更新 {updated}，跳过（已有标签）{skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
