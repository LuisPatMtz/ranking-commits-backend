from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.commit import Commit
from app.models.evaluation import TeacherEvaluation
from app.models.group import Group
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.project_evaluation import ProjectEvaluation
from app.models.user import User, UserRole
from app.schemas.group import GroupRankingGradesUpdateRequest, GroupRankingItemOut

router = APIRouter(prefix="/ranking", tags=["ranking"])


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
        db.query(GroupUser.usuario_id, User.nombre, Participant.github_username)
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

    max_commits = max((commit_count_map.get(member_id, 0) for member_id in member_ids), default=0)

    ranking_rows: list[GroupRankingItemOut] = []
    for member in members:
        commits_count = commit_count_map.get(member.usuario_id, 0)
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
