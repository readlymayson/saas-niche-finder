from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "saas_niche_finder",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "refresh-niches-pipeline-every-hour": {
            "task": "app.workers.tasks.refresh_niches_pipeline",
            "schedule": crontab(minute=0, hour="*"),
        },
        "recompute-niche-scores-every-30-min": {
            "task": "app.workers.tasks.recompute_niche_scores",
            "schedule": crontab(minute="*/30"),
        },
    },
)
celery_app.autodiscover_tasks(["app.workers"])
