from celery import Celery

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
)
celery_app.autodiscover_tasks(["app.workers"])
