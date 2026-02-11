FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code (also bind-mounted at runtime for editing)
COPY src/ /app/src/
COPY config/ /app/config/
COPY scripts/ /app/scripts/
COPY data/styles/ /app/data/styles/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 7777

CMD ["python", "-m", "medical_mcp.sse_server", "--host", "0.0.0.0", "--port", "7777"]
