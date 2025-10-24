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
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------------------
# 2. Set timezone
# -------------------------------------------------------------------
ENV TZ=${TZ:-UTC}
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
# For production without dev dependencies, uncomment:
#RUN poetry install --no-root --without dev

# -------------------------------------------------------------------
# 5. Copy application code 
# -------------------------------------------------------------------
COPY src ./src

# -------------------------------------------------------------------
# 6. Update PYTHONPATH so Python finds src/
# -------------------------------------------------------------------
ENV PYTHONPATH=/app/src:$PYTHONPATH

# -------------------------------------------------------------------
# 7. Default command (overridden by docker-compose)
# -------------------------------------------------------------------
CMD ["python", "-m", "network_autopilot.__main__"]
