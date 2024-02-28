from fastapi import FastAPI
from .routes.projects import projects

app = FastAPI()


@app.get("/")
async def get_root():
    return {"msg": "Virtual Labs API"}


app.include_router(projects)
