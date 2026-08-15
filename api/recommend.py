#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三周 Day 5：/recommend 推荐接口。

接收用户画像 JSON，调用 matching_engine.recommend_videos，
返回 Top N 匹配视频（含得分明细与匹配理由）。

两种画像传入方式：
  1. record_id：从 user_profiles 表加载已保存的诊断画像
  2. 直接传画像字段：face_shape / pain_points / style_tag / keywords
"""

import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import UserProfile
from db.session import get_db
from services.matching_engine import recommend_videos

router = APIRouter(tags=["recommend"])


class RecommendRequest(BaseModel):
    record_id: str = Field(default="", description="user_profiles 表中的诊断记录 id")
    face_shape: str = Field(default="", description="脸型，如 heart / 心形脸")
    pain_points: list[str] = Field(default_factory=list, description="痛点列表")
    style_tag: str = Field(default="", description="风格标签")
    keywords: list[str] = Field(default_factory=list, description="关键词")
    top_n: int = Field(default=5, ge=1, le=20, description="返回条数")
    hot_weight: float = Field(default=0.3, ge=0.0, le=1.0, description="热度权重")


@router.post("/recommend")
def recommend(req: RecommendRequest, db: Session = Depends(get_db)):
    profile = None
    if req.record_id:
        profile = db.scalar(
            select(UserProfile).where(UserProfile.record_id == req.record_id)
        )
        if not profile:
            raise HTTPException(status_code=404, detail=f"画像记录不存在：{req.record_id}")

    has_direct = bool(
        req.face_shape or req.pain_points or req.style_tag or req.keywords
    )
    if not profile and not has_direct:
        raise HTTPException(
            status_code=400,
            detail="请提供 record_id，或至少填写 face_shape / pain_points / style_tag / keywords 之一",
        )

    results = recommend_videos(
        db,
        profile=profile,
        face_shape=req.face_shape,
        pain_points=req.pain_points,
        style_tag=req.style_tag,
        keywords=req.keywords,
        top_n=req.top_n,
        hot_weight=req.hot_weight,
    )

    used_profile = {
        "face_shape": req.face_shape or (profile.face_shape if profile else ""),
        "pain_points": req.pain_points or (profile.pain_points if profile else []),
        "style_tag": req.style_tag or (profile.style_tag if profile else ""),
        "keywords": req.keywords or (profile.keywords if profile else []),
    }
    return {
        "profile": used_profile,
        "top_n": len(results),
        "hot_weight": req.hot_weight,
        "results": results,
    }
