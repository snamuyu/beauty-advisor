#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三周 Day 1：SQLAlchemy 数据模型。

依据 PRD 设计两张表：
  1. videos         视频元数据表（对应第二周生成的视频标签 JSON）
  2. user_profiles  用户画像表（对应第一周 /analyze 生成的风格诊断记录）

兼容 SQLite 与 MySQL：JSON 列在 SQLite 中存为 TEXT，在 MySQL 中存为 JSON。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的公共基类。"""


class Video(Base):
    """视频元数据表。

    数据来源：第二周 ASR+VL 融合分析产出（output_fusion/<分类>/<视频>.json），
    入库时由数据迁移脚本（Day 2）填充；热度字段供 Day 4 排序使用。
    """

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True,
        comment="视频唯一标识（文件名 stem 或 BV 号）",
    )
    title: Mapped[str] = mapped_column(String(500), default="", comment="视频标题")
    categories: Mapped[list] = mapped_column(
        JSON, default=list, comment="所属分类列表，如 ['修容教程']"
    )
    summary: Mapped[str] = mapped_column(Text, default="", comment="一句话简介")
    steps: Mapped[list] = mapped_column(JSON, default=list, comment="核心步骤列表")
    tips: Mapped[list] = mapped_column(JSON, default=list, comment="注意事项列表")
    keywords: Mapped[list] = mapped_column(JSON, default=list, comment="关键词列表")
    conclusion: Mapped[str] = mapped_column(Text, default="", comment="总结")
    tags: Mapped[dict] = mapped_column(
        JSON, default=dict,
        comment="适用人群标签：face_shapes/feature_tags/pain_points/style/difficulty/confidence",
    )
    asr_text: Mapped[str] = mapped_column(Text, default="", comment="Whisper 转写全文")
    asr_source: Mapped[str] = mapped_column(String(1000), default="", comment="转写文本文件路径")
    vl_source: Mapped[str] = mapped_column(String(1000), default="", comment="VL 分析 JSON 路径")
    fusion_source: Mapped[str] = mapped_column(String(1000), default="", comment="融合结果 JSON 路径")
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0, comment="视频时长（秒）")
    frames_count: Mapped[int] = mapped_column(Integer, default=0, comment="关键帧数量")
    like_count: Mapped[int] = mapped_column(Integer, default=0, comment="点赞数（热度权重）")
    collect_count: Mapped[int] = mapped_column(Integer, default=0, comment="收藏数（热度权重）")
    play_count: Mapped[int] = mapped_column(Integer, default=0, comment="播放数")
    source_url: Mapped[str] = mapped_column(String(1000), default="", comment="视频来源 URL")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class UserProfile(Base):
    """用户画像表。

    数据来源：第一周 /analyze 的风格诊断记录（history/<record_id>.json），
    同一条诊断记录（record_id）只会入库一次。
    """

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(64), default="anonymous", index=True, comment="用户标识"
    )
    record_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, comment="对应 history 诊断记录 id"
    )
    age: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年龄")
    gender: Mapped[str] = mapped_column(String(32), default="", comment="性别")
    face_shape: Mapped[str] = mapped_column(String(64), default="", comment="脸型")
    maturity: Mapped[float] = mapped_column(Float, default=0.5, comment="成熟度 0-1")
    volume: Mapped[float] = mapped_column(Float, default=0.5, comment="量感 0-1")
    curvature: Mapped[float] = mapped_column(Float, default=0.5, comment="曲直度 0-1")
    width: Mapped[float] = mapped_column(Float, default=0.5, comment="宽窄度 0-1")
    style_tag: Mapped[str] = mapped_column(String(128), default="", comment="风格标签")
    keywords: Mapped[list] = mapped_column(JSON, default=list, comment="风格关键词")
    pain_points: Mapped[list] = mapped_column(JSON, default=list, comment="需要修饰的痛点")
    positioning_reason: Mapped[str] = mapped_column(Text, default="", comment="风格定位理由")
    makeup_advice: Mapped[list] = mapped_column(JSON, default=list, comment="妆容建议列表")
    hair_advice: Mapped[dict] = mapped_column(JSON, default=dict, comment="发型建议")
    summary: Mapped[str] = mapped_column(Text, default="", comment="总结语")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
