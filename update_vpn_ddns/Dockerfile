# Use an official Python runtime as a parent image
FROM python:3.10.13-slim

# Set working directory
WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files
COPY src/ ./src/

# Install cron and timezone data
RUN apt-get update && apt-get install -y cron tzdata

# Set the timezone inside the container
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Copy the cron job into the container
COPY cron/mycron /etc/cron.d/mycron

# Give proper permissions and apply cron job
RUN chmod 0644 /etc/cron.d/mycron && crontab /etc/cron.d/mycron

# Copy the entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose port if needed (not required for cron jobs)
# EXPOSE 8000

# Start the container with the entrypoint script
CMD ["/usr/local/bin/docker-entrypoint.sh"]
