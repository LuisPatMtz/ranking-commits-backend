from fastapi import APIRouter

router = APIRouter(prefix="/evaluaciones", tags=["evaluaciones"])


@router.get("")
def list_evaluations():
    return []
