#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三周 Day 1：建表脚本。

用法：
  python db/init_db.py             # 按 config.DATABASE_URL 建表（默认 SQLite）
  python db/init_db.py --url sqlite:///./data/test.db
  python db/init_db.py --url "mysql+pymysql://root:pass@127.0.0.1:3306/beauty_advisor?charset=utf8mb4"
  python db/init_db.py --echo      # 打印执行的 SQL
"""

import argparse
import os
import sys

# 保证无论以 python db/init_db.py 还是 python -m db.init_db 运行，
# 都能 import 到项目根目录下的 config 和 db 包。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 控制台默认 GBK，统一按 UTF-8 输出并容错
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main():
    parser = argparse.ArgumentParser(description="创建 beauty-advisor 数据库表")
    parser.add_argument("--url", default="", help="数据库连接串，覆盖 DATABASE_URL")
    parser.add_argument("--echo", action="store_true", help="打印建表 SQL")
    args = parser.parse_args()

    if args.url:
        from sqlalchemy import create_engine

        import db.models  # noqa: F401

        from db.models import Base

        engine = create_engine(args.url, echo=args.echo)
        Base.metadata.create_all(bind=engine)
        db_url = args.url
    else:
        from db.session import engine, init_db

        engine.echo = args.echo
        init_db()
        db_url = str(engine.url)

    # 打印建表结果
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"数据库：{db_url}")
    print(f"已确认的表：{', '.join(tables) if tables else '（无）'}")
    for table in tables:
        cols = [col["name"] for col in inspector.get_columns(table)]
        print(f"  - {table}: {', '.join(cols)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
