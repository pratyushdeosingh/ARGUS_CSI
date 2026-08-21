FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARGUS_EBPF_MODE=replay

WORKDIR /workspace/services/ebpf-detector

COPY services/ebpf-detector/requirements.txt /tmp/ebpf-requirements.txt
RUN pip install --no-cache-dir -r /tmp/ebpf-requirements.txt

COPY services/ebpf-detector /workspace/services/ebpf-detector

EXPOSE 8002

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8002"]
