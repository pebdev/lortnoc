FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for update script)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY lortnoc_client/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy directories maintaining structure
COPY config/ /app/config/
COPY lortnoc_core/ /app/lortnoc_core/
COPY lortnoc_client/ /app/lortnoc_client/
COPY resources/ /app/resources/

# Create data/log dir if needed
RUN mkdir -p /app/data

# Copy unified tools
COPY tools/scripts/ /app/tools/scripts/
RUN chmod +x /app/tools/scripts/*.sh

# Set PYTHONPATH explicitly to /app to make imports generic
ENV PYTHONPATH="/app"

# Run the update/launch script
CMD ["/app/tools/scripts/run.sh", "client"]
