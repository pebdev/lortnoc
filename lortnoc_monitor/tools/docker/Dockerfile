FROM python:3.11-slim

WORKDIR /app

COPY lortnoc_monitor/tools/docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*

COPY config/ /app/config/
COPY lortnoc_core/ /app/lortnoc_core/
COPY lortnoc_monitor/sources/ /app/sources/
COPY resources/ /app/resources/
RUN mkdir -p /app/data

ENV PYTHONPATH="/app"
EXPOSE 8080

CMD ["python", "sources/main.py"]
