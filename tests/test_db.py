#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库模型自测：使用内存 SQLite 验证建表、插入、JSON 字段读写。

用法：python test_db.py
"""

import os
import sys

# 保证从 tests/ 子目录运行时也能 import 项目根目录的包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db.models import Base, UserProfile, Video

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        # 模拟第二周融合结果入库
        video = Video(
            video_id="nose_contour_tutorial",
            title="鼻子修容保姆级教学",
            categories=["修容教程"],
            summary="改善鼻头大、鼻翼肥的问题",
            steps=["保湿打底", "阴影上色", "提亮鼻翼", "定妆高光"],
            tips=["阴影颜色要浅", "晕染要柔和"],
            keywords=["修容", "鼻影"],
            conclusion="正确步骤可打造精致鼻型",
            tags={
                "face_shapes": ["圆脸", "方圆脸"],
                "feature_tags": ["塌鼻梁", "蒜头鼻"],
                "pain_points": ["显脸小", "缩小鼻翼"],
                "style": "日常通勤",
                "difficulty": "beginner",
                "confidence": 0.92,
            },
            like_count=12345,
            collect_count=6789,
            play_count=987654,
            duration_sec=720.5,
            frames_count=20,
        )
        db.add(video)

        # 模拟第一周 /analyze 诊断记录入库
        profile = UserProfile(
            user_id="anonymous",
            record_id="20260731_010812",
            age=22,
            gender="female",
            face_shape="heart",
            maturity=0.117,
            volume=1.0,
            curvature=0.761,
            width=1.0,
            style_tag="甜美灵动少女",
            keywords=["甜美", "灵动"],
            pain_points=["脸圆", "下巴短"],
            makeup_advice=[{"area": "底妆", "action": "轻薄气垫", "reason": "保持自然"}],
            hair_advice={"length": "中长发", "curl": "微卷", "bangs": "空气刘海"},
            summary="勇敢尝试不同造型",
        )
        db.add(profile)
        db.commit()

        # 查询验证
        v = db.scalar(select(Video).where(Video.video_id == "nose_contour_tutorial"))
        p = db.scalar(select(UserProfile).where(UserProfile.record_id == "20260731_010812"))

        assert v is not None and p is not None
        assert v.tags["pain_points"] == ["显脸小", "缩小鼻翼"]
        assert v.categories == ["修容教程"]
        assert p.style_tag == "甜美灵动少女"
        assert p.hair_advice["bangs"] == "空气刘海"
        assert p.makeup_advice[0]["area"] == "底妆"
        assert p.face_shape == "heart"

        print("模型自测通过 ✔")
        print(f"videos 行数：{db.query(Video).count()}")
        print(f"user_profiles 行数：{db.query(UserProfile).count()}")
        print(f"示例视频热度权重 like={v.like_count}, collect={v.collect_count}")


if __name__ == "__main__":
    main()
