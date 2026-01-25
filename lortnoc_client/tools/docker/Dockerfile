FROM python:3.11-slim

WORKDIR /app

# Install dependencies both for client and core (if any extra)
COPY lortnoc_client/tools/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy directories
# We mount them in a way that respects the relative imports if running from root,
# but here we are constructing a standalone env.
# The client main.py adds its parent dir to sys.path.
# If main.py is in /app/sources/, parent is /app/.
# So lortnoc_core should be in /app/lortnoc_core/

COPY config/ /app/config/
COPY lortnoc_core/ /app/lortnoc_core/
COPY lortnoc_client/sources/ /app/sources/

# Create data/log dir if needed
RUN mkdir -p /app/data

# Set PYTHONPATH explicitly to /app to make imports generic
ENV PYTHONPATH="/app"

CMD ["python", "sources/main.py"]
