from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.commit import Commit
from app.models.participant import Participant
from app.models.repository import Repository
from app.models.user import User

router = APIRouter(prefix="/github", tags=["github"])


@router.post("/sync/{usuario_id}")
def sync_user_commits(
    usuario_id: int,
    days: int = 365,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != usuario_id and current_user.rol not in ("docente", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos para sincronizar este usuario")

    participant = db.query(Participant).filter(Participant.usuario_id == usuario_id).first()
    if not participant or not participant.github_username:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante sin github_username")

    github_username = participant.github_username.strip()
    since_dt = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 3650)))
    since_iso = since_dt.isoformat().replace("+00:00", "Z")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ranking-commits-app",
    }

    synced_repos = 0
    synced_commits = 0

    with httpx.Client(timeout=20.0, headers=headers) as client:
        repos_resp = client.get(f"https://api.github.com/users/{github_username}/repos", params={"per_page": 100, "type": "owner", "sort": "updated"})
        if repos_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudieron obtener repositorios de GitHub")

        repos = repos_resp.json()

        for repo_data in repos:
            owner = repo_data.get("owner", {}).get("login")
            repo_name = repo_data.get("name")
            html_url = repo_data.get("html_url")
            if not owner or not repo_name or not html_url:
                continue

            repo = (
                db.query(Repository)
                .filter(Repository.usuario_id == usuario_id)
                .filter(Repository.owner == owner)
                .filter(Repository.repo == repo_name)
                .first()
            )
            if not repo:
                repo = Repository(
                    owner=owner,
                    repo=repo_name,
                    url=html_url,
                    usuario_id=usuario_id,
                    proyecto_nombre=repo_name,
                    activo=True,
                )
                db.add(repo)
                db.flush()
                synced_repos += 1

            commits_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo_name}/commits",
                params={"author": github_username, "since": since_iso, "per_page": 100},
            )
            if commits_resp.status_code != 200:
                continue

            for commit_data in commits_resp.json():
                sha = commit_data.get("sha")
                commit_obj = commit_data.get("commit", {})
                message = commit_obj.get("message")
                date_str = commit_obj.get("author", {}).get("date")
                url = commit_data.get("html_url")
                if not sha or not message or not date_str or not url:
                    continue

                exists = db.query(Commit).filter(Commit.sha == sha).first()
                if exists:
                    continue

                commit_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                db.add(
                    Commit(
                        sha=sha,
                        usuario_id=usuario_id,
                        repositorio_id=repo.id,
                        mensaje=message[:500],
                        fecha=commit_date,
                        url=url,
                        puntos=1,
                    )
                )
                synced_commits += 1

    db.commit()

    return {
        "message": "Sync completado",
        "usuario_id": usuario_id,
        "github_username": github_username,
        "repos_nuevos": synced_repos,
        "commits_nuevos": synced_commits,
        "since": since_iso,
    }
