# Use an official Python runtime as a parent image
FROM python:3.10.13-slim

# Set working directory
WORKDIR /app

# -------------------------------------------------------------------
# 1. Install system dependencies (single layer)
# -------------------------------------------------------------------
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    cron \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------------------
# 2. Set timezone
# -------------------------------------------------------------------
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# -------------------------------------------------------------------
# 3. Install Poetry
# -------------------------------------------------------------------
ENV POETRY_VERSION=2.1.2
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Make Poetry avoid virtualenvs for Docker
RUN poetry config virtualenvs.create false

# -------------------------------------------------------------------
# 4. Install Python dependencies (cached and no dev deps in prod)
# -------------------------------------------------------------------
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-interaction --no-ansi --no-root
#RUN poetry install --no-interaction --no-ansi --no-root --without dev
#RUN poetry install --no-root --without dev

# -------------------------------------------------------------------
# 5. Copy application code and cron configs
# -------------------------------------------------------------------
COPY src ./src
COPY cron/mycron /etc/cron.d/mycron
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# -------------------------------------------------------------------
# 6. Permissions and cron setup
# -------------------------------------------------------------------
RUN chmod 0644 /etc/cron.d/mycron \
    && crontab /etc/cron.d/mycron \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# -------------------------------------------------------------------
# 7. Entrypoint
# -------------------------------------------------------------------
CMD ["/usr/local/bin/docker-entrypoint.sh"]