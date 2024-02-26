# Development

0. Make sure you have [poetry installed](https://python-poetry.org/docs/#installation)

1. Install the dependencies

```
poetry install
```

2. Start the server
```
poetry run uvicorn virtual_labs.api:app --reload
```

This should start the server on port 8000 (http://127.0.0.1:8000)
The docs will be available at http://127.0.0.1:8000/docs#/

# IDE Setup

## VS Code

1. Make sure that VSCode is picking up the right python version. This should look like `~/.cache/pypoetry/virtualenvs/virtual-labs[uuid]...`
2. You might want to install the Ruff extension for vscode (extension_id - charliermarsh.ruff)