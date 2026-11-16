#!/bin/bash
set -e

echo "=== FluxVPN Worker API Starting ==="
echo "PORT: ${PORT:-8080}"
echo "DATABASE_URL set: $(if [ -n "$DATABASE_URL" ]; then echo 'yes'; else echo 'NO!'; fi)"
echo "REDIS_URL set: $(if [ -n "$REDIS_URL" ]; then echo 'yes'; else echo 'NO!'; fi)"

# Test basic Python imports first
echo "Testing Python imports..."
python -c "
import sys
print(f'Python: {sys.version}')

# Test critical imports
try:
    print('Importing fastapi...', end=' ')
    import fastapi
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)

try:
    print('Importing sqlalchemy...', end=' ')
    import sqlalchemy
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)

try:
    print('Importing eth_account...', end=' ')
    from eth_account import Account
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)

try:
    print('Importing app.core.config...', end=' ')
    from app.core.config import settings
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)

try:
    print('Importing app.core.database...', end=' ')
    from app.core.database import Base, engine
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)

try:
    print('Importing app.models...', end=' ')
    from app.models import *
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)

try:
    print('Importing app.main...', end=' ')
    from app.main import app
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)

print('All imports successful!')
"

# Wait for database to be ready
echo "Waiting for database..."
python -c "
import time
import psycopg2
import os

database_url = os.environ.get('DATABASE_URL', '')
max_retries = 30
retry_delay = 2

for i in range(max_retries):
    try:
        conn = psycopg2.connect(database_url)
        conn.close()
        print('Database is ready!')
        break
    except Exception as e:
        print(f'Waiting for database... ({i+1}/{max_retries}): {e}')
        time.sleep(retry_delay)
else:
    print('Could not connect to database after max retries')
    exit(1)
"

# Run database migrations for schema sync
echo "Running database migrations..."
alembic upgrade head

echo "Database setup complete!"

# Start the application
echo "Starting Worker API on port ${PORT:-8080}..."
if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --reload
fi

exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
