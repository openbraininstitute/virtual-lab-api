# Prerequisites

Make sure you have the following dependencies installed:
- [python](https://www.python.org/downloads/) (version 3.12)
- [poetry](https://python-poetry.org/docs/#installation) (version >=1.5.1)
- [docker](https://docs.docker.com/engine/install/) - Add the docker group to your user to enable running docker without `sudo`. This can be done by running `sudo usermod -a -G <your username>` 
- [jq](https://jqlang.github.io/jq/download/)

# Development

1. Install the dependencies

   ```bash
   poetry install
   ```
2. Start dev environment

   ```bash
   make init
   ```
3. Run db migrations (this also initializes the database)
   ```
   make init-db
   ```

This should start the server on port 8000 (http://127.0.0.1:8000)
The docs will be available at http://127.0.0.1:8000/docs#/

# Retrieving tokens for test users

The token for user `test` (only user right now that can create virtual labs) is already copied to your clipboard when you run `make init`.
Tokens for user `test`, `test-1`, or `test-2` can also be retrieved using the script `get_user_token.sh`.
It echoes the token to the stdout as well as copies it to your clipboard.

```bash
./get_user_token.sh
# Now you will be prompted to enter a username. Valid usernames are `test`, `test-1`, or `test-2`. Example:
Enter username (test, test-1 or test-2)
-rtest-1
Access token:
<access_token>
```

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

# Testing

Tests can be run using the following command:
```
make test
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
