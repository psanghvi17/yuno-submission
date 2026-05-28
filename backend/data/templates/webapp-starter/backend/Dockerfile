FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Keep backend code under /app/backend and frontend assets under /app/frontend
# so main.py can mount ../frontend when present.
COPY backend/ ./backend/
COPY frontend/ ./frontend/
ENV DATABASE_PATH=/data/app.db
EXPOSE 8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
