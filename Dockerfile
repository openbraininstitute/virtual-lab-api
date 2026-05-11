# syntax=docker/dockerfile:1.9
ARG UV_VERSION=latest
ARG PYTHON_VERSION=3.12
ARG PYTHON_BASE=${PYTHON_VERSION}-slim-bookworm

# uv stage
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# build stage
FROM python:${PYTHON_BASE} AS builder

SHELL ["bash", "-e", "-x", "-o", "pipefail", "-c"]

RUN <<EOT
apt-get update -qy
apt-get install -qyy \
  -o APT::Install-Recommends=false \
  -o APT::Install-Suggests=false \
  gcc \
  libc6-dev \
  libpq-dev
EOT

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python${PYTHON_VERSION}

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# run stage
FROM python:${PYTHON_BASE}

SHELL ["bash", "-e", "-x", "-o", "pipefail", "-c"]

RUN <<EOT
apt-get update -qy
apt-get install -qyy \
  -o APT::Install-Recommends=false \
  -o APT::Install-Suggests=false \
  libpq5
apt-get clean
rm -rf /var/lib/apt/lists/*
EOT

RUN <<EOT
groupadd -r app
useradd -r -d /app -g app -N app
EOT

USER app
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=app:app --from=builder /app/.venv/ .venv/
COPY --chown=app:app alembic.ini docker-entrypoint.sh ./
COPY --chown=app:app alembic/ alembic/
COPY --chown=app:app virtual_labs/ virtual_labs/

RUN python -m compileall virtual_labs/ alembic/

RUN <<EOT
python -V
python -m site
python -c 'import virtual_labs'
EOT

EXPOSE 8000

STOPSIGNAL SIGINT
ENTRYPOINT ["./docker-entrypoint.sh"]
