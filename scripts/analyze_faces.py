"""
人脸特征向量提取（计划 P2-12）。

1. 视频：对 ASR 关键帧抽样做百度人脸检测，计算四维向量写入 videos.feature_vector
2. 用户画像：从 user_profiles 的 dimensions + face_shape 推导 feature_vector

用法：
  python scripts/analyze_faces.py                 # 全量（已算的跳过）
  python scripts/analyze_faces.py --force         # 强制重算
  python scripts/analyze_faces.py --limit 10      # 只处理前 N 条（测试）
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from core.face_analyzer import FaceAnalyzer
from db.models import UserProfile, Video
from db.session import SessionLocal
from services.feature_vector import DIM_KEYS, detect_frames_vector

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]
ASR_OUTPUT = ROOT.parent / "ASR 语音转文字" / "output"


def frames_dir_for(v: Video) -> Path:
    cat = (v.categories or [""])[0]
    return ASR_OUTPUT / cat / f"{v.video_id}_frames"


def main():
    parser = argparse.ArgumentParser(description="人脸特征向量提取（视频 + 用户）")
    parser.add_argument("--force", action="store_true", help="强制重算")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数（0=全部）")
    parser.add_argument("--max-frames", type=int, default=3, help="每个视频抽样帧数")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # 1) 用户画像向量（从 dimensions 推导）
        up_updated = 0
        for p in db.scalars(select(UserProfile)).all():
            if p.feature_vector and not args.force:
                continue
            p.feature_vector = {
                "dims": {k: getattr(p, k, 0.5) for k in DIM_KEYS},
                "face_shape": p.face_shape or "",
            }
            up_updated += 1
        db.commit()
        print(f"[用户画像] 已更新特征向量 {up_updated} 条")

        # 2) 视频关键帧人脸检测
        videos = db.scalars(
            select(Video)
            .where(Video.content_type == "video")
            .order_by(Video.id)
        ).all()
        if args.limit:
            videos = videos[: args.limit]

        analyzer = FaceAnalyzer()
        done = skipped = no_face = failed = 0
        for i, v in enumerate(videos, 1):
            if v.feature_vector and not args.force:
                skipped += 1
                continue
            vec = detect_frames_vector(frames_dir_for(v), analyzer, max_frames=args.max_frames)
            if vec:
                v.feature_vector = vec
                done += 1
            else:
                no_face += 1
            if i % 20 == 0 or i == len(videos):
                print(f"  进度 {i}/{len(videos)}：成功 {done}，无人脸 {no_face}，跳过 {skipped}")
        db.commit()
        print(f"\n[视频] 完成：写入 {done}，无人脸/失败 {no_face}，跳过已有 {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
