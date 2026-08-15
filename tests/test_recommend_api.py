#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""/recommend 接口测试（Day 5），位于 tests/ 目录。

前提：先启动 API（python -m uvicorn main:app --port 8000）。
用法：python test_recommend_api.py
"""

import sys

import requests

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE = "http://127.0.0.1:8000"


def show(title: str, payload: dict):
    resp = requests.post(f"{BASE}/recommend", json=payload, timeout=30)
    print(f"\n== {title} → HTTP {resp.status_code} ==")
    data = resp.json()
    if resp.status_code != 200:
        print(data)
        return
    p = data["profile"]
    print(f"画像：脸型 {p['face_shape']} | 风格 {p['style_tag']} | "
          f"痛点 {p['pain_points']} | 关键词 {p['keywords']}")
    for i, v in enumerate(data["results"], 1):
        print(f"  [{i}] score={v['score']} | {v['title']}")
        print(f"      理由：{'；'.join(v['reasons']) or '暂无强匹配'}")


def main():
    # 方式一：从 user_profiles 读取已保存画像
    show("按 record_id 推荐", {"record_id": "20260731_010812", "top_n": 5})

    # 方式二：直接传画像字段（UTF-8 中文）
    show("直接传画像字段", {
        "face_shape": "heart",
        "pain_points": ["显脸小", "消肿"],
        "style_tag": "甜美",
        "keywords": ["腮红", "少女"],
        "top_n": 3,
    })

    # 错误处理
    show("不存在的 record_id", {"record_id": "not_exist"})
    show("空画像", {"top_n": 3})


if __name__ == "__main__":
    main()
