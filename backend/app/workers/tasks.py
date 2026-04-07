from celery import shared_task


@shared_task(name="app.workers.tasks.ping")
def ping() -> str:
    return "pong"
