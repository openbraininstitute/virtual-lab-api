from fastapi import APIRouter

router = APIRouter(prefix="/users")


@router.get("")
def retrieve_user() -> None:
    return
