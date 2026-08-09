# tasks/celery_app.py
import json
import os
import logging
from celery import Celery

from config import TEMP_DIR
from core.video_tagger import generate_video_tags

logger = logging.getLogger(__name__)

celery_app = Celery(
    "beauty_advisor",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    # 限制并发数，避免本地模型过载
    worker_concurrency=2,
    # 单个任务超时10分钟
    task_soft_time_limit=600,
    task_time_limit=900,
)


@celery_app.task(bind=True, max_retries=2)
def process_video_task(self, video_id: str, asr_text: str, vl_analysis: str = ""):
    """
    异步视频标签生成任务

    流程：ASR文本 + VL分析 → 本地千问生成标签 → 存入JSON文件
    """
    try:
        logger.info(f"开始处理视频: {video_id}")

        # 调用本地千问生成标签
        tags = generate_video_tags(asr_text, vl_analysis)

        # 保存到本地JSON文件（MVP阶段暂不用数据库）
        os.makedirs(f"{TEMP_DIR}/video_tags", exist_ok=True)
        output_path = f"{TEMP_DIR}/video_tags/{video_id}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "video_id": video_id,
                "tags": tags,
            }, f, ensure_ascii=False, indent=2)

        logger.info(f"视频 {video_id} 标签生成完成，置信度: {tags.get('confidence', 0)}")
        return {"video_id": video_id, "status": "success", "tags": tags}

    except Exception as e:
        logger.error(f"视频 {video_id} 处理失败: {e}")
        raise self.retry(exc=e, countdown=60)