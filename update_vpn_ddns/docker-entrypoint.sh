#!/bin/bash
set -e

CRON_ENABLED=${CRON_ENABLED:-false}

# Ensure PYTHONPATH includes the src directory
export PYTHONPATH=/app/src:$PYTHONPATH

if [ "$CRON_ENABLED" = "true" ]; then
  echo "Starting cron daemon..."

  # Ensure cron logs are written to a file
  touch /var/log/cron.log
  tail -f /var/log/cron.log &    # Keep logs visible

  # Start cron service in the foreground, keep Docker container alive
  cron -f
else
  echo "CRON disabled. Running script once"
  python -m update_vpn_ddns.__main__
  #/usr/local/bin/python /app/src/update_vpn_ddns/update_vpn_ddns.py
  #poetry run python /app/src/update_vpn_ddns.py
fi
