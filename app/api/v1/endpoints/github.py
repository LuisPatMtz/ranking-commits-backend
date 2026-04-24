from fastapi import APIRouter

router = APIRouter(prefix="/github", tags=["github"])


@router.post("/sync/{usuario_id}")
def sync_user_commits(usuario_id: int):
    return {"message": "Sync queued", "usuario_id": usuario_id}
