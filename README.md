# SaaS Niche Finder

Монорепозиторий: backend (FastAPI), frontend (React + Vite).

## Локальная разработка (backend)

### Виртуальное окружение

```bash
python -m venv .venv
```

Активация:

- Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
- Linux / macOS: `source .venv/bin/activate`

### Установка зависимостей

Из **корня** репозитория:

```bash
pip install -e "./backend[dev]"
```

Группа `dev` ставит среду для тестов и [Ruff](https://docs.astral.sh/ruff/). Дополнительно для ML (torch, transformers): `pip install -e "./backend[ml]"` или сразу `pip install -e "./backend[dev,ml]"`. В PowerShell для extras безопаснее одиночные кавычки во всём аргументе, например `pip install -e './backend[dev,ml]'`.

### Переменные окружения

Реальные секреты в репозиторий не попадают. Шаблон — файл [.env.example](.env.example) в корне: скопируйте его в `.env` и заполните значения локально.

При запуске API `pydantic-settings` читает `.env` относительно **текущего рабочего каталога**. Если вы поднимаете сервер из каталога `backend/`, положите `.env` рядом (например `backend/.env`), предварительно скопировав из `.env.example`.

### Тесты и линтер

Из **корня**:

```bash
python -m pytest
python -m ruff check backend tests
```

Пути к тестам и `PYTHONPATH` для пакета `app` задаются в [pytest.ini](pytest.ini).

## Frontend (React + Vite)

Из каталога [frontend/](frontend/):

```bash
cd frontend
npm ci
npm run dev
```

Приложение: http://localhost:5173 — CORS для API уже настроен в `backend/app/main.py`.

Переменная `VITE_API_URL` (см. [.env.example](.env.example)) по умолчанию `http://127.0.0.1:8000`. Подробнее — [frontend/README.md](frontend/README.md).

Поднимите API (`uvicorn app.main:app` из `backend/` или `docker compose up api`) перед входом в дашборд.

## SynGate (полуавтономная выручка)

- Бизнес-контекст: [state/business-brief.md](state/business-brief.md)
- Revenue-бэклог: [backlog/revenue.yaml](backlog/revenue.yaml)
- Черновики маркетинга: [marketing/](marketing/) — публикация после approve в `state/approval_queue.json`
- Оркестратор: [SynEvo](../SynEvo) — `python -m synevo.loop --lane revenue` или `scripts/run_syngate_cycle.ps1`
