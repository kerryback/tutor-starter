# The home app: tutors.example.edu.  scripts/deploy-home.sh builds it from a
# folder holding home/'s files and engine/session_cookie.py beside them.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV HOME_DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
