# Base Image
FROM python:3.10.13-slim AS base

# Set working directory
WORKDIR /app

# =============================================
# 1. Install System Dependencies (single layer)
# =============================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential tzdata \
    && rm -rf /var/lib/apt/lists/*

# ==================
# Timezone handling:
# ==================
# The container timezone is driven exclusively by the $TZ variable from .env,
# not the host system’s localtime. This ensures consistent time across
# environments and makes deployment fully self-contained
#
# If you need to change timezone behavior, update the .env file:
#   TZ=Europe/London
#
# Python and system time will automatically reflect this setting

# Set timezone from build arg (default is UTC)
ARG TZ=UTC
ENV TZ=${TZ}

# Configure system clock and zoneinfo based on TZ
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone

# =========================================
# 2. Install Poetry inside Docker container
# =========================================
ENV POETRY_VERSION=2.1.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    PATH="/opt/poetry/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    poetry --version && \
    poetry config virtualenvs.create false && \
    poetry config virtualenvs.in-project false

# ======================================
# 3. Install Dependencies (cached layer)
# ======================================
COPY pyproject.toml poetry.lock* ./

# Default install (includes dev deps when POETRY_ENV=dev)
ARG POETRY_ENV=prod
RUN if [ "$POETRY_ENV" = "dev" ]; then \
        poetry install --no-root --no-interaction --no-ansi; \
    else \
        poetry install --no-root --no-interaction --no-ansi --without dev; \
    fi

# ========================
# 4. Copy Application Code
# ========================
COPY src ./src

# Make app code discoverable by Python
ENV PYTHONPATH=/app/src

# ===============================
# 5. Optimize runtime environment
# ===============================
# Disable .pyc files to reduce image size and keep mounts clean
ENV PYTHONDONTWRITEBYTECODE=1

# ==================
# 6. Default Command 
# ==================
CMD ["python", "-m", "update_dns.__main__"]
