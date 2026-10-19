FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# opencv-python-headless imports libgomp and libglib from the system image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies. The cascade check fails the build if the wheel
# does not contain the bundled face and plate models.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import cv2; from pathlib import Path; root = Path(cv2.data.haarcascades); assert (root / 'haarcascade_frontalface_default.xml').is_file(); assert (root / 'haarcascade_russian_plate_number.xml').is_file()"

# Copy source code
COPY . .

# Run with dynamic PORT (Render/Railway inject $PORT)
ENV PORT=8010
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
