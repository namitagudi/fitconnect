FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p models && python -c "import urllib.request as u; u.urlretrieve('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task','models/pose_landmarker_full.task')"
ENV PORT=8000 COOKIE_SECURE=1
# One worker: the pose model is loaded once and rate limits are kept in memory.
CMD ["sh","-c","python seed.py && gunicorn -w 1 --threads 4 -b 0.0.0.0:${PORT} 'gym:create_app()'"]
