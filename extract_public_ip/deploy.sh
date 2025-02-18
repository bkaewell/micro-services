#!/bin/bash

# Define base directories
REPO_BASE=~/repo/automation-scripts
DEPLOY_BASE=~/deployed_scripts

# Set the subdirectory for the specific script
SCRIPT_SUBDIR=extract_public_ip

# Define the full paths for the repository and deployed script directories
REPO_DIR="$REPO_BASE/$SCRIPT_SUBDIR"
DEPLOY_DIR="$DEPLOY_BASE/$SCRIPT_SUBDIR"

# Ensure the base deployment directory exists
if [ ! -d "$DEPLOY_BASE" ]; then
    echo "Base deployment directory '$DEPLOY_BASE' does not exist. Creating it..."
    mkdir -p "$DEPLOY_BASE"
fi

# Check if the specific deployment directory exists, otherwise create it
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
rsync -av \
    --exclude='.env' \
    --exclude='README.md' \
    --exclude='requirements.txt' \
    --exclude='logs' \
    --exclude='cron_job' \
    --exclude='deploy.sh' \
    "$REPO_DIR/" "$DEPLOY_DIR/"

# Check if the .env file exists in the deployed folder; if not, copy the .env.example over
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    echo "No .env found in '$DEPLOY_DIR'. Copying .env.example to .env..."
    cp "$REPO_DIR/.env.example" "$DEPLOY_DIR/.env"
    echo "Copied .env.example to deployed directory."
else
    echo ".env file already exists in '$DEPLOY_DIR'. Skipping copy."
fi

# Copy the cron job file from the repository to the deployment's cron_job subdirectory.
CRON_SOURCE="$REPO_DIR/extract_public_ip_address.cron"
CRON_DEST="$DEPLOY_DIR/cron_job/extract_public_ip_address.cron"
if [ -f "$CRON_SOURCE" ]; then
    cp "$CRON_SOURCE" "$CRON_DEST"
    echo "Cron job file copied to '$DEPLOY_DIR/cron_job'."
else
    echo "No cron job file found in the repository at '$CRON_SOURCE'."
fi

# Automatically load the cron job from the deployed cron_job directory if the file exists.
if [ -f "$CRON_DEST" ]; then
    echo "Installing cron job from '$CRON_DEST'..."
    crontab "$CRON_DEST"
    echo "Cron job installed."
else
    echo "No cron job file found at '$CRON_DEST'. Skipping cron job installation."
fi

echo "Deployment complete."
