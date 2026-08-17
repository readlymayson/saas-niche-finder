-- Миграция: убрать мультитенантность (users/api_keys) из личного инструмента.
--
-- ВНИМАНИЕ: запускать ОДИН раз на существующей БД (docker compose up postgres),
-- перед первым запуском API. НЕ трогает niche_ideas / raw_posts / wordstat_cache
-- (эмбеддинги pgvector сохраняются).
--
-- Запуск:
--   docker compose exec -T postgres psql -U postgres -d niche_finder < backend/scripts/migrate_drop_users.sql
-- или
--   psql postgresql://postgres:postgres@localhost:5432/niche_finder -f backend/scripts/migrate_drop_users.sql

BEGIN;

-- Снимаем FK feedback.user_id (таблица users удаляется ниже)
ALTER TABLE IF EXISTS feedback DROP COLUMN IF EXISTS user_id;

-- Удаляем таблицы мультитенантности (CASCADE снимет оставшиеся зависимости)
DROP TABLE IF EXISTS processed_webhooks CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS users CASCADE;

COMMIT;

-- Проверка (опционально):
-- SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
