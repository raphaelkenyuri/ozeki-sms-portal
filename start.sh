#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/ozeki-app.log"
PID_FILE="/tmp/ozeki.pid"
MODE="${1:-native}"   # native | docker | docker-stop | docker-logs

cd "$SCRIPT_DIR"

# ── Docker mode ───────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
  command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found."; exit 1; }

  if [ ! -f ".env" ]; then
    echo "ERROR: .env not found. Copy .env.example and fill in your values:"
    echo "  cp .env.example .env"
    exit 1
  fi

  echo "Building and starting containers..."
  docker compose up --build -d

  echo ""
  echo "  Containers running."
  echo "  URL:  http://localhost:${APP_PORT:-8000}"
  echo ""
  echo "  Useful commands:"
  echo "    bash start.sh docker-logs   # follow app logs"
  echo "    bash start.sh docker-stop   # stop all containers"
  echo "    docker compose ps           # container status"
  exit 0
fi

if [ "$MODE" = "docker-stop" ]; then
  docker compose down
  echo "Containers stopped."
  exit 0
fi

if [ "$MODE" = "docker-logs" ]; then
  docker compose logs -f app
  exit 0
fi

# ── Native mode (default) ─────────────────────────────────────────────────────

# Check .env exists
if [ ! -f ".env" ]; then
  echo "ERROR: .env not found. Copy .env.example and fill in your values:"
  echo "  cp .env.example .env"
  exit 1
fi

# Check dependencies
python3 -c "import flask, pymysql, httpx, lxml" 2>/dev/null || {
  echo "ERROR: Missing Python packages. Run:"
  echo "  sudo apt-get install -y python3-flask python3-pymysql"
  exit 1
}

# Check MariaDB is reachable
source <(grep -E '^(DB_HOST|DB_PORT|DB_USER|DB_PASSWORD|DB_NAME|APP_PORT)' .env 2>/dev/null || true)
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
APP_PORT="${APP_PORT:-8000}"

python3 -c "
import pymysql, sys
try:
    pymysql.connect(host='${DB_HOST}', port=${DB_PORT},
                    user='${DB_USER:-ozeki_app}', password='${DB_PASSWORD:-}',
                    database='${DB_NAME:-ozeki_app}', connect_timeout=3)
    print('DB OK')
except Exception as e:
    print(f'ERROR: Cannot connect to MariaDB: {e}')
    print('  Make sure MariaDB is running: sudo service mariadb start')
    sys.exit(1)
"

# Stop any existing instance
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping existing instance (PID $OLD_PID)..."
    kill "$OLD_PID"
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

# Start the app
echo "Starting Ozeki SMS app on port ${APP_PORT}..."
nohup python3 -m app.main > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

sleep 2

# Confirm it's up
if kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
  echo ""
  echo "  App running — PID $(cat $PID_FILE)"
  echo "  URL:  http://localhost:${APP_PORT}"
  echo "  Logs: tail -f $LOG_FILE"
  echo ""
  echo "  To stop:  kill \$(cat $PID_FILE)"
else
  echo "ERROR: App failed to start. Check logs:"
  echo "  cat $LOG_FILE"
  exit 1
fi
