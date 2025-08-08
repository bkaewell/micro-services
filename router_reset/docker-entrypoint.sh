#!/bin/bash
if [ "$1" = "cron" ]; then
  echo "Starting cron mode..."
  crond -f
else
  echo "Running manual reset..."
  python src/reset_router.py
fi

