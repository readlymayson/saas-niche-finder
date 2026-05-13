"""YandexGPT (Foundation Models): синхронный HTTP-клиент для черновых карточек ниш."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class YandexGptError(Exception):
    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.detail = detail


def default_model_uri(settings: Settings) -> str:
    if settings.yandex_gpt_model_uri:
        return settings.yandex_gpt_model_uri
    if not settings.yandex_gpt_folder_id:
        msg = "Задайте YANDEX_GPT_FOLDER_ID или YANDEX_GPT_MODEL_URI"
        raise YandexGptError(msg)
    return f"gpt://{settings.yandex_gpt_folder_id}/yandexgpt/latest"


class YandexGptClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._own_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=120.0)

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        key = self._settings.yandex_gpt_api_key
        if not key:
            msg = "Задайте YANDEX_GPT_API_KEY"
            raise YandexGptError(msg)
        return {
            "Authorization": f"Api-Key {key}",
            "Content-Type": "application/json",
        }

    async def complete(
        self,
        user_text: str,
        *,
        system_text: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        model_uri = default_model_uri(self._settings)
        system_text = system_text or (
            "Ты аналитик B2B-рынков РФ. Отвечай кратко и по делу на русском, структурируй списками."
        )
        body: dict[str, Any] = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(max_tokens),
            },
            "messages": [
                {"role": "system", "text": system_text},
                {"role": "user", "text": user_text},
            ],
        }
        r = await self._client.post(
            self._settings.yandex_gpt_api_url,
            headers=self._headers(),
            json=body,
        )
        if r.status_code >= 400:
            raise YandexGptError(f"YandexGPT HTTP {r.status_code}", detail=r.text)
        data = r.json()
        return data

    async def niche_card_draft(
        self,
        keyword: str,
        wordstat_summary: str | None = None,
    ) -> dict[str, Any]:
        prompt = (
            f"Сформируй черновую карточку B2B-ниши по ключу «{keyword}». "
            "Включи: 1) кому продаём 2) боль/запрос 3) тип продукта (SaaS/сервис) "
            "4) примеры конкурентов/аналогов 5) риски. Кратко."
        )
        if wordstat_summary:
            prompt += f"\n\nКонтекст по Вордстат (если есть): {wordstat_summary}"
        return await self.complete(prompt)
