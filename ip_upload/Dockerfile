# Use an official Python runtime as a parent image
FROM python:3.10.13-slim

# Install cron
RUN apt-get update && apt-get install -y cron

# Set working directory
WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Cron placeholder 

# Copy cron file 
# COPY cron/mycron /etc/cron.d/mycron
# RUN chmod 0644 /etc/cron.d/mycron && crontab /etc/cron.d/mycron

# Copy the entrypoint script
# COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose port if needed (not required for cron jobs)
# EXPOSE 8000

# Default command: run our custom entrypoint script
# CMD ["docker-entrypoint.sh"]
