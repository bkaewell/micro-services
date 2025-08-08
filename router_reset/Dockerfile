FROM python:3.9-slim
WORKDIR /app
COPY src/ ./src/
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh
ENTRYPOINT ["./docker-entrypoint.sh"]

