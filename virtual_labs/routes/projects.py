from fastapi import APIRouter

projects = APIRouter(prefix="/lab/{labid}/projects")


@projects.get("/{project_id}")
async def get_project(project_id: str):
    print(project_id)
    pass
