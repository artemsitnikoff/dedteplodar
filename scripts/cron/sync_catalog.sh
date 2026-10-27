#!/usr/bin/env bash
# Nightly catalog sync — install on the HOST crontab (not inside a container):
#
#   crontab -e
#   30 4 * * * /var/www/dedteplodar/scripts/cron/sync_catalog.sh
#
# Runs scripts/sync_catalog.py inside the `admin` container (it has torch, the
# E5 cache volume and base/). The script takes its own lock, so overlapping
# with the admin "Обновить каталог" button is harmless (the second one exits
# as "skipped"). Output: logs/catalog_sync.log; a Telegram summary goes to
# OPERATOR_CHAT_ID (--notify). The feed URL comes from YANDEX_YML_URL in .env.
set -u
cd "$(dirname "$(readlink -f "$0")")/../.." || exit 1
mkdir -p logs
LOG=logs/catalog_sync.log
# crude size rotation: keep one previous file
if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt 5000000 ]; then
  mv -f "$LOG" "$LOG.1"
fi
{
  echo "=== $(date -Is) catalog sync start ==="
  docker compose exec -T admin python scripts/sync_catalog.py --notify
  echo "=== $(date -Is) catalog sync exit=$? ==="
} >> "$LOG" 2>&1
