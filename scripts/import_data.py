#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三周 Day 2：数据入库脚本（数据迁移）。

把已有的离线结果批量写入数据库：
  1. 第二周视频标签（ASR 语音转文字/output_fusion/<分类>/<视频>.json）→ videos 表
  2. 第一周风格诊断记录（history/<record_id>.json）→ user_profiles 表

可选：合并 video_crawler/data/crawler_index.csv 里的 URL、时长、点赞/播放数。

用法：
  python import_data.py                  # 全部入库（已存在的自动跳过）
  python import_data.py --videos         # 只导入视频
  python import_data.py --profiles       # 只导入用户画像
  python import_data.py --force          # 已存在的记录也更新
  python import_data.py --dry-run        # 只统计，不写库
  python import_data.py --limit 3        # 只处理前 3 个
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# 保证从 scripts/ 子目录运行时也能 import 项目根目录的 db 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.models import UserProfile, Video
from db.session import SessionLocal

# Windows 控制台默认 GBK，统一按 UTF-8 输出并容错
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT_DIR = Path(__file__).resolve().parent  # beauty-advisor/scripts
ROOT_DIR = PROJECT_DIR.parent.parent          # F:\looks

DEFAULT_VIDEO_DIR = ROOT_DIR / "ASR 语音转文字" / "output_fusion"
DEFAULT_ASR_OUTPUT = ROOT_DIR / "ASR 语音转文字" / "output"
DEFAULT_INDEX_FILE = ROOT_DIR / "video_crawler" / "data" / "crawler_index.csv"
DEFAULT_HISTORY_DIR = PROJECT_DIR.parent / "history"
DEFAULT_MC_DIR = ROOT_DIR / "MediaCrawler"


def _normalize_stem(name: str) -> str:
    """去掉 .fNNNNN 流后缀，得到内容名。"""
    return re.sub(r"\.f\d+$", "", name)


def load_crawler_index(index_file: Path) -> tuple[dict, dict]:
    """读取 video_crawler 索引，返回 (按标题, 按 video_id) 两个元数据索引。"""
    result: dict = {}
    by_id: dict = {}
    if not index_file.is_file():
        print(f"[索引] 未找到 {index_file}，跳过热度/URL 合并。")
        return result, by_id
    with open(index_file, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = _normalize_stem(row.get("title", "")).strip()
            meta = {
                "video_id": (row.get("video_id") or "").strip(),
                "url": (row.get("url") or "").strip(),
                "uploader": (row.get("uploader") or "").strip(),
                "duration_sec": _to_float(row.get("duration")),
                "like_count": _to_int(row.get("like_count")),
                "view_count": _to_int(row.get("view_count")),
                "comment_count": _to_int(row.get("comment_count")),
            }
            if key:
                result[key] = meta
            if meta["video_id"]:
                by_id[meta["video_id"]] = meta
    print(f"[索引] 已加载 {len(result)} 条视频元数据：{index_file}")
    return result, by_id


def lookup_meta(stem: str, by_title: dict, by_id: dict) -> dict:
    """按 文件名 stem 查找 crawler_index 元数据：
    1) stem 与标题完全一致；2) 标题包含在 stem 中（取最长）；3) video_id 前缀命中（xhs 笔记 id）。
    """
    if stem in by_title:
        return by_title[stem]
    candidates = [k for k in by_title if k and k in stem]
    if candidates:
        return by_title[max(candidates, key=len)]
    vid = ""
    for v in by_id:
        if stem.startswith(v + "_") or stem == v:
            if len(v) > len(vid):
                vid = v
    if vid:
        return by_id[vid]
    return {}


def _to_float(value) -> float:
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    try:
        return int(float(value)) if value not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def collect_fusion_files(video_dir: Path) -> list[tuple[str, Path]]:
    """扫描 output_fusion，返回 [(stem, 首个 JSON 路径)]，跨分类按 stem 去重。"""
    if not video_dir.is_dir():
        print(f"[视频] 未找到融合结果目录：{video_dir}")
        return []
    groups: dict[str, list[Path]] = {}
    for p in sorted(video_dir.rglob("*.json")):
        if "_report" in p.parts:
            continue
        groups.setdefault(p.stem, []).append(p)
    return [(stem, files[0]) for stem, files in sorted(groups.items())]


def _frames_count(asr_output: Path, cat: str, stem: str) -> int:
    frames_dir = asr_output / cat / f"{stem}_frames"
    if not frames_dir.is_dir():
        return 0
    return len(list(frames_dir.glob("keyframe_*.jpg")))


def _duration_from_keyframes(asr_output: Path, cat: str, stem: str) -> float:
    """用关键帧时间戳索引估算视频时长（秒），找不到返回 0。"""
    idx = asr_output / cat / f"{stem}_frames" / "keyframes.txt"
    if not idx.is_file():
        return 0.0
    last = 0.0
    for line in idx.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*([\d.]+)s\s", line)
        if m:
            last = max(last, float(m.group(1)))
    return last


def build_video(stem: str, json_path: Path, asr_output: Path, meta: dict) -> Video | None:
    """把一个融合 JSON 转成 Video 对象；解析失败返回 None。"""
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"    [跳过] {stem} JSON 解析失败：{exc}")
        return None

    if payload.get("error"):
        print(f"    [跳过] {stem} 融合结果含错误：{payload['error'][:120]}")
        return None

    result = payload.get("result") or {}
    categories = list(payload.get("categories") or [])
    first_cat = categories[0] if categories else ""

    txt_path = asr_output / first_cat / f"{stem}.txt"
    asr_text = ""
    if txt_path.is_file():
        asr_text = txt_path.read_text(encoding="utf-8", errors="replace")
    else:
        print(f"    [提示] 未找到转写文本：{txt_path}")

    duration = meta.get("duration_sec") or 0.0
    if not duration:
        duration = _duration_from_keyframes(asr_output, first_cat, stem)

    return Video(
        video_id=stem,
        title=(result.get("title") or payload.get("video") or stem),
        uploader=meta.get("uploader") or "",
        categories=categories,
        summary=result.get("summary") or "",
        steps=list(result.get("steps") or []),
        tips=list(result.get("tips") or []),
        keywords=list(result.get("keywords") or []),
        conclusion=result.get("conclusion") or "",
        tags={},  # 人群标签（face_shapes/pain_points 等）依赖 Day2 之后的 video_tagger，暂无数据
        asr_text=asr_text,
        asr_source=str(txt_path),
        vl_source=str(payload.get("vl_source") or ""),
        fusion_source=str(json_path),
        duration_sec=round(duration, 1),
        frames_count=_frames_count(asr_output, first_cat, stem),
        like_count=meta.get("like_count") or 0,
        collect_count=0,
        play_count=meta.get("view_count") or 0,
        source_url=meta.get("url") or "",
        content_type="video",
    )


def import_videos(db, video_dir: Path, asr_output: Path, index_file: Path, force: bool, limit: int, dry_run: bool) -> dict:
    meta_by_title, meta_by_id = load_crawler_index(index_file)
    items = collect_fusion_files(video_dir)
    if limit:
        items = items[:limit]

    inserted = updated = skipped = failed = 0
    for stem, json_path in items:
        existing = db.scalar(select(Video).where(Video.video_id == stem))
        if existing and not force:
            skipped += 1
            continue

        video = build_video(stem, json_path, asr_output, lookup_meta(stem, meta_by_title, meta_by_id))
        if video is None:
            failed += 1
            continue

        if dry_run:
            print(f"    [将导入] {stem}")
            continue

        if existing and force:
            for key, value in video.__dict__.items():
                if key != "_sa_instance_state" and key != "id":
                    if key == "tags" and not value and getattr(existing, "tags", None):
                        continue  # 不覆盖已有标签
                    setattr(existing, key, value)
            updated += 1
        else:
            db.add(video)
            inserted += 1
        print(f"    [{'更新' if existing and force else '导入'}] {stem}")

    if not dry_run:
        db.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "failed": failed}


def collect_history_files(history_dir: Path) -> list[Path]:
    if not history_dir.is_dir():
        print(f"[画像] 未找到历史记录目录：{history_dir}")
        return []
    return sorted(history_dir.glob("*.json"))


def build_profile(json_path: Path) -> UserProfile | None:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"    [跳过] {json_path.name} 解析失败：{exc}")
        return None

    face_info = data.get("face_info") or {}
    dims = data.get("dimensions") or {}
    return UserProfile(
        user_id="anonymous",
        record_id=str(data.get("id") or json_path.stem),
        age=face_info.get("age"),
        gender=face_info.get("gender") or "",
        face_shape=face_info.get("face_shape") or "",
        maturity=float(dims.get("maturity") or 0.5),
        volume=float(dims.get("volume") or 0.5),
        curvature=float(dims.get("curvature") or 0.5),
        width=float(dims.get("width") or 0.5),
        style_tag=data.get("style_tag") or "",
        keywords=list(data.get("keywords") or []),
        pain_points=[],  # 画像暂无痛点数据（依赖后续用户问卷）
        positioning_reason=data.get("positioning_reason") or "",
        makeup_advice=list(data.get("makeup_advice") or []),
        hair_advice=dict(data.get("hair_advice") or {}),
        summary=data.get("summary") or "",
    )


def import_profiles(db, history_dir: Path, force: bool, limit: int, dry_run: bool) -> dict:
    files = collect_history_files(history_dir)
    if limit:
        files = files[:limit]

    inserted = updated = skipped = failed = 0
    for json_path in files:
        record_id = json_path.stem
        existing = db.scalar(select(UserProfile).where(UserProfile.record_id == record_id))
        if existing and not force:
            skipped += 1
            continue

        profile = build_profile(json_path)
        if profile is None:
            failed += 1
            continue

        if dry_run:
            print(f"    [将导入] {record_id}（{profile.style_tag}）")
            continue

        if existing and force:
            for key, value in profile.__dict__.items():
                if key != "_sa_instance_state" and key != "id":
                    setattr(existing, key, value)
            updated += 1
        else:
            db.add(profile)
            inserted += 1
        print(f"    [{'更新' if existing and force else '导入'}] {record_id}（{profile.style_tag}）")

    if not dry_run:
        db.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "failed": failed}


def collect_image_notes(mc_dir: Path) -> list[dict]:
    """从 MediaCrawler 的小红书搜索结果里收集图文笔记（type != video）。"""
    jsonl_dir = mc_dir / "data" / "xhs" / "jsonl"
    json_dir = mc_dir / "data" / "xhs" / "json"
    records: list[dict] = []
    for folder in (jsonl_dir, json_dir):
        if not folder.is_dir():
            continue
        for fp in sorted(folder.glob("search_contents_*")):
            try:
                text = fp.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            if fp.suffix == ".jsonl":
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            else:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, list):
                    records.extend(r for r in data if isinstance(r, dict))
                elif isinstance(data, dict):
                    records.append(data)
    seen: dict[str, dict] = {}
    for r in records:
        if str(r.get("type") or "").strip() == "video":
            continue
        note_id = str(r.get("note_id") or "").strip()
        if not note_id or not (r.get("note_url") or "").strip():
            continue
        seen.setdefault(note_id, r)
    return list(seen.values())


def import_image_notes(db, mc_dir: Path, force: bool, dry_run: bool) -> dict:
    """把小红书图文笔记（无视频）也入库：标题 + 分类 + 笔记链接，content_type=image_note。"""
    items = collect_image_notes(mc_dir)
    inserted = updated = skipped = 0
    for note in items:
        note_id = str(note.get("note_id") or "").strip()
        existing = db.scalar(select(Video).where(Video.video_id == note_id))
        if existing and not force:
            skipped += 1
            continue
        title = (note.get("title") or note.get("desc") or note_id)[:200]
        cat = (note.get("source_keyword") or "").strip()
        row = Video(
            video_id=note_id,
            title=title,
            categories=[cat] if cat else [],
            summary="",
            keywords=list(note.get("tag_list") or []),
            source_url=str(note.get("note_url") or ""),
            content_type="image_note",
        )
        if dry_run:
            print(f"    [将导入图文] {note_id}（{cat}）")
            continue
        if existing and force:
            for key, value in row.__dict__.items():
                if key != "_sa_instance_state" and key != "id":
                    setattr(existing, key, value)
            updated += 1
        else:
            db.add(row)
            inserted += 1
    if not dry_run:
        db.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description="把离线结果批量导入数据库（Day 2）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--videos", action="store_true", help="只导入视频")
    group.add_argument("--profiles", action="store_true", help="只导入用户画像")
    group.add_argument("--image-notes", action="store_true", help="只导入小红书图文笔记")
    parser.add_argument("--video-dir", default=str(DEFAULT_VIDEO_DIR), help="融合 JSON 目录")
    parser.add_argument("--asr-output", default=str(DEFAULT_ASR_OUTPUT), help="ASR 项目 output 目录")
    parser.add_argument("--index-file", default=str(DEFAULT_INDEX_FILE), help="video_crawler 索引 CSV")
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR), help="历史诊断记录目录")
    parser.add_argument("--mc-dir", default=str(DEFAULT_MC_DIR), help="MediaCrawler 根目录（图文笔记来源）")
    parser.add_argument("--force", action="store_true", help="已存在的记录也更新")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数（0=全部）")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.image_notes:
            print("== 导入小红书图文笔记（image_note）==")
            r = import_image_notes(db, Path(args.mc_dir), args.force, args.dry_run)
            print(f"图文：导入 {r['inserted']}，更新 {r['updated']}，跳过 {r['skipped']}")
            return
        if not args.profiles:
            print("== 导入视频（videos）==")
            r = import_videos(
                db, Path(args.video_dir), Path(args.asr_output),
                Path(args.index_file), args.force, args.limit, args.dry_run,
            )
            print(f"视频：导入 {r['inserted']}，更新 {r['updated']}，跳过 {r['skipped']}，失败 {r['failed']}")
        if not args.videos:
            print("\n== 导入用户画像（user_profiles）==")
            r = import_profiles(db, Path(args.history_dir), args.force, args.limit, args.dry_run)
            print(f"画像：导入 {r['inserted']}，更新 {r['updated']}，跳过 {r['skipped']}，失败 {r['failed']}")
    finally:
        db.close()

    if args.dry_run:
        print("\n（--dry-run：未写入任何数据）")


if __name__ == "__main__":
    main()
