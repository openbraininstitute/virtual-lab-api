from fastapi import APIRouter


router = APIRouter(prefix="/virtual-labs")


@router.get("")
def retrieve_virtual_lab() -> None:
    return
