from fastapi import APIRouter

router = APIRouter(prefix="/commits", tags=["commits"])


@router.get("/{usuario_id}")
def list_commits(usuario_id: int):
    return {"usuario_id": usuario_id, "items": []}
