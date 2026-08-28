FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY services/graph-detector/requirements.txt /tmp/graph-requirements.txt
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --default-timeout=1000 -r /tmp/graph-requirements.txt


COPY services/graph-detector /workspace/services/graph-detector
COPY data/normal/transactions.json /workspace/data/normal/transactions.json
COPY data/attack/transactions.json /workspace/data/attack/transactions.json
WORKDIR /workspace/services/graph-detector
EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
