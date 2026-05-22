# SynEvo agent rules (saas-niche-finder)

Адаптировано из практик Karpathy / superpowers — только то, что снижает типичные ошибки LLM в коде.

## Обязательно

- Один цикл = одна задача из task-card; не рефакторить «заодно» соседние модули.
- Минимальный diff: меняй только файлы, нужные для acceptance.
- Не выдумывай API, env-переменные и зависимости — смотри существующий код и `.env.example`.
- Перед завершением: `python -m pytest -q` и `python -m ruff check backend tests` из **корня** репозитория.
- Установка dev-зависимостей: `pip install -e "./backend[dev]"` (без секретов в код/коммит).
- Не коммить `.env`, ключи, токены; не логировать секреты в stdout.

## Тесты

- Новые тесты — без внешних API (Telegram, Yandex GPT, Wordstat) unless уже замокано в fixtures.
- Предпочитай существующие паттерны в `tests/` (async pytest, fixtures).

## Стиль

- Следуй ruff (E, F, I, UP) и структуре `backend/app/`.
- Не добавляй лишние абстракции «на будущее».
- Комментарии только для неочевидной бизнес-логики.

## Sandbox

- Не отключай sandbox без необходимости.
- Сеть — только для pip/npm согласно `.cursor/sandbox.json`.

## При провале L0

- Читай блок «Краткий снимок метрик» и исправляй конкретную ошибку, не переписывай модуль целиком.

## SynGate (human-gate)

- **Запрещено без approve** (`state/approval_queue.json`, `approved: true`): `git push`, prod deploy, изменение `.env`, цен, оферты, webhook ЮKassa на prod.
- **Revenue-lane:** skill `.cursor/skills/syngate/SKILL.md`; артефакт в `state/revenue/<task-id>.md`.
- **Kill switch:** если в корне репо есть `state/PAUSE` — не вноси изменений (цикл остановлен оркестратором).
- Не отправляй email и не публикуй посты от имени продукта — только черновики в `marketing/`.
