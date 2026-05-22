from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.anonymous_competitor import AnonymousCompetitor
from app.models.commit import Commit
from app.models.daily_contribution import DailyContribution
from app.models.docente_invite import DocenteInvite
from app.models.group import Proyecto as Group
from app.models.group_share_token import GroupShareToken
from app.models.group_student_invite import GroupStudentInvite
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.peer_vote import PeerVote
from app.models.ranking import Ranking
from app.models.repository import Repository
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _require_admin(current_user: User) -> None:
    if current_user.rol != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el admin puede realizar esta acción")


@router.get("/admin/stats")
def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    return {
        "total_usuarios": db.query(func.count(User.id)).scalar(),
        "total_docentes": db.query(func.count(User.id)).filter(User.rol == UserRole.docente).scalar(),
        "total_alumnos": db.query(func.count(User.id)).filter(User.rol == UserRole.alumno).scalar(),
        "usuarios_activos": db.query(func.count(User.id)).filter(User.activo.is_(True)).scalar(),
        "total_grupos": db.query(func.count(Group.id)).scalar(),
        "total_commits": db.query(func.count(Commit.id)).scalar(),
        "total_participantes": db.query(func.count(Participant.id)).scalar(),
        "invites_docente_pendientes": db.query(func.count(DocenteInvite.id))
            .filter(DocenteInvite.used_by_user_id.is_(None))
            .scalar(),
        "invites_alumno_activos": db.query(func.count(GroupStudentInvite.id))
            .filter(GroupStudentInvite.activo.is_(True))
            .scalar(),
    }


@router.get("/admin/invites-docente")
def list_docente_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    rows = db.query(DocenteInvite).order_by(DocenteInvite.created_at.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "token": r.token,
            "usado": r.used_by_user_id is not None,
            "expires_at": r.expires_at.isoformat(),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.patch("/{usuario_id}/toggle-activo", response_model=UserOut)
def toggle_user_active(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    user = db.query(User).filter(User.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes desactivarte a ti mismo")
    user.activo = not user.activo
    db.commit()
    db.refresh(user)
    return user


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username ya registrado")

    user = User(
        nombre=payload.nombre,
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        rol=payload.rol,
        activo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserOut])
def list_users(
    rol: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    query = db.query(User)
    if rol:
        query = query.filter(User.rol == rol)
    return query.order_by(User.id.desc()).all()


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    user = db.query(User).filter(User.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes eliminarte a ti mismo")

    db.query(PeerVote).filter((PeerVote.votante_id == usuario_id) | (PeerVote.votado_id == usuario_id)).delete(synchronize_session=False)
    db.query(Ranking).filter(Ranking.usuario_id == usuario_id).delete(synchronize_session=False)
    db.query(DailyContribution).filter(DailyContribution.usuario_id == usuario_id).delete(synchronize_session=False)
    db.query(Commit).filter(Commit.usuario_id == usuario_id).delete(synchronize_session=False)
    db.query(Repository).filter(Repository.usuario_id == usuario_id).delete(synchronize_session=False)
    db.query(GroupUser).filter(GroupUser.usuario_id == usuario_id).delete(synchronize_session=False)
    db.query(AnonymousCompetitor).filter(AnonymousCompetitor.claimed_by_user_id == usuario_id).update({"claimed_by_user_id": None}, synchronize_session=False)
    db.query(GroupShareToken).filter(
        (GroupShareToken.owner_docente_id == usuario_id) |
        (GroupShareToken.invited_docente_id == usuario_id) |
        (GroupShareToken.used_by_docente_id == usuario_id)
    ).delete(synchronize_session=False)
    db.query(GroupStudentInvite).filter(GroupStudentInvite.created_by_docente_id == usuario_id).delete(synchronize_session=False)
    db.query(DocenteInvite).filter(
        (DocenteInvite.created_by_admin_id == usuario_id) | (DocenteInvite.used_by_user_id == usuario_id)
    ).delete(synchronize_session=False)

    grupos_del_usuario = db.query(Group.id).filter(Group.created_by_user_id == usuario_id).subquery()
    db.query(PeerVote).filter(PeerVote.proyecto_id.in_(grupos_del_usuario)).delete(synchronize_session=False)
    db.query(Ranking).filter(Ranking.proyecto_id.in_(grupos_del_usuario)).delete(synchronize_session=False)
    db.query(GroupStudentInvite).filter(GroupStudentInvite.proyecto_id.in_(grupos_del_usuario)).delete(synchronize_session=False)
    db.query(GroupShareToken).filter(GroupShareToken.proyecto_id.in_(grupos_del_usuario)).delete(synchronize_session=False)
    db.query(AnonymousCompetitor).filter(AnonymousCompetitor.proyecto_id.in_(grupos_del_usuario)).delete(synchronize_session=False)
    db.query(GroupUser).filter(GroupUser.proyecto_id.in_(grupos_del_usuario)).delete(synchronize_session=False)
    db.query(Group).filter(Group.created_by_user_id == usuario_id).delete(synchronize_session=False)

    db.query(Participant).filter(Participant.usuario_id == usuario_id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()


@router.get("/admin/proyectos", response_model=list[dict])
def list_all_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    rows = (
        db.query(Group, User.nombre, User.username)
        .outerjoin(User, User.id == Group.created_by_user_id)
        .order_by(Group.id.desc())
        .all()
    )
    return [
        {
            "id": group.id,
            "nombre": group.nombre,
            "carrera": group.carrera,
            "fecha_inicio": group.fecha_inicio.isoformat(),
            "fecha_cierre": group.fecha_cierre.isoformat(),
            "docente_nombre": docente_nombre,
            "docente_username": docente_username,
        }
        for group, docente_nombre, docente_username in rows
    ]


@router.delete("/admin/proyectos/{proyecto_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    proyecto_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    group = db.query(Group).filter(Group.id == proyecto_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    db.query(PeerVote).filter(PeerVote.proyecto_id == proyecto_id).delete(synchronize_session=False)
    db.query(Ranking).filter(Ranking.proyecto_id == proyecto_id).delete(synchronize_session=False)
    db.query(GroupStudentInvite).filter(GroupStudentInvite.proyecto_id == proyecto_id).delete(synchronize_session=False)
    db.query(GroupShareToken).filter(GroupShareToken.proyecto_id == proyecto_id).delete(synchronize_session=False)
    db.query(AnonymousCompetitor).filter(AnonymousCompetitor.proyecto_id == proyecto_id).delete(synchronize_session=False)
    db.query(GroupUser).filter(GroupUser.proyecto_id == proyecto_id).delete(synchronize_session=False)
    db.delete(group)
    db.commit()
