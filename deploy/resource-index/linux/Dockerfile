ARG PYTHON_IMAGE=python:3.11.9-slim-bookworm
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONPATH=/app

WORKDIR /app
COPY deploy/resource-index/requirements.txt /tmp/resource-index-requirements.txt
RUN pip install --no-cache-dir -r /tmp/resource-index-requirements.txt

COPY magnet /app/magnet
COPY deploy/resource-index /app/deploy/resource-index

ENTRYPOINT ["python", "-m", "magnet.resource_index"]
