FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONPATH=/app/backend

WORKDIR /app

# Install system dependencies for OpenCV, PyTesseract, and Postgres
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    gcc \
    libpq-dev \
    curl \
    ca-certificates \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# facenet-pytorch's declared pins (torch<2.3, numpy<2, Pillow<10.3) are stale and
# conflict with the modern versions installed above; its actual code runs fine
# against them (verified in scripts/calibrate_face_threshold.py), so install
# without pulling its dependency constraints.
RUN pip install --no-cache-dir --no-deps facenet-pytorch>=2.6.0

# Copy backend code, scripts, and demo datasets
COPY backend ./backend
COPY scripts ./scripts
COPY demo-data ./demo-data

# Bake the pretrained VGGFace2 face-embedding weights (~107MB) into the image at
# build time, so the container needs internet only once (here), never at runtime.
RUN python -c "from facenet_pytorch import InceptionResnetV1; InceptionResnetV1(pretrained='vggface2').eval()"

# Ensure upload and storage directories exist
RUN mkdir -p /app/uploads/documents /app/uploads/faces /app/uploads/heatmaps /app/uploads/crops

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
