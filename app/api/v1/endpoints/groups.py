from fastapi import APIRouter

router = APIRouter(prefix="/grupos", tags=["grupos"])


@router.get("")
def list_groups():
    return []
