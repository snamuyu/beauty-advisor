#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""填充 videos.tags（Day 3 数据准备 + 计划 P1-5）。

默认用关键词规则提取；加 --llm 用 Qwen-Max（ASR 文本 + VL 画面分析）打标，
LLM 失败时自动回退规则版。

用法：python tag_videos.py [--dry-run] [--force] [--llm] [--limit N]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 保证从 scripts/ 子目录运行时也能 import 项目根目录的包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from db.models import Video
from db.session import SessionLocal
from services import llm_tagger
from services.rule_tagger import extract_tags

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main():
    parser = argparse.ArgumentParser(description="填充 videos.tags（规则 / LLM）")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    parser.add_argument("--force", action="store_true", help="已打标也重新计算")
    parser.add_argument("--llm", action="store_true", help="用 Qwen-Max 打标（失败回退规则）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数（0=全部）")
    parser.add_argument("--delay", type=float, default=0.3, help="LLM 调用间隔秒数")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        videos = db.scalars(select(Video).order_by(Video.id)).all()
        if args.limit:
            videos = videos[: args.limit]
        updated = skipped = 0
        llm_ok = rule_fallback = failed = 0
        for v in videos:
            if v.tags and not args.force:
                skipped += 1
                continue
            tags = None
            source = "rule"
            if args.llm:
                try:
                    vl = _load_vl_analysis(v)
                    tags = llm_tagger.generate_tags(v.asr_text or "", vl)
                    source = "llm"
                    llm_ok += 1
                    time.sleep(args.delay)
                except Exception as exc:  # noqa: BLE001
                    print(f"    [回退规则] {v.video_id[:30]} LLM 失败：{exc}")
                    rule_fallback += 1
            if tags is None:
                tags = extract_tags(v.title, v.summary, v.asr_text)
            print(
                f"    [{'将打标' if args.dry_run else '打标'}|{source}] {v.video_id[:30]}"
                f" 脸型={tags['face_shapes']} 痛点={tags['pain_points']} 风格={tags['style']}"
            )
            if not args.dry_run:
                v.tags = tags
                updated += 1
        if not args.dry_run:
            db.commit()
        print(f"\n完成：更新 {updated}，跳过 {skipped}，"
              f"LLM 成功 {llm_ok}，回退规则 {rule_fallback}，失败 {failed}")
    finally:
        db.close()


def _load_vl_analysis(v: Video) -> str:
    """读取 VL 分析 JSON 的 analysis 字段，拼成文本供 LLM 参考。"""
    src = (v.vl_source or "").strip()
    if not src or not Path(src).is_file():
        return ""
    try:
        data = json.loads(Path(src).read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return ""
    analysis = data.get("analysis") or {}
    if not isinstance(analysis, dict):
        return ""
    parts = []
    for key in ("title", "summary", "steps", "tips", "conclusion"):
        val = analysis.get(key)
        if isinstance(val, list):
            parts.append("；".join(str(x) for x in val))
        elif val:
            parts.append(str(val))
    return "\n".join(parts)


if __name__ == "__main__":
    main()
