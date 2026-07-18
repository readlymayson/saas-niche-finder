#!/bin/bash
apt-get install -y -qq postgresql-18-pgvector
su - postgres -c "psql -d niche_finder -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
echo "pgvector installed and enabled"
