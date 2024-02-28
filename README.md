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
3. add envirement variables
    ```sh
    DATABASE_URL = "postgresql://vlm:vlm@localhost:15432/vlm"
    ```
4. Start the server

   ```sh
   make dev
   ```

   or

   ```sh
   poetry run uvicorn virtual_labs.api:app --reload
   ```

This should start the server on port 8000 (http://127.0.0.1:8000)
The docs will be available at http://127.0.0.1:8000/docs#/

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

- Static type checks (using mypy)
- Formatting (using ruff)
- Linting (using ruff)
