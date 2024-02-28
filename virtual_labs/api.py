from fastapi import FastAPI
from .routes.projects import projects

app = FastAPI()
app.include_router(projects)
