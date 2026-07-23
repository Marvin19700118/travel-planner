FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ agent/
COPY static/ static/
COPY main.py auth.py storage.py ./

# Cloud Run sets PORT; default matches `docker run -p 8080:8080` for local testing.
ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
