# Development

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
