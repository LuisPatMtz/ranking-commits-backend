from datetime import date, datetime, time, timedelta, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, inspect
from sqlalchemy.orm import Session
import httpx

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.commit import Commit
from app.models.evaluation import TeacherEvaluation
from app.models.group import Group
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.project_evaluation import ProjectEvaluation
from app.models.user import User, UserRole
from app.schemas.group import GeneralRankingItemOut, GroupRankingGradesUpdateRequest, GroupRankingItemOut

router = APIRouter(prefix="/ranking", tags=["ranking"])

VALID_METRICS = {"todo", "commits", "contribuciones"}
VALID_PERIODS = {"7d", "30d", "90d", "1y", "all", "custom"}


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado o sin permisos")
    return group


def _build_group_ranking(db: Session, group_id: int, docente_id: int, days: int = 3650) -> list[GroupRankingItemOut]:
    since_date = datetime.now(timezone.utc) - timedelta(days=max(days, 1))

    members = (
        db.query(GroupUser.usuario_id, User.nombre, Participant.github_username, Participant.github_contributions_total)
        .join(User, User.id == GroupUser.usuario_id)
        .outerjoin(Participant, Participant.usuario_id == User.id)
        .filter(GroupUser.grupo_id == group_id)
        .filter(User.rol == UserRole.alumno)
        .order_by(User.nombre.asc())
        .all()
    )

    if not members:
        return []

    member_ids = [row.usuario_id for row in members]

    commit_rows = (
        db.query(Commit.usuario_id, func.count(Commit.id))
        .filter(Commit.usuario_id.in_(member_ids))
        .filter(Commit.fecha >= since_date)
        .group_by(Commit.usuario_id)
        .all()
    )
    commit_count_map = {usuario_id: int(count) for usuario_id, count in commit_rows}

    teacher_rows = (
        db.query(TeacherEvaluation.alumno_id, func.avg(TeacherEvaluation.calificacion))
        .filter(TeacherEvaluation.grupo_id == group_id)
        .filter(TeacherEvaluation.docente_id == docente_id)
        .filter(TeacherEvaluation.alumno_id.in_(member_ids))
        .group_by(TeacherEvaluation.alumno_id)
        .all()
    )
    teacher_grade_map = {alumno_id: float(avg_grade or 0) for alumno_id, avg_grade in teacher_rows}

    table_names = set(inspect(db.bind).get_table_names())
    project_grade_map: dict[int, float] = {}
    if ProjectEvaluation.__tablename__ in table_names:
        project_rows = (
            db.query(ProjectEvaluation.alumno_id, func.avg(ProjectEvaluation.calificacion))
            .filter(ProjectEvaluation.grupo_id == group_id)
            .filter(ProjectEvaluation.docente_id == docente_id)
            .filter(ProjectEvaluation.alumno_id.in_(member_ids))
            .group_by(ProjectEvaluation.alumno_id)
            .all()
        )
        project_grade_map = {alumno_id: float(avg_grade or 0) for alumno_id, avg_grade in project_rows}

    max_commits = max(
        (
            member.github_contributions_total
            if member.github_contributions_total is not None
            else commit_count_map.get(member.usuario_id, 0)
            for member in members
        ),
        default=0,
    )

    ranking_rows: list[GroupRankingItemOut] = []
    for member in members:
        commits_count = (
            member.github_contributions_total
            if member.github_contributions_total is not None
            else commit_count_map.get(member.usuario_id, 0)
        )
        commits_points = (commits_count / max_commits * 100.0) if max_commits > 0 else 0.0
        commits_points = round(min(commits_points, 100.0), 2)

        docente_grade = round(min(max(teacher_grade_map.get(member.usuario_id, 0.0), 0.0), 100.0), 2)
        proyecto_grade = round(min(max(project_grade_map.get(member.usuario_id, 0.0), 0.0), 100.0), 2)
        promedio = round((commits_points + docente_grade + proyecto_grade) / 3.0, 2)

        ranking_rows.append(
            GroupRankingItemOut(
                rank=0,
                usuario_id=member.usuario_id,
                nombre=member.nombre,
                github_username=member.github_username,
                commits_count=commits_count,
                commits_points=commits_points,
                docente_grade=docente_grade,
                proyecto_grade=proyecto_grade,
                promedio=promedio,
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


def _parse_tooltip_count(tooltip_text: str) -> int:
    if "No contributions" in tooltip_text:
        return 0

    match = re.search(r"([\d,]+)\s+contributions?", tooltip_text, re.IGNORECASE)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def _fetch_available_contribution_years(client: httpx.Client, github_username: str) -> list[int]:
    resp = client.get(
        f"https://github.com/users/{github_username}/contributions",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        return [datetime.now(timezone.utc).year]

    years = sorted({int(year) for year in re.findall(r'id="year-link-(\d{4})"', resp.text)}, reverse=True)
    return years or [datetime.now(timezone.utc).year]


def _fetch_contribution_cells_for_year(client: httpx.Client, github_username: str, year: int) -> dict[date, int]:
    resp = client.get(
        f"https://github.com/users/{github_username}/contributions?from={year}-01-01&to={year}-12-31",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        return {}

    html = resp.text
    date_by_component_id: dict[str, date] = {}
    for match in re.finditer(
        r'<td[^>]*data-date="([0-9]{4}-[0-9]{2}-[0-9]{2})"[^>]*id="(contribution-day-component-[^"]+)"|<td[^>]*id="(contribution-day-component-[^"]+)"[^>]*data-date="([0-9]{4}-[0-9]{2}-[0-9]{2})"',
        html,
    ):
        cell_date = match.group(1) or match.group(4)
        component_id = match.group(2) or match.group(3)
        if cell_date and component_id:
            date_by_component_id[component_id] = date.fromisoformat(cell_date)

    tooltip_count_by_component_id = {
        component_id: _parse_tooltip_count(re.sub(r"\s+", " ", tooltip_text.strip()))
        for component_id, tooltip_text in re.findall(
            r'<tool-tip[^>]*for="(contribution-day-component-[^"]+)"[^>]*>(.*?)</tool-tip>',
            html,
            re.S,
        )
    }

    result: dict[date, int] = {}
    for component_id, cell_date in date_by_component_id.items():
        result[cell_date] = tooltip_count_by_component_id.get(component_id, 0)
    return result


def _fetch_contributions_total_for_period(
    client: httpx.Client,
    github_username: str,
    start_date: date | None,
    end_date: date | None,
    cache: dict[tuple[str, int], dict[date, int]],
) -> int:
    if start_date is None or end_date is None:
        years = _fetch_available_contribution_years(client, github_username)
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
            cache[cache_key] = _fetch_contribution_cells_for_year(client, github_username, year)

        for contribution_date, contribution_count in cache[cache_key].items():
            if start_date <= contribution_date <= end_date:
                total += contribution_count
    return total


@router.get("")
def get_ranking():
    return []


@router.get("/grupo/{grupo_id}", response_model=list[GroupRankingItemOut])
def get_group_ranking(
    grupo_id: int,
    days: int = 3650,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _resolve_owned_group_or_404(db, grupo_id, current_user)
    return _build_group_ranking(db, group.id, current_user.id, days)


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
        db.query(GroupUser.grupo_id, GroupUser.usuario_id, User.nombre, Participant.github_username)
        .join(User, User.id == GroupUser.usuario_id)
        .outerjoin(Participant, Participant.usuario_id == User.id)
        .filter(GroupUser.grupo_id.in_(allowed_group_ids))
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

    teacher_rows = (
        db.query(TeacherEvaluation.grupo_id, TeacherEvaluation.alumno_id, func.avg(TeacherEvaluation.calificacion))
        .filter(TeacherEvaluation.docente_id == current_user.id)
        .filter(TeacherEvaluation.grupo_id.in_(allowed_group_ids))
        .group_by(TeacherEvaluation.grupo_id, TeacherEvaluation.alumno_id)
        .all()
    )
    teacher_grade_map = {(group_id, alumno_id): float(avg_grade or 0) for group_id, alumno_id, avg_grade in teacher_rows}

    table_names = set(inspect(db.bind).get_table_names())
    project_grade_map: dict[tuple[int, int], float] = {}
    if ProjectEvaluation.__tablename__ in table_names:
        project_rows = (
            db.query(ProjectEvaluation.grupo_id, ProjectEvaluation.alumno_id, func.avg(ProjectEvaluation.calificacion))
            .filter(ProjectEvaluation.docente_id == current_user.id)
            .filter(ProjectEvaluation.grupo_id.in_(allowed_group_ids))
            .group_by(ProjectEvaluation.grupo_id, ProjectEvaluation.alumno_id)
            .all()
        )
        project_grade_map = {(group_id, alumno_id): float(avg_grade or 0) for group_id, alumno_id, avg_grade in project_rows}

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

        docente_grade = round(min(max(teacher_grade_map.get((member.grupo_id, member.usuario_id), 0.0), 0.0), 100.0), 2)
        proyecto_grade = round(min(max(project_grade_map.get((member.grupo_id, member.usuario_id), 0.0), 0.0), 100.0), 2)

        rows.append(
            GeneralRankingItemOut(
                rank=0,
                group_id=member.grupo_id,
                group_name=group_name_by_id.get(member.grupo_id, f"Grupo {member.grupo_id}"),
                usuario_id=member.usuario_id,
                nombre=member.nombre,
                github_username=member.github_username,
                commits_count=commits_count,
                contributions_count=contributions_count,
                metric_value=metric_value,
                metric_points=0.0,
                docente_grade=docente_grade,
                proyecto_grade=proyecto_grade,
                total_score=0.0,
            )
        )

    max_metric_value = max((row.metric_value for row in rows), default=0)
    for row in rows:
        row.metric_points = round((row.metric_value / max_metric_value * 100.0), 2) if max_metric_value > 0 else 0.0
        row.total_score = (
            round((row.metric_points + row.docente_grade + row.proyecto_grade) / 3.0, 2)
            if metric == "todo"
            else row.metric_points
        )

    rows.sort(key=lambda row: (-row.total_score, -row.metric_value, row.nombre.lower()))
    for index, row in enumerate(rows, start=1):
        row.rank = index
    return rows


@router.put("/grupo/{grupo_id}/calificaciones")
def update_group_ranking_grades(
    grupo_id: int,
    payload: GroupRankingGradesUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _resolve_owned_group_or_404(db, grupo_id, current_user)

    membership = (
        db.query(GroupUser)
        .filter(GroupUser.grupo_id == group.id)
        .filter(GroupUser.usuario_id == payload.usuario_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El alumno no pertenece al grupo")

    if payload.docente_grade is not None:
        docente_grade = int(round(min(max(payload.docente_grade, 0.0), 100.0)))
        existing_teacher_eval = (
            db.query(TeacherEvaluation)
            .filter(TeacherEvaluation.alumno_id == payload.usuario_id)
            .filter(TeacherEvaluation.docente_id == current_user.id)
            .filter(TeacherEvaluation.grupo_id == group.id)
            .order_by(TeacherEvaluation.id.desc())
            .first()
        )
        if existing_teacher_eval:
            existing_teacher_eval.calificacion = docente_grade
            existing_teacher_eval.puntos_importancia = 100
        else:
            db.add(
                TeacherEvaluation(
                    alumno_id=payload.usuario_id,
                    docente_id=current_user.id,
                    grupo_id=group.id,
                    calificacion=docente_grade,
                    puntos_importancia=100,
                    comentario=None,
                )
            )

    if payload.proyecto_grade is not None:
        table_names = set(inspect(db.bind).get_table_names())
        if ProjectEvaluation.__tablename__ not in table_names:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Falta tabla de evaluaciones de proyecto. Ejecuta init_db para crearla.",
            )

        proyecto_grade = int(round(min(max(payload.proyecto_grade, 0.0), 100.0)))
        existing_project_eval = (
            db.query(ProjectEvaluation)
            .filter(ProjectEvaluation.alumno_id == payload.usuario_id)
            .filter(ProjectEvaluation.docente_id == current_user.id)
            .filter(ProjectEvaluation.grupo_id == group.id)
            .first()
        )
        if existing_project_eval:
            existing_project_eval.calificacion = proyecto_grade
        else:
            db.add(
                ProjectEvaluation(
                    alumno_id=payload.usuario_id,
                    docente_id=current_user.id,
                    grupo_id=group.id,
                    calificacion=proyecto_grade,
                )
            )

    db.commit()
    return {"message": "Calificaciones actualizadas"}
