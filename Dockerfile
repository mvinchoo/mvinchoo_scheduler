FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files (actions.py, logger.py, packages, etc.)
COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["python", "/app/scheduler.py"]