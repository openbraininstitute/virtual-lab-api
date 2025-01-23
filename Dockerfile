FROM python:3.12-bookworm AS builder

RUN pip install poetry==1.4.2

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/vl-manager-app-cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry add psycopg2-binary

RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --without dev --no-root

FROM python:3.12-slim-bookworm AS runtime

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"


COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
WORKDIR /app

COPY ./virtual_labs /app/virtual_labs
COPY ./alembic /app/alembic

COPY ./docker-entrypoint.sh /app/
COPY ./alembic.ini /app/

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
