FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend codebase (including static web assets)
COPY backend/ .

# Expose port (default 8000)
EXPOSE 8000

# Start server using uvicorn, dynamically binding to the port set by the hosting environment
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
