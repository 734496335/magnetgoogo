ARG PYTHON_IMAGE=python:3.11.9-slim-bookworm
FROM ${PYTHON_IMAGE}
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONPATH=/app

WORKDIR /app
COPY deploy/resource-index/requirements.txt /tmp/resource-index-requirements.txt
RUN python -m pip install \
    --no-cache-dir \
    --index-url "$PIP_INDEX_URL" \
    -r /tmp/resource-index-requirements.txt

COPY magnet /app/magnet
COPY deploy/resource-index /app/deploy/resource-index

ENTRYPOINT ["python", "-m", "magnet.resource_index"]
