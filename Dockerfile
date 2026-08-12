FROM python:3.11-slim

WORKDIR /app

# Install dependencies
# Pass --build-arg HTTP_PROXY=http://proxy:port if you're behind a proxy
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# Copy application code
COPY app/ ./app/
COPY schema.sql .

EXPOSE 8000

CMD ["python3", "-m", "app.main"]
