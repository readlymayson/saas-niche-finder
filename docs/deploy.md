# Деплой SaaS Niche Finder (Hetzner CX22)

Ориентир: Ubuntu 22.04+, Docker 24+, 2 vCPU / 4 GB RAM.

## 1. Сервер

1. Создайте VPS (например Hetzner CX22), откройте порты **22**, **80**, **443**.
2. Установите Docker и compose plugin.
3. Клонируйте репозиторий в `/opt/saas-niche-finder`.

## 2. Секреты

Скопируйте `.env.example` → `.env` на сервере и задайте:

- `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`
- `TELEGRAM_*` (если live-парсинг)
- `YANDEX_*` (Вордстат / YandexGPT)
- `YOOKASSA_*` + `SYNGATE_ALLOW_YOOKASSA_PROD=1` после human-gate
- `YOOKASSA_RETURN_URL=https://yourapp.ru/billing/success`

## 3. ML-артефакт (неделя 2)

На машине с GPU или локально:

```bash
docker compose --profile ml run --rm ml-train
python backend/ml/check_artifact_metrics.py --min-accuracy 0.85
```

Скопируйте `backend/ml/artifacts/rubert-pain-cls` на сервер (каталог в `.gitignore`).

## 4. Запуск стека

```bash
docker compose up -d postgres redis api worker beat
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

## 5. Frontend

Соберите статику и отдайте через nginx:

```bash
cd frontend && npm ci && npm run build
```

Пример nginx: `root /var/www/niche-finder/dist;` + proxy `/api` → `http://127.0.0.1:8000` (или отдельный поддомен API).

## 6. Webhook ЮKassa

URL: `https://yourapp.ru/v1/billing/webhooks/yookassa`  
Событие: `payment.succeeded`. В metadata при оплате передаётся `user_email`.

## 7. Нагрузочное тестирование

```bash
pip install locust
locust -f locustfile.py --host http://127.0.0.1:8000
```

Цель MVP: 100 RPS на `/health` и публичные маршруты с p95 < 500 ms (без тяжёлого ML на hot path).

## 8. Бэкапы

- Ежедневный `pg_dump` PostgreSQL
- Redis — по необходимости (квоты Free переживут сброс)
