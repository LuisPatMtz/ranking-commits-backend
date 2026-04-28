from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
import httpx

from app.api.deps import get_current_user
from app.core.github_scraper import fetch_available_contribution_years, fetch_contribution_cells_for_year
from app.db.session import get_db
from app.models.anonymous_competitor import AnonymousCompetitor
from app.models.commit import Commit
from app.models.daily_contribution import DailyContribution
from app.models.group import Proyecto as Group
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.peer_vote import PeerVote
from app.models.user import User, UserRole
from app.schemas.group import GeneralRankingItemOut, GroupRankingItemOut

router = APIRouter(prefix="/ranking", tags=["ranking"])

VALID_METRICS = {"todo", "commits", "contribuciones"}
VALID_PERIODS = {"7d", "30d", "90d", "1y", "all", "custom"}


def _calculate_streak(commit_dates: list[date], today: date) -> int:
    if not commit_dates:
        return 0
    unique_dates = set(commit_dates)
    yesterday = today - timedelta(days=1)
    # Si no hubo commit hoy pero sí ayer, la racha sigue activa
    if today in unique_dates:
        start = today
    elif yesterday in unique_dates:
        start = yesterday
    else:
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


def _resolve_owned_group_or_404(db: Session, group_id: int, current_user: User) -> Group:
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden consultar ranking")

    group = (
        db.query(Group)
        .filter(Group.id == group_id)
        .filter(Group.created_by_user_id == current_user.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado o sin permisos")
    return group


def _build_group_ranking(db: Session, group: Group, peer_voting_enabled: bool = False) -> list[GroupRankingItemOut]:
    project_start = datetime.combine(group.fecha_inicio.date() if hasattr(group.fecha_inicio, "date") else group.fecha_inicio, time.min, tzinfo=timezone.utc)
    project_end = datetime.combine(group.fecha_cierre.date() if hasattr(group.fecha_cierre, "date") else group.fecha_cierre, time.max, tzinfo=timezone.utc)

    members = (
        db.query(GroupUser.usuario_id, User.nombre, Participant.github_username, Participant.github_contributions_total)
        .join(User, User.id == GroupUser.usuario_id)
        .outerjoin(Participant, Participant.usuario_id == User.id)
        .filter(GroupUser.proyecto_id == group.id)
        .filter(User.rol == UserRole.alumno)
        .order_by(User.nombre.asc())
        .all()
    )

    if not members:
        return []

    member_ids = [row.usuario_id for row in members]
    project_start_date = project_start.date()
    project_end_date = project_end.date()

    # Contribuciones diarias (commits + PRs + issues + reviews — todo lo del heatmap de GitHub)
    daily_rows = (
        db.query(DailyContribution.usuario_id, DailyContribution.fecha, DailyContribution.count)
        .filter(DailyContribution.usuario_id.in_(member_ids))
        .filter(DailyContribution.fecha >= project_start_date)
        .filter(DailyContribution.fecha <= project_end_date)
        .all()
    )
    activity_count_map: dict[int, int] = {}
    activity_dates_by_member: dict[int, list[date]] = {}
    for uid, fecha, cnt in daily_rows:
        if cnt > 0:
            activity_count_map[uid] = activity_count_map.get(uid, 0) + cnt
            activity_dates_by_member.setdefault(uid, []).append(fecha)

    # Fallback: alumnos que aún no sincronizaron su heatmap usan commits de la BD
    members_without_daily = [uid for uid in member_ids if uid not in activity_count_map]
    if members_without_daily:
        commit_rows = (
            db.query(Commit.usuario_id, func.count(Commit.id))
            .filter(Commit.usuario_id.in_(members_without_daily))
            .filter(Commit.fecha >= project_start)
            .filter(Commit.fecha <= project_end)
            .group_by(Commit.usuario_id)
            .all()
        )
        for uid, cnt in commit_rows:
            activity_count_map[uid] = int(cnt)

        commit_date_rows = (
            db.query(Commit.usuario_id, func.date(Commit.fecha).label("d"))
            .filter(Commit.usuario_id.in_(members_without_daily))
            .filter(Commit.fecha >= project_start)
            .filter(Commit.fecha <= project_end)
            .distinct()
            .all()
        )
        for uid, d in commit_date_rows:
            activity_dates_by_member.setdefault(uid, []).append(d)

    today = datetime.now(timezone.utc).date()
    effective_today = min(today, project_end_date)
    streak_map = {uid: _calculate_streak(activity_dates_by_member.get(uid, []), effective_today) for uid in member_ids}
    max_streak = max(streak_map.values(), default=0)

    peer_vote_avg_map: dict[int, float] = {}
    if peer_voting_enabled:
        peer_rows = (
            db.query(PeerVote.votado_id, func.avg(PeerVote.estrellas))
            .filter(PeerVote.proyecto_id == group.id)
            .filter(PeerVote.votado_id.in_(member_ids))
            .group_by(PeerVote.votado_id)
            .all()
        )
        peer_vote_avg_map = {votado_id: float(avg_stars or 0) for votado_id, avg_stars in peer_rows}

    max_activity = max(activity_count_map.get(m.usuario_id, 0) for m in members) if members else 0

    ranking_rows: list[GroupRankingItemOut] = []
    for member in members:
        commits_count = activity_count_map.get(member.usuario_id, 0)
        commits_points = round((commits_count / max_activity * 100.0), 2) if max_activity > 0 else 0.0

        streak_days = streak_map.get(member.usuario_id, 0)
        streak_points = round((streak_days / max_streak * 100.0), 2) if max_streak > 0 else 0.0

        raw_peer_avg = peer_vote_avg_map.get(member.usuario_id, 0.0)
        peer_vote_avg = round(raw_peer_avg, 2)
        peer_vote_points = round(raw_peer_avg / 5.0 * 100.0, 2) if raw_peer_avg > 0 else 0.0

        if peer_voting_enabled:
            promedio = round(commits_points * 0.33 + streak_points * 0.33 + peer_vote_points * 0.34, 2)
        else:
            promedio = round((commits_points + streak_points) / 2.0, 2)

        ranking_rows.append(
            GroupRankingItemOut(
                rank=0,
                usuario_id=member.usuario_id,
                nombre=member.nombre,
                github_username=member.github_username,
                commits_count=commits_count,
                commits_points=commits_points,
                streak_days=streak_days,
                streak_points=streak_points,
                peer_vote_avg=peer_vote_avg,
                peer_vote_points=peer_vote_points,
                promedio=promedio,
            )
        )

    # Incluir competidores anónimos sin cuenta reclamada
    anon_rows = (
        db.query(AnonymousCompetitor)
        .filter(AnonymousCompetitor.proyecto_id == group.id)
        .filter(AnonymousCompetitor.claimed_by_user_id.is_(None))
        .all()
    )
    for anon in anon_rows:
        anon_commits = 0
        anon_streak = 0
        if anon.github_username:
            participant_match = (
                db.query(Participant)
                .filter(Participant.github_username == anon.github_username)
                .first()
            )
            if participant_match:
                anon_commit_count = (
                    db.query(func.count(Commit.id))
                    .filter(Commit.usuario_id == participant_match.usuario_id)
                    .filter(Commit.fecha >= project_start)
                    .filter(Commit.fecha <= project_end)
                    .scalar() or 0
                )
                anon_commits = int(anon_commit_count)
                anon_dates = (
                    db.query(func.date(Commit.fecha).label("d"))
                    .filter(Commit.usuario_id == participant_match.usuario_id)
                    .filter(Commit.fecha >= project_start)
                    .filter(Commit.fecha <= project_end)
                    .distinct()
                    .all()
                )
                anon_streak = _calculate_streak([r.d for r in anon_dates], effective_today)

        anon_commits_points = round((anon_commits / max_commits * 100.0), 2) if max_commits > 0 else 0.0
        anon_streak_points = round((anon_streak / max_streak * 100.0), 2) if max_streak > 0 else 0.0
        if peer_voting_enabled:
            anon_promedio = round(anon_commits_points * 0.33 + anon_streak_points * 0.33, 2)
        else:
            anon_promedio = round((anon_commits_points + anon_streak_points) / 2.0, 2)

        ranking_rows.append(
            GroupRankingItemOut(
                rank=0,
                usuario_id=-anon.id,
                nombre=f"{anon.nombre} (pendiente)",
                github_username=anon.github_username,
                commits_count=anon_commits,
                commits_points=anon_commits_points,
                streak_days=anon_streak,
                streak_points=anon_streak_points,
                peer_vote_avg=0.0,
                peer_vote_points=0.0,
                promedio=anon_promedio,
            )
        )

    ranking_rows.sort(key=lambda row: (-row.promedio, -row.commits_count, row.nombre.lower()))
    for index, row in enumerate(ranking_rows, start=1):
        row.rank = index

    return ranking_rows


def _resolve_period_range(period: str, from_date: date | None, to_date: date | None) -> tuple[date | None, date | None]:
    today = datetime.now(timezone.utc).date()

    if period == "all":
        return None, None
    if period == "7d":
        return today - timedelta(days=6), today
    if period == "30d":
        return today - timedelta(days=29), today
    if period == "90d":
        return today - timedelta(days=89), today
    if period == "1y":
        return today - timedelta(days=364), today
    if period == "custom":
        if not from_date or not to_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debes enviar from_date y to_date para periodo custom")
        if from_date > to_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from_date no puede ser mayor a to_date")
        return from_date, to_date

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Periodo no valido")


def _fetch_contributions_total_for_period(
    client: httpx.Client,
    github_username: str,
    start_date: date | None,
    end_date: date | None,
    cache: dict[tuple[str, int], dict[date, int]],
) -> int:
    if start_date is None or end_date is None:
        years = fetch_available_contribution_years(client, github_username)
        if not years:
            return 0
        start_date = date(min(years), 1, 1)
        end_date = datetime.now(timezone.utc).date()
    else:
        years = list(range(start_date.year, end_date.year + 1))

    total = 0
    for year in years:
        cache_key = (github_username, year)
        if cache_key not in cache:
            cache[cache_key] = fetch_contribution_cells_for_year(client, github_username, year)

        for contribution_date, contribution_count in cache[cache_key].items():
            if start_date <= contribution_date <= end_date:
                total += contribution_count
    return total


@router.get("")
def get_ranking():
    return []


@router.get("/proyecto/{proyecto_id}", response_model=list[GroupRankingItemOut])
def get_group_ranking(
    proyecto_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _resolve_owned_group_or_404(db, proyecto_id, current_user)
    return _build_group_ranking(db, group, peer_voting_enabled=group.peer_voting_enabled)


@router.get("/general", response_model=list[GeneralRankingItemOut])
def get_general_ranking(
    metric: str = "todo",
    period: str = "1y",
    from_date: date | None = None,
    to_date: date | None = None,
    group_ids: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden consultar ranking")
    if metric not in VALID_METRICS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Metrica no valida")
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Periodo no valido")

    selected_group_ids: list[int] | None = None
    if group_ids:
        selected_group_ids = [int(group_id) for group_id in group_ids.split(",") if group_id.strip()]

    groups_query = db.query(Group).filter(Group.created_by_user_id == current_user.id)
    if selected_group_ids:
        groups_query = groups_query.filter(Group.id.in_(selected_group_ids))
    groups = groups_query.all()
    if not groups:
        return []

    allowed_group_ids = [group.id for group in groups]
    group_name_by_id = {group.id: group.nombre for group in groups}

    range_start, range_end = _resolve_period_range(period, from_date, to_date)

    members = (
        db.query(GroupUser.proyecto_id, GroupUser.usuario_id, User.nombre, Participant.github_username)
        .join(User, User.id == GroupUser.usuario_id)
        .outerjoin(Participant, Participant.usuario_id == User.id)
        .filter(GroupUser.proyecto_id.in_(allowed_group_ids))
        .filter(User.rol == UserRole.alumno)
        .all()
    )
    if not members:
        return []

    member_ids = sorted({member.usuario_id for member in members})
    commit_query = (
        db.query(Commit.usuario_id, func.count(Commit.id))
        .filter(Commit.usuario_id.in_(member_ids))
    )
    if range_start is not None and range_end is not None:
        commit_query = commit_query.filter(
            Commit.fecha >= datetime.combine(range_start, time.min, tzinfo=timezone.utc),
            Commit.fecha <= datetime.combine(range_end, time.max, tzinfo=timezone.utc),
        )
    commit_rows = commit_query.group_by(Commit.usuario_id).all()
    commit_count_map = {usuario_id: int(count) for usuario_id, count in commit_rows}

    today = datetime.now(timezone.utc).date()
    general_date_rows = (
        db.query(Commit.usuario_id, func.date(Commit.fecha).label("d"))
        .filter(Commit.usuario_id.in_(member_ids))
        .distinct()
        .all()
    )
    commit_dates_by_member: dict[int, list[date]] = {}
    for uid, d in general_date_rows:
        commit_dates_by_member.setdefault(uid, []).append(d)
    streak_map = {uid: _calculate_streak(commit_dates_by_member.get(uid, []), today) for uid in member_ids}
    max_streak = max(streak_map.values(), default=0)

    contributions_count_map: dict[int, int] = {}
    if metric in {"todo", "contribuciones"}:
        yearly_cache: dict[tuple[str, int], dict[date, int]] = {}
        with httpx.Client(timeout=20.0) as client:
            for member in members:
                if member.usuario_id in contributions_count_map:
                    continue
                if not member.github_username:
                    contributions_count_map[member.usuario_id] = 0
                    continue
                contributions_count_map[member.usuario_id] = _fetch_contributions_total_for_period(
                    client,
                    member.github_username.strip(),
                    range_start,
                    range_end,
                    yearly_cache,
                )

    rows: list[GeneralRankingItemOut] = []
    for member in members:
        commits_count = commit_count_map.get(member.usuario_id, 0)
        contributions_count = contributions_count_map.get(member.usuario_id, 0)

        if metric == "commits":
            metric_value = commits_count
        elif metric == "contribuciones":
            metric_value = contributions_count
        else:
            metric_value = contributions_count if member.github_username else commits_count

        streak_days = streak_map.get(member.usuario_id, 0)
        streak_points = round((streak_days / max_streak * 100.0), 2) if max_streak > 0 else 0.0

        rows.append(
            GeneralRankingItemOut(
                rank=0,
                group_id=member.proyecto_id,
                group_name=group_name_by_id.get(member.proyecto_id, f"Proyecto {member.proyecto_id}"),
                usuario_id=member.usuario_id,
                nombre=member.nombre,
                github_username=member.github_username,
                commits_count=commits_count,
                contributions_count=contributions_count,
                metric_value=metric_value,
                metric_points=0.0,
                streak_days=streak_days,
                streak_points=streak_points,
                total_score=0.0,
            )
        )

    max_metric_value = max((row.metric_value for row in rows), default=0)
    for row in rows:
        row.metric_points = round((row.metric_value / max_metric_value * 100.0), 2) if max_metric_value > 0 else 0.0
        row.total_score = (
            round((row.metric_points + row.streak_points) / 2.0, 2)
            if metric == "todo"
            else row.metric_points
        )

    rows.sort(key=lambda row: (-row.total_score, -row.metric_value, row.nombre.lower()))
    for index, row in enumerate(rows, start=1):
        row.rank = index
    return rows
