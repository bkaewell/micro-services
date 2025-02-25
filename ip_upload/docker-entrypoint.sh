#!/bin/bash

# Exit on error
set -e

# Load environment variables from .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ "$CRON_ENABLED" = "true" ]; then
  echo "Starting cron daemon..."

  # Ensure cron logs are written to a file
  touch /var/log/cron.log
  tail -f /var/log/cron.log &  # Keep logs visible
  
  # Start cron service in the foreground, keep Docker container alive
  cron -f
else
  echo "CRON disabled. Running script once."
  /usr/local/bin/python /app/src/ip_upload.py
fi
