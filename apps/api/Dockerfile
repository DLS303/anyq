FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Run with dynamic PORT (Render/Railway inject $PORT)
ENV PORT=8010
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
