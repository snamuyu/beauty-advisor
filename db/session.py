#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库引擎与会话管理（第三周 Day 1）。

默认使用 SQLite（data/beauty_advisor.db）；设置 DATABASE_URL 环境变量
可切换到 MySQL，例如：
  mysql+pymysql://root:password@127.0.0.1:3306/beauty_advisor?charset=utf8mb4
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import DATABASE_URL


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


_connect_args = {"check_same_thread": False} if _is_sqlite(DATABASE_URL) else {}
_engine_options = {"pool_pre_ping": True} if not _is_sqlite(DATABASE_URL) else {}

# 确保 SQLite 的 data 目录存在
if _is_sqlite(DATABASE_URL) and DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL[len("sqlite:///"):]
    if db_path and not db_path.startswith(":memory:"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    **_engine_options,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db():
    """FastAPI 依赖：每个请求一个会话，用完自动关闭。"""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有表（已存在则跳过，不会破坏数据）。"""
    import db.models  # noqa: F401  确保模型已注册到 Base.metadata

    from db.models import Base

    Base.metadata.create_all(bind=engine)
