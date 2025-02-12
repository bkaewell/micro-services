#!/bin/bash

# Define directories
REPO_DIR=~/repo/automation-scripts/extract_public_ip
DEPLOY_DIR=~/deployed_extract_public_ip

# Check if DEPLOY_DIR exists, otherwise create it
if [ -d "$DEPLOY_DIR" ]; then
    echo "Deployment directory '$DEPLOY_DIR' already exists. Updating files..."
else
    echo "Deployment directory '$DEPLOY_DIR' does not exist. Creating it..."
    mkdir -p "$DEPLOY_DIR"
fi

# Create the logs sub-directory if it doesn't exist
if [ ! -d "$DEPLOY_DIR/logs" ]; then
    mkdir -p "$DEPLOY_DIR/logs"
    echo "Logs directory created at '$DEPLOY_DIR/logs'."
else
    echo "Logs directory already exists at '$DEPLOY_DIR/logs'."
fi

# Create the cron_job sub-directory if it doesn't exist
if [ ! -d "$DEPLOY_DIR/cron_job" ]; then
    mkdir -p "$DEPLOY_DIR/cron_job"
    echo "Cron job directory created at '$DEPLOY_DIR/cron_job'."
else
    echo "Cron job directory already exists at '$DEPLOY_DIR/cron_job'."
fi

# Sync code from the repo to the deployed area, excluding production-specific files
rsync -av --exclude='.env' --exclude='logs' "$REPO_DIR/" "$DEPLOY_DIR/"

# Check if the .env file exists in the deployed folder; if not, copy the .env.example over
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    echo "No .env found in '$DEPLOY_DIR'. Copying .env.example ..."
    cp "$REPO_DIR/.env.example" "$DEPLOY_DIR/.env"
    echo "Copied .env.example to deployed directory."
else
    echo ".env file already exists in '$DEPLOY_DIR'. Skipping copy."
fi

echo "Deployment complete."
