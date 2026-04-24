from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.commit import Commit
from app.models.repository import Repository

router = APIRouter(prefix="/commits", tags=["commits"])


@router.get("/{usuario_id}")
def list_commits(usuario_id: int, limit: int = 200, db: Session = Depends(get_db)):
    max_limit = max(1, min(limit, 1000))
    rows = (
        db.query(Commit, Repository)
        .join(Repository, Repository.id == Commit.repositorio_id)
        .filter(Commit.usuario_id == usuario_id)
        .order_by(Commit.fecha.desc())
        .limit(max_limit)
        .all()
    )

    items = [
        {
            "sha": commit.sha,
            "mensaje": commit.mensaje,
            "fecha": commit.fecha,
            "url": commit.url,
            "puntos": commit.puntos,
            "repo": repository.repo,
            "owner": repository.owner,
        }
        for commit, repository in rows
    ]

    return {"usuario_id": usuario_id, "total": len(items), "items": items}
