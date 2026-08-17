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
)
celery_app.autodiscover_tasks(["app.workers"])

# ── Celery Beat Schedule ──
# Runs the entire ETL pipeline on a regular basis.
# NOTE: only tasks defined in app/workers/tasks.py are scheduled here.

celery_app.conf.beat_schedule = {
    # Scrape VC.ru every hour
    "scrape-vcru-every-hour": {
        "task": "app.workers.tasks.scrape_vcru",
        "schedule": crontab(minute="5"),  # 5 minutes past each hour
    },
    # Scrape Telegram every 2 hours
    "scrape-telegram-every-2-hours": {
        "task": "app.workers.tasks.scrape_telegram",
        "schedule": crontab(minute="15", hour="*/2"),
    },
    # ML-process new posts every 15 minutes
    "process-raw-posts-every-15-min": {
        "task": "app.workers.tasks.process_raw_posts",
        "schedule": crontab(minute="*/15"),
        "kwargs": {"limit": 20},
    },
    # Aggregate niches every 30 minutes
    "aggregate-niches-every-30-min": {
        "task": "app.workers.tasks.aggregate_niches",
        "schedule": crontab(minute="*/30"),
    },
    # Update Wordstat data every 6 hours
    "update-wordstat-every-6-hours": {
        "task": "app.workers.tasks.update_wordstat",
        "schedule": crontab(minute="0", hour="*/6"),
    },
    # Re-score all niches daily at 3:00 AM
    "score-niches-daily": {
        "task": "app.workers.tasks.score_niches",
        "schedule": crontab(hour="3", minute="0"),
    },
}
