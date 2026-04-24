from fastapi import APIRouter

router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.get("")
def get_ranking():
    return []


@router.get("/grupo/{grupo_id}")
def get_group_ranking(grupo_id: int):
    return {"grupo_id": grupo_id, "items": []}
