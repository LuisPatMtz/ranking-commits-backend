from datetime import date, datetime, timedelta, timezone
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.github_scraper import fetch_contribution_cells_for_year
from app.db.session import get_db
from app.models.commit import Commit
from app.models.daily_contribution import DailyContribution
from app.models.participant import Participant
from app.models.repository import Repository
from app.models.user import User

router = APIRouter(prefix="/github", tags=["github"])


def _compute_streak(db: Session, usuario_id: int) -> int:
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    rows = (
        db.query(func.date(Commit.fecha).label("d"))
        .filter(Commit.usuario_id == usuario_id)
        .distinct()
        .all()
    )
    unique_dates: set[date] = {r.d for r in rows}
    if not unique_dates:
        return 0
    start = today if today in unique_dates else (yesterday if yesterday in unique_dates else None)
    if start is None:
        return 0
    streak = 0
    expected = start
    for d in sorted(unique_dates, reverse=True):
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
    return streak


def _fetch_public_contributions_total(client: httpx.Client, github_username: str) -> int | None:
    profile_resp = client.get(
        f"https://github.com/users/{github_username}/contributions",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0",
        },
    )
    if profile_resp.status_code != 200:
        return None

    html = profile_resp.text
    match = re.search(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", html, re.IGNORECASE)
    if not match:
        return None

    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


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
        **({"Authorization": f"token {settings.github_token}"} if settings.github_token else {}),
    }

    synced_repos = 0
    synced_commits = 0

    with httpx.Client(timeout=20.0, headers=headers) as client:
        contributions_total = _fetch_public_contributions_total(client, github_username)

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

        # Scraping del heatmap de GitHub (commits + PRs + issues + reviews)
        # Se hace dentro del bloque `with` para reutilizar la conexión abierta
        sync_from_date = since_dt.date()
        sync_to_date = datetime.now(timezone.utc).date()
        synced_daily = 0
        for year in range(sync_from_date.year, sync_to_date.year + 1):
            daily_cells = fetch_contribution_cells_for_year(client, github_username, year)
            for contribution_date, contribution_count in daily_cells.items():
                if sync_from_date <= contribution_date <= sync_to_date:
                    existing_daily = (
                        db.query(DailyContribution)
                        .filter(DailyContribution.usuario_id == usuario_id)
                        .filter(DailyContribution.fecha == contribution_date)
                        .first()
                    )
                    if existing_daily:
                        existing_daily.count = contribution_count
                    else:
                        db.add(DailyContribution(
                            usuario_id=usuario_id,
                            fecha=contribution_date,
                            count=contribution_count,
                        ))
                        synced_daily += 1

    participant.github_contributions_total = contributions_total
    participant.github_contributions_updated_at = datetime.now(timezone.utc)

    db.commit()

    streak_days = _compute_streak(db, usuario_id)

    return {
        "message": "Sync completado",
        "usuario_id": usuario_id,
        "github_username": github_username,
        "repos_nuevos": synced_repos,
        "commits_nuevos": synced_commits,
        "dias_contribucion_nuevos": synced_daily,
        "contribuciones_totales": contributions_total,
        "streak_days": streak_days,
        "since": since_iso,
    }
