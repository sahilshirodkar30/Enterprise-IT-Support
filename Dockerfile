
FROM python:3.13-slim

# Python environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Working directory inside the container
WORKDIR /srv

# Install dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && useradd -r -u 10001 enterpriseai

# Copy application folders
COPY app ./app
COPY frontend ./frontend

# Run as non-root user
USER enterpriseai

# FastAPI and Streamlit ports
EXPOSE 8000 8501

# Default command: FastAPI
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
