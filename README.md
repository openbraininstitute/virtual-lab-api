# Development

0. Make sure you have [poetry installed](https://python-poetry.org/docs/#installation)
1. Install the dependencies

   ```sh
   poetry install
   ```
2. Start keycloak and local database

   ```sh
   make init # this is will start keycloak instance and local database
   ```
3. Run db migrations
   ```
   make init-db
   ```
4. Start the server. This will apply migrations and start the server.

   ```sh
   make dev
   ```

This should start the server on port 8000 (http://127.0.0.1:8000)
The docs will be available at http://127.0.0.1:8000/docs#/

# Generating db migrations

The version numbers are stored in alembic/versions. Alembic can be used to autogenerate migration scripts based on schema changes like so:

```
poetry run alembic revision --autogenerate -m '<A descriptive message>'
```
Note that these migration scripts *should* be reviewed carefully. Also, not all schema changes can be autogerated. Details about which schema changes need scripts to be written manually are [here](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect).

Migration can be run like so:
```
poetry run alembic upgrade head
```

To check if migration is needed (same as above, alembic cannot check all schema changes):
```
make check-db-schema
```

# IDE Setup

## VS Code

1. Make sure that VSCode is picking up the right python version. This should look like `~/.cache/pypoetry/virtualenvs/virtual-labs[uuid]...`
2. Recommended extensions:
    - Ruff (extension_id - charliermarsh.ruff)
    - MyPy Type Checker (extension_id: ms-python.mypy-type-checker)

# Contributing

To create an MR and push code to it, you will need to setup git-hooks *only the first time you push code to the repo*.

1. Install git hooks to enable pre-push checks
```
poetry run pre-commit install
```

This will setup a git hook (pre-push) that is configured to run the following checks.

- Formatting (using ruff)
- Linting (using ruff)
