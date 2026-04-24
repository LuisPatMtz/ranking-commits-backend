from fastapi import APIRouter

router = APIRouter(prefix="/repositorios", tags=["repositorios"])


@router.get("")
def list_repositories():
    return []
