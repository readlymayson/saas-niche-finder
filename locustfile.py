"""Locust: smoke нагрузки API (план MVP — ориентир 100 RPS)."""

from locust import HttpUser, between, task


class ApiUser(HttpUser):
    wait_time = between(0.01, 0.05)

    @task(3)
    def health(self) -> None:
        self.client.get("/health")

    @task(2)
    def ready(self) -> None:
        self.client.get("/ready")

    @task(1)
    def root_openapi(self) -> None:
        self.client.get("/openapi.json", name="/openapi.json")
