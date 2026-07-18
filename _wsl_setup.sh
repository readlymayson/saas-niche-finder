#!/bin/bash
# Настройка PostgreSQL и Redis в WSL

echo "=== Starting Redis ==="
service redis-server start
redis-cli ping

echo "=== Starting PostgreSQL ==="
service postgresql start

echo "=== Setting password ==="
su - postgres -c "psql -c \"ALTER USER postgres PASSWORD 'postgres';\""

echo "=== Configuring pg_hba.conf ==="
PG_HBA=$(find /etc/postgresql -name pg_hba.conf 2>/dev/null | head -1)
if ! grep -q "0.0.0.0/0" "$PG_HBA"; then
    echo "host all all 0.0.0.0/0 scram-sha-256" >> "$PG_HBA"
fi

echo "=== Configuring listen_addresses ==="
PG_CONF=$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -1)
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"
sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"

echo "=== Restarting PostgreSQL ==="
service postgresql restart

echo "=== Creating database ==="
su - postgres -c "createdb niche_finder 2>/dev/null || echo 'DB already exists'"

echo "=== Verifying ==="
su - postgres -c "psql -c 'SELECT datname FROM pg_database;'"

echo "=== Test connection ==="
pg_isready

echo ""
echo "=== DONE ==="
echo "PostgreSQL: localhost:5432, user=postgres, password=postgres, db=niche_finder"
echo "Redis:      localhost:6379"
