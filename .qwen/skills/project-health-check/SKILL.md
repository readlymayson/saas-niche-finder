---
name: project-health-check
description: Perform a systematic readiness check on a full-stack monorepo — verify backend (Python/venv/ruff/pytest), frontend (npm/tsc), Docker/env config, and run tests/linters in a single pass
source: auto-skill
extracted_at: '2026-06-10T14:51:11.687Z'
---

# Project Health Check Procedure

## Когда применять

Когда пользователь просит «проверить, готов ли проект к работе» или дать общий вердикт о состоянии проекта — особенно для Python+TS моногепо с Docker и Celery.

## Процедура

Проверки можно запускать параллельно группами, если инструменты не зависят друг от друга.

### Шаг 1 — Backend
1. **Версия Python**: проверить через `.venv/Scripts/python --version` (или `python3 --version`) — должна соответствовать `requires-python` в `pyproject.toml`.
2. **Импорт модуля**: `python -c "import app"` — убедиться, что пакет установлен (`pip install -e .`).
3. **Структура файлов**: просканировать `backend/**/*.py` — убедиться, что все ожидаемые модули на месте (api, models, services, workers, ml, config, main).

### Шаг 2 — Frontend
1. **package.json**: проверить наличие и состав зависимостей.
2. **Установка пакетов**: `npm ls --depth=0` — все ли пакеты на месте, нет ли missing peer dependencies.
3. **TypeScript**: `npx tsc --noEmit` — ноль ошибок компиляции.
4. **Структура**: проверить наличие ключевых страниц и компонентов (`frontend/src/pages/`, `frontend/src/components/`).

### Шаг 3 — Docker и инфраструктура
1. **docker-compose.yml**: проверить наличие всех сервисов (postgres, redis, api, worker, beat, ml-train).
2. **Dockerfile**'s: проверить наличие `backend/Dockerfile`, `backend/Dockerfile.ml` (если есть ml-профиль).
3. **.env**: проверить, существует ли файл `.env` (в корне или `backend/.env`). Если нет — отметить как предупреждение.

### Шаг 4 — .env и переменные окружения

Если `.env` отсутствует:
1. Скопировать `.env.example` → `.env`.
2. **Обязательно сгенерировать `JWT_SECRET_KEY`**:
   ```
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Вставить вывод в `JWT_SECRET_KEY=` в `.env`.
3. Для остальных секретов (Telegram, Яндекс, ЮKassa) — оставить закомментированными.

**Диагностика pydantic-settings** (critical — частый источник путаницы):
- pydantic-settings читает .env, но **системные переменные окружения имеют приоритет** над .env.
- Если в системе (Windows: `set VAR=value`, Linux: `export VAR=value`) уже задана переменная с тем же именем — значение .env будет проигнорировано.
- Проверка: выполнить скрипт, который сравнивает os.environ и dotenv_values:
  ```python
  import os
  from pydantic_settings import BaseSettings, SettingsConfigDict
  class S(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
      ...
  s = S()
  # если значение из .env НЕ применилось — значит есть системная env var
  ```
- На Windows: `setx` обновляет системную переменную, но действует только для **новых** сессий cmd.
- **Решение**: перезапустить терминал, либо удалить системную env var.

### Шаг 5 — Линтер
- Запустить `ruff check backend tests` (или эквивалент для другого языка).
- Убедиться, что «All checks passed!».

### Шаг 6 — Тесты
- Запустить `python -m pytest -v --tb=short`.
- Зафиксировать: сколько passed/skipped/failed, общее время.
- Обратить внимание на warnings (deprecation — обычно не критично, но отметить).

### Шаг 7 — Финальный вердикт
Собрать результаты в формате:

```
## Результаты проверки

### ✅ Backend
- **Python**: <версия> (<требование>)
- **Ruff**: <версия> — <результат>
- **Модули**: <import app — успех/неудача>
- **Структура**: <кол-во файлов> .py файлов, <краткая оценка>

### ✅ Frontend
- **TypeScript**: <результат tsc --noEmit>
- **Зависимости**: все/не все установлены
- **Структура**: <кол-во компонентов>, оценка конфигурации

### ✅ Тесты
- **N passed, N skipped, N failed** — <время>
- <кол-во> тестовых файлов, <кол-во> фикстур

### ⚠️ Замечания
1. ...
2. ...

### Итог
<Одна строка: готов/не готов к работе>
```

## Важные нюансы

- **Python 3.14**: на Windows может выдавать `pkg_resources` deprecation warnings от некоторых библиотек (pymorphy2, setuptools). Это не блокер, но если начнутся проблемы — рекомендовать Python 3.11–3.13.
- **setuptools <82**: в `pyproject.toml` может быть явный пин `setuptools>=65.0,<82` — это связано с тем, что setuptools 82+ ломает `pkg_resources`. При проверке обратить внимание.
- **.env**: отсутствие `.env` — не ошибка, но обязательное предупреждение. Проект не запустится с настройками по умолчанию.
- **Docker**: если docker-compose.yml есть, но контейнеры не запущены — отметить, что это нормально для проверки, но нужно для полноценного запуска.
- **pydantic-settings env var priority**: если .env создан, но его значения не применяются (особенно JWT) — проверить `os.environ` на наличие одноимённых переменных. На Windows их можно увидеть через `set VAR` в cmd. pydantic-settings всегда отдаёт приоритет реальным env var перед .env.
