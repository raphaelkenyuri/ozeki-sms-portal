#!/usr/bin/env bash
# Bundles the app into a tarball for transfer to another machine.
# On the target machine: tar -xzf ozeki-sms-app.tar.gz && cd ozeki && docker compose up --build -d

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ARCHIVE="ozeki-sms-app.tar.gz"

echo "Packaging app into $ARCHIVE ..."

tar -czf "../$ARCHIVE" \
  --exclude='.env' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude="$ARCHIVE" \
  -C .. \
  ozeki/

echo ""
echo "  Created: $(cd .. && realpath $ARCHIVE)"
echo ""
echo "  Transfer to target machine, then:"
echo "    tar -xzf $ARCHIVE"
echo "    cd ozeki"
echo "    cp .env.example .env   # fill in your values"
echo "    docker compose up --build -d"
