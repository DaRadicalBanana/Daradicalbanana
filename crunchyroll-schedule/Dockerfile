# Container image for the Crunchyroll schedule app.
# Build context is this directory (crunchyroll-schedule/).
# Works on any container host (Render, Railway, Fly.io, Docker locally).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV APP_TIMEZONE=America/New_York
EXPOSE 8000

# Hosts inject $PORT; default to 8000 for local `docker run -p 8000:8000`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
