# SaaS Niche Finder — QWEN.md

## Project Overview

Монорепозиторий для поиска B2B SaaS-ниш на российском рынке. Агрегирует сигналы из Telegram-каналов, VC.ru, Яндекс.Вордстата и YandexGPT, ранжирует ниши по скорингу и представляет в виде карточек на дашборде.

**Статус**: MVP (pre-prod). Prod billing и публикация контента — только после ручного human-gate.

---

## Tech Stack

### Backend (`backend/`)
- **Язык**: Python ≥3.11
- **Фреймворк**: FastAPI (uvicorn)
- **ORM**: SQLAlchemy 2.0 (asyncpg, asyncio)
- **Брокер задач**: Celery + Redis
- **БД**: PostgreSQL 15 + pgvector (для эмбеддингов)
- **Миграции**: Alembic (опционально — автосоздание таблиц через lifespan)
- **Аутентификация**: JWT (python-jose) + bcrypt (passlib)
- **ML**: RuBERT (transformers, torch), Natasha (NLP), pgvector
- **Внешние API**: Telethon (Telegram), Яндекс.Директ (Вордстат), YandexGPT, ЮKassa
- **Тесты**: pytest, pytest-asyncio, aiosqlite (DB-less тесты), Locust (нагрузочные)
- **Линтер**: Ruff (E, F, I, UP, line-length=100)

### Frontend (`frontend/`)
- **Язык**: TypeScript (strict)
- **Фреймворк**: React 18 + Vite 5
- **Стили**: Tailwind CSS + shadcn/ui (Radix UI, class-variance-authority)
- **Роутинг**: react-router-dom v6
- **Сборка**: `tsc -b && vite build`
- **Линтер**: ESLint (flat config)

### Инфраструктура
- **Контейнеризация**: Docker Compose
- **Профили**: `ml` — для обучения RuBERT (отдельный образ с torch)
- **Сервисы**: postgres, redis, api, worker, beat, ml-train

---

## Building & Running

### Backend (локально)

```bash
# Виртуальное окружение
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate       # Linux/macOS

# Установка
pip install -e "./backend[dev]"       # + тесты и ruff
pip install -e "./backend[dev,ml]"    # + torch/transformers

# Запуск API
uvicorn app.main:app --reload --port 8000
# Из каталога backend/ с .env рядом
```

### Frontend (локально)

```bash
cd frontend
npm ci
npm run dev       # http://localhost:5173
npm run build     # tsc -b && vite build
npm run lint      # ESLint
```

### Docker Compose (все сервисы)

```bash
# Запуск БД + API + Celery
docker compose up -d

# Запуск с ML-сервисом (обучение RuBERT)
docker compose --profile ml run --rm ml-train python ml/build_demo_dataset.py
docker compose --profile ml run --rm ml-train
```

### Тесты и линтер

```bash
# Из корня репозитория
python -m pytest                       # все тесты
python -m pytest tests/test_auth.py    # конкретный файл
python -m ruff check backend tests     # линтер
```

### Нагрузочное тестирование

```bash
locust -f locustfile.py --host http://localhost:8000
```

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/          # Роутеры: auth, billing, niches
│   │   ├── core/         # (резерв)
│   │   ├── db/           # base.py (DeclarativeBase), session.py (engine/async_session)
│   │   ├── models/       # SQLAlchemy модели: user, niche_idea, raw_post, wordstat_cache, feedback, processed_webhook
│   │   ├── schemas/      # Pydantic схемы
│   │   ├── services/     # Бизнес-логика: telegram_collector, vc_ingest, vc_parser, wordstat,
│   │   │                 #   yandex_gpt, pain_classifier, scoring, niche_pipeline, niche_draft,
│   │   │                 #   natasha_entities, usage_limit
│   │   ├── workers/      # Celery-таски: ingest_telegram, ingest_vc_rss, refresh_niches_pipeline и т.д.
│   │   ├── config.py     # Pydantic Settings (env_file=backend/.env)
│   │   ├── deps.py       # FastAPI Depends (current_user, get_db)
│   │   └── main.py       # FastAPI app + lifespan (создание таблиц + pgvector)
│   ├── ml/               # ML-скрипты: train_classifier, embeddings, сбор датасета
│   ├── Dockerfile        # python:3.12-slim-bookworm
│   ├── Dockerfile.ml     # + torch/transformers
│   └── pyproject.toml    # Зависимости, ruff-конфиг
├── frontend/
│   ├── src/
│   │   ├── pages/        # Landing, AuthPage, Dashboard, NicheDetail, Account, BillingSuccess
│   │   ├── components/ui/  # shadcn/ui компоненты
│   │   ├── lib/          # api.ts (клиент API), utils.ts
│   │   ├── App.tsx       # Роутер (7 маршрутов)
│   │   └── main.tsx      # Точка входа
│   ├── package.json      # React 18, Vite 5, Tailwind, shadcn/ui
│   └── vite.config.ts    # @ alias, proxy /auth и /health на localhost:8000
├── tests/                # pytest-тесты бэкенда
│   ├── fixtures/         # Тестовые фикстуры (JSON, RSS)
│   ├── test_health.py, test_ready.py, test_auth_validation.py, test_niches_api.py,
│   │   test_scoring.py, test_vc_parser.py, test_natasha_entities.py, test_telegram_ingest.py,
│   │   test_niche_pipeline.py, test_ml_pipeline.py, test_usage_limit.py,
│   │   test_billing.py, test_billing_idempotency.py, test_week3_wordstat.py
├── backlog/
│   ├── revenue.yaml      # Revenue-бэклог SynGate (landing, SEO, email, pricing, outreach)
│   └── tasks.yaml        # Dev-бэклог (закрытые и текущие задачи)
├── state/
│   ├── business-brief.md # ICP, оффер, тарифы, human-gate чеклист
│   ├── metrics-business.json
│   └── revenue/          # Черновики для SynGate, .gitkeep
├── marketing/            # Черновики: landing-hero, pricing, onboarding-email, cold-outreach
├── go-to-market/         # GTM-материалы
├── docs/                 # Документация
├── docker-compose.yml    # postgres, redis, api, worker, beat, ml-train (profile)
├── locustfile.py         # Locust smoke-тест (~100 RPS)
├── pytest.ini            # pythonpath=backend, asyncio_mode=auto
└── .env.example          # Шаблон переменных окружения
```

---

## Architecture & Key Design Decisions

### API слои
1. **Роутеры** (`api/`) — только маршрутизация, Depends(), валидация
2. **Сервисы** (`services/`) — бизнес-логика, внешние API, скоринг
3. **Модели** (`models/`) — SQLAlchemy ORM
4. **Схемы** (`schemas/`) — Pydantic request/response
5. **Воркеры** (`workers/`) — Celery-таски для фоновой обработки

### База данных
- PostgreSQL + pgvector (эмбеддинги 768d от RuBERT)
- Таблицы создаются автоматически при старте через `lifespan` + `metadata.create_all`
- Миграции через Alembic для production

### Аутентификация
- JWT (access + refresh token)
- pydantic-settings читает `JWT_SECRET_KEY` из `.env`
- `/auth/register` — создание пользователя (free план)
- `/auth/login` — выдача токенов

### SynGate (полуавтономная выручка)
- **Агент не включает prod billing** и не публикует контент без `approved: true` в `state/approval_queue.json`
- Revenue-задачи в `backlog/revenue.yaml` с приоритетами
- Маркетинговые черновики сохраняются в `marketing/` и дублируются в `state/revenue/`
- Оркестратор: `SynEvo` (внешний репозиторий)

### ML
- RuBERT-pain classifier — классификация боли (p=0..1)
- Эмбеддинги (768d) для поиска похожих ниш через pgvector
- Скрипты: `ml/train_classifier.py`, `ml/embeddings.py`, `ml/build_demo_dataset.py`

### Celery (расписание)
| Таска | Расписание | Описание |
|-------|-----------|----------|
| `refresh_niches_pipeline` | Каждый час | Обновление пайплайна ниш |
| `recompute_niche_scores` | Каждые 30 мин | Пересчёт скоринга |
| `ingest_vc_rss` | 03:15 ежедневно | Сбор RSS VC.ru (фикстуры) |
| `ingest_telegram` | 03:30 ежедневно | Сбор Telegram (фикстуры) |

---

## Development Conventions

### Python
- **Форматирование**: Ruff (line-length=100)
- **Правила Ruff**: E (pycodestyle), F (pyflakes), I (imports), UP (pyupgrade)
- **Типизация**: Обязательна (Python 3.11+)
- **Target**: Python 3.11
- **Импорты**: `from app.{module} import {name}` (относительно pythonpath=backend)
- **Тесты**: pytest-asyncio, `asyncio_mode=auto`, `asyncio_default_fixture_loop_scope=function`
- **Пути к тестам**: `tests/` (из корня)

### TypeScript / React
- **strict** режим TypeScript
- **Алиас**: `@` → `src/`
- **Стили**: Tailwind CSS + shadcn/ui
- **Компоненты**: Функциональные, стрелочные функции, `export default`
- **Пути файлов**: PascalCase для компонентов, camelCase для утилит

### Docker
- **api/worker/beat**: общий образ `Dockerfile` (python:3.12-slim-bookworm)
- **ml-train**: отдельный образ `Dockerfile.ml` (с torch), профиль `ml`
- Каталог `backend/ml` монтируется в контейнер — правки без пересборки
- Переменные в docker-compose: `${VAR:-default}`

### Переменные окружения
- Шаблон: `.env.example`
- Локальный `.env` — в `.gitignore`
- Для локального запуска: `.env` рядом с рабочим каталогом (backend/)
- Документация по всем переменным — в `.env.example`

### Важные ограничения
- **Prod billing**: только после human-gate (чеклист в `state/business-brief.md`)
- **Публикация контента**: только через `state/approval_queue.json` с `approved: true`
- **Телеграм**: user-аккаунт через Telethon, flood control (30 msg/min)
- **ЮKassa**: webhook payment.succeeded проверяется тестовым платежом 1₽
