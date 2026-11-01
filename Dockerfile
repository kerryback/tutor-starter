# One tutor's image.  scripts/deploy.sh builds it from a folder holding
# engine/, instructions/ and the tutor's own folder copied to tutor/.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine/ engine/
COPY instructions/ instructions/
COPY tutor/ tutor/
RUN if [ -f tutor/requirements.txt ]; then pip install --no-cache-dir -r tutor/requirements.txt; fi
ENV DATA_DIR=/data TUTOR_DIR=/app/tutor INSTRUCTIONS_DIR=/app/instructions VOICE_ENABLED=1
WORKDIR /app/engine
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
