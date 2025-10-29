# Base Image
FROM python:3.10.13-slim AS base

# Set working directory
WORKDIR /app

# ------------------------------
# 1. Install System Dependencies
# ------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone (default UTC unless overridden)
# ENV TZ=${TZ:-UTC}
# RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# -----------------------------------------
# 2. Install Poetry inside Docker container
# -----------------------------------------
ENV POETRY_VERSION=2.1.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    PATH="/opt/poetry/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    poetry --version && \
    poetry config virtualenvs.create false && \
    poetry config virtualenvs.in-project false

# --------------------------------------
# 3. Install Dependencies (cached layer)
# --------------------------------------
COPY pyproject.toml poetry.lock* ./

# Default install (includes dev deps when POETRY_ENV=dev)
ARG POETRY_ENV=prod
RUN if [ "$POETRY_ENV" = "dev" ]; then \
        poetry install --no-root --no-interaction --no-ansi; \
    else \
        poetry install --no-root --no-interaction --no-ansi --without dev; \
    fi

# ------------------------
# 4. Copy Application Code
# ------------------------
COPY src ./src

# Make app code discoverable by Python
ENV PYTHONPATH=/app/src

# -------------------------------
# 5. Optimize runtime environment
# -------------------------------
# Disable .pyc files to reduce image size and keep mounts clean
ENV PYTHONDONTWRITEBYTECODE=1

# -------------------------------------------------
# 6. Default Command (overridden by docker-compose)
# -------------------------------------------------
CMD ["python", "-m", "network_autopilot.__main__"]






# # Use an official Python runtime as a parent image
# FROM python:3.10.13-slim

# # Set working directory
# WORKDIR /app

# # -------------------------------------------------------------------
# # 1. Install system dependencies (single layer)
# # -------------------------------------------------------------------
# RUN apt-get update && apt-get install -y \
#     curl \
#     build-essential \
#     tzdata \
#     && rm -rf /var/lib/apt/lists/*

# # -------------------------------------------------------------------
# # 2. Set timezone
# # -------------------------------------------------------------------
# ENV TZ=${TZ:-UTC}
# RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# # -------------------------------------------------------------------
# # 3. Install Poetry
# # -------------------------------------------------------------------
# ENV POETRY_VERSION=2.1.2
# RUN curl -sSL https://install.python-poetry.org | python3 -
# ENV PATH="/root/.local/bin:$PATH"

# # Make Poetry avoid virtualenvs for Docker
# RUN poetry config virtualenvs.create false

# # -------------------------------------------------------------------
# # 4. Install Python dependencies (cached and no dev deps in prod)
# # -------------------------------------------------------------------
# COPY pyproject.toml poetry.lock* ./
# RUN poetry install --no-interaction --no-ansi --no-root
# # For production without dev dependencies, uncomment:
# #RUN poetry install --no-root --without dev

# # -------------------------------------------------------------------
# # 5. Copy application code 
# # -------------------------------------------------------------------
# COPY src ./src

# # -------------------------------------------------------------------
# # 6. Update PYTHONPATH so Python finds src/
# # -------------------------------------------------------------------
# ENV PYTHONPATH=/app/src:$PYTHONPATH

# # -------------------------------------------------------------------
# # 7. Default command (overridden by docker-compose)
# # -------------------------------------------------------------------
# CMD ["python", "-m", "network_autopilot.__main__"]
