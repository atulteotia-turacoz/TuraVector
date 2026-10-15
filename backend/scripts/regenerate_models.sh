#!/usr/bin/env bash
# Regenerate app/models/generated.py from the live MySQL schema.
cd "$(dirname "$0")/.."
set -a; source .env; set +a
PW=$(python3 -c "import urllib.parse,os;print(urllib.parse.quote_plus(os.environ['DB_PASSWORD']))")
./venv/bin/sqlacodegen --generator declarative "mysql+pymysql://${DB_USER}:${PW}@${DB_HOST}:${DB_PORT}/${DB_NAME}" > app/models/generated.py
