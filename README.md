# Virtual Labs API

REST API used to manage virtual labs and their projects

The service is an async FastAPI application backed by PostgreSQL (async SQLAlchemy + Alembic), Redis, Keycloak (OIDC), Stripe (billing & subscriptions), Mailpit (local SMTP). It is packaged and run with [`uv`](https://docs.astral.sh/uv/) and orchestrated locally via Docker Compose.

---

## Table of contents

- [Stack & requirements](#stack--requirements)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Environment configuration](#environment-configuration)
- [Common Make targets](#common-make-targets)
- [Authentication & test users](#authentication--test-users)
- [Keycloak admin UI](#keycloak-admin-ui)
- [Database & migrations](#database--migrations)
- [Testing](#testing)
- [Billing / Stripe testing](#billing--stripe-testing)
- [Operational scripts](#operational-scripts)
- [Code quality](#code-quality)
- [IDE setup](#ide-setup)
- [Contributing](#contributing)
- [Funding & acknowledgment](#funding--acknowledgment)

---

## Stack & requirements

| Tool | Version | Notes |
| ---- | ------- | ----- |
| Python | `>=3.12,<4` | Project targets 3.12 (also tested against 3.13/3.14) |
| [`uv`](https://docs.astral.sh/uv/getting-started/installation/) | latest | Package + virtualenv manager (replaces Poetry) |
| Docker + Docker Compose | latest | Brings up Postgres, Redis, Keycloak (+ its DB), Mailpit, and a Stripe CLI listener |
| [`jq`](https://jqlang.github.io/jq/download/) | any | Used by helper scripts |
| Stripe CLI | optional | For local webhook / Setup Intent testing |

Key runtime dependencies (see [pyproject.toml](pyproject.toml) for the full list): `fastapi[all]`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic` v2, `pydantic-settings`, `python-keycloak`, `pyjwt`, `stripe`, `fastapi-mail`, `redis`, `loguru`, `sentry-sdk[fastapi]`, `obp-accounting-sdk`.

> Make sure your user is in the `docker` group so Docker commands don't require `sudo`:
> ```bash
> sudo usermod -aG docker "$USER"
> ```

---

## Repository layout

```
virtual_labs/
├── api.py              # FastAPI app factory, middleware, exception handlers, router wiring
├── routes/             # HTTP layer — one module per domain (labs, projects, billing, …)
├── usecases/           # Application use-cases orchestrating services + repositories
├── services/           # Domain services (Stripe, Keycloak, email, accounting, …)
├── repositories/       # Async SQLAlchemy data access
├── domain/             # Pydantic schemas / domain models (request/response DTOs)
├── infrastructure/     # DB session pool, Redis client, settings, transport, kc, email
├── core/               # Cross-cutting primitives: exceptions, response schemas, auth
├── external/           # Adapters for third-party systems
├── shared/             # Shared utilities
├── static/             # Static assets (email templates, etc.)
├── utils/              # Generic helpers
└── tests/              # Pytest suite (async, integration markers)
alembic/                # Alembic env + versioned migrations
scripts/                # One-off and operational scripts (subscription tiers, bulk invite, …)
env-prep/               # Keycloak realm export + seed data used by dev-init.sh
```

The router wiring lives in [virtual_labs/api.py](virtual_labs/api.py). All routers are mounted under `settings.BASE_PATH`, and OpenAPI docs are exposed at `{BASE_PATH}/docs`.

---

## Quick start

```bash
# 1. Install uv (one-time): https://docs.astral.sh/uv/getting-started/installation/

# 2. Install Python deps into a managed virtualenv
make install            # equivalent to: uv sync

# 3. Create your local env file (see Environment configuration below)
#    Use the committed `.env.development` as a starting point:
cp .env.development .env.local

# 4. Bring up infra + app
make init

# 5. Initialize / migrate the database
make init-db

# 6. Run the API in reload mode against the running stack (optional)
make dev
```

The API will be available at `http://127.0.0.1:8000` and the interactive docs at `http://127.0.0.1:8000/docs`.

---

## Environment configuration

The service reads configuration from `.env.local` (loaded by `dev-init.sh` and `make init`). The repo ships [.env.development](.env.development) with the non-secret defaults that match `docker-compose.yml` — use it as a starting template and fill in your own Stripe / Sentry / Keycloak secrets locally.

The authoritative list of supported settings (with defaults and types) lives in [virtual_labs/infrastructure/settings.py](virtual_labs/infrastructure/settings.py). Common groups:

- **App**: `APP_NAME`, `APP_DEBUG`, `DEPLOYMENT_ENV`, `BASE_PATH`, `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`
- **Database**: async SQLAlchemy URI (`postgresql+asyncpg://…`)
- **Keycloak**: `KC_SERVER_URI`, `KC_REALM_NAME`, `KC_CLIENT_ID`, `KC_CLIENT_SECRET`
- **Redis**: host / port / credentials
- **Stripe**: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_DEVICE_NAME`, `STRIPE_API_VERSION`, tax-billing flags (`BILLING_TAX_ENABLED`, `BILLING_TAX_ENABLED_COUNTRIES`, `BILLING_TAX_BEHAVIOR`, `BILLING_TAX_MISSING_COUNTRY_MODE`)
- **Sentry**: `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE`

---

## Common Make targets

Run `make help` (or simply `make`) to print this list in your terminal — every target's description below comes straight from the inline `## …` annotations in the [Makefile](Makefile), so it always reflects the truth.

```console
$ make help
help                    Show this help
install                 Install all dependencies
upgrade-deps            Upgrade all dependencies to latest compatible versions
check-deps              Check lock file is up to date
audit                   Run package auditing
dev                     Run development api server
init                    Run project with .env.local file (for local development)
init-ci                 Run project without env file (for CI/CD environments)
destroy                 Destroy project containers (with .env.local)
destroy-ci              Destroy project containers (without env file)
build                   Build the Docker image
format                  Run formatters and auto-fix linting issues
lint                    Run linters (check only, no modifications)
style-check             Run pre-commit style checks
type-check              Run static type checks
check-all               Run format, lint, style-check and type-check
test                    Run tests
init-db                 Create & seed db tables
check-db-schema         Check if db schema change requires a migration
migration               Create or update the alembic migration
tiers                   Populate subscription tiers
```

A few of the most common targets in context:

- **First-time setup:** `make install && make init && make init-db`
- **Day-to-day:** `make dev` (reload server), `make test`, `make check-all` before pushing
- **Migrations:** `make migration MESSAGE="…"` to autogenerate, `make init-db` to apply
- **Reset the stack:** `make destroy` (drops containers + volumes)

---

## Authentication & test users

The dev stack ships with a Keycloak realm (`obp-realm`) populated by [env-prep/realm-export.json](env-prep/realm-export.json).

`make init` automatically copies the token for user `test` (the user allowed to create virtual labs) to your clipboard.

You can also fetch a token at any time:

```bash
./get_user_token.sh
# Prompts for username — valid values: test, test-1, test-2
```

The token is both printed to stdout and copied to your clipboard.

---

## Keycloak admin UI

The Keycloak container is exposed on host port `9090` with `--hostname-admin=http://localhost:9090`, so the admin console is reachable out of the box at:

- URL: `http://localhost:9090`
- Username / password: `admin` / `admin` (see [docker-compose.yml](docker-compose.yml))
- Realm used by the API: `obp-realm` (seeded from [env-prep/realm-export.json](env-prep/realm-export.json))

---

## Database & migrations

Migrations live in [alembic/versions](alembic/versions). Alembic config is in [alembic.ini](alembic.ini).

**Generate a new migration** (autogenerated from model changes):

```bash
make migration MESSAGE="add foo column to virtual_labs"
# or directly:
uv run alembic revision --autogenerate -m "add foo column"
```

> Always review autogenerated migrations. Alembic cannot detect every schema change — see the [autogenerate caveats](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect).

**Apply migrations:**

```bash
make init-db
# or:
uv run alembic upgrade head
```

**Check whether a migration is required:**

```bash
make check-db-schema
```

---

## Testing

Run the full suite (also populates test subscription tiers first):

```bash
make test
```

Run a subset directly:

```bash
uv run pytest virtual_labs/tests/path/to/test_file.py -k some_test -x
```

Integration tests are marked with `@pytest.mark.integration` (see `pyproject.toml`).

---

## Billing / Stripe testing

The `STRIPE_SECRET_KEY` test key and `STRIPE_DEVICE_NAME=dev` must be present in `.env.local`. Swiss VAT / tax-billing knobs are documented in [SUBSCRIPTION.md](SUBSCRIPTION.md) and the `BILLING_TAX_*` settings.

### Setup Intents (attaching payment methods)

Attaching a payment method is normally a frontend flow (`stripe.confirmSetup()`). To test from the backend manually:

1. Create a Setup Intent via `POST /virtual-labs/{virtual_lab_id}/billing/setup-intent`.
2. Confirm it through the Stripe CLI:

```sh
stripe setup_intents confirm seti_1PFtBwFjhkSGAqrAUHCvTAAA \
  --payment-method=pm_card_visa
```

References: [Stripe Setup Intents](https://stripe.com/docs/api/setup_intents) · [Stripe CLI](https://stripe.com/docs/stripe-cli).

---

## Operational scripts

Installed as `uv run` entrypoints (defined in [pyproject.toml](pyproject.toml)):

| Command | Purpose |
| ------- | ------- |
| `uv run populate-tiers` | Seed/refresh subscription tiers (`--test` for test mode) — [scripts/populate_subscription_tiers.py](scripts/populate_subscription_tiers.py) |
| `uv run upgrade-subscription` | Upgrade an existing subscription — [scripts/upgrade_subscription.py](scripts/upgrade_subscription.py) |
| `uv run send_emails` | Send templated emails — [scripts/send_emails.py](scripts/send_emails.py) |
| `uv run manage-coupons` | Manage Stripe coupons — [scripts/manage_stripe_coupons.py](scripts/manage_stripe_coupons.py) |
| `uv run bulk-invite` | Bulk-invite users to a project — [scripts/bulk_invite_to_project.py](scripts/bulk_invite_to_project.py) |
| `uv run migrate-tax-billing` | One-off migration to the tax-billing model — [scripts/migrate_to_tax_billing.py](scripts/migrate_to_tax_billing.py) |

---

## Code quality

- **Formatting & linting:** [Ruff](https://docs.astral.sh/ruff/) — `make format` / `make lint`
- **Static typing:** [`ty`](https://docs.astral.sh/ty/) — `make type-check` (config in `pyproject.toml`)
- **Pre-commit hooks:** ruff format + ruff lint on push

Install hooks once after cloning:

```bash
uv run pre-commit install
```

CI runs `style-check` against `.pre-commit-config-ci.yaml`.

---

## IDE setup

### VS Code

1. Point the Python interpreter at the uv-managed venv: `.venv/bin/python` in the project root (created by `uv sync`).
2. Recommended extensions:
   - **Ruff** (`charliermarsh.ruff`)
   - **Python** (`ms-python.python`)

The project uses [`ty`](https://docs.astral.sh/ty/) (configured in `pyproject.toml`) as the type checker — invoke it via `make type-check`.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

1. Branch off `main`.
2. `uv run pre-commit install` (first time only).
3. Keep PRs focused; include tests where reasonable.
4. Run `make check-all` and `make test` before opening a PR.

---

## Funding & acknowledgment

The development of this software was supported by funding to the Blue Brain Project, a research center of the École polytechnique fédérale de Lausanne (EPFL), from the Swiss government's ETH Board of the Swiss Federal Institutes of Technology.

Copyright © 2024 Blue Brain Project/EPFL
Copyright © 2025 Open Brain Institute
