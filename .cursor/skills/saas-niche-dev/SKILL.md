---
name: saas-niche-dev
description: Локальная разработка saas-niche-finder для циклов SynEvo (pytest, ruff, backend venv).
---

# SaaS Niche Finder — dev workflow

## Окружение

Из корня репозитория `saas-niche-finder`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e "./backend[dev]"
```

## Проверки (как CI)

```powershell
python -m ruff check backend tests
python -m pytest -q
```

## Структура

- API: `backend/app/api/`
- Сервисы: `backend/app/services/`
- Тесты: `tests/` (корень репо)
- Конфиг: `backend/app/config.py`, пример env: `.env.example`

## SynEvo

- Бэклог: `backlog/tasks.yaml`
- Правила агента: `.cursor/rules/synevo-agent.md`
- Sandbox: `.cursor/sandbox.json`

Не трогай `backend/ml/artifacts/` без явной задачи.
