FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY verdict verdict
RUN pip install --no-cache-dir .
CMD ["uvicorn", "verdict.main:app", "--host", "0.0.0.0", "--port", "8000"]
