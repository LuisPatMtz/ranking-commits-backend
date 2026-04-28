from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.group import Group
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.peer_vote import PeerVote
from app.models.user import User, UserRole
from app.schemas.group import CompañeroVotable, MiPerfilAlumno, PeerVoteCreate, PeerVoteOut, VotoRecibidoOut

router = APIRouter(tags=["votos"])


def _require_alumno(current_user: User) -> None:
    if current_user.rol != UserRole.alumno:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo alumnos pueden acceder a esta sección")


def _get_active_membership(db: Session, proyecto_id: int, usuario_id: int) -> GroupUser:
    membership = (
        db.query(GroupUser)
        .filter(GroupUser.proyecto_id == proyecto_id)
        .filter(GroupUser.usuario_id == usuario_id)
        .filter(GroupUser.fecha_fin.is_(None))
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No perteneces a este proyecto")
    return membership


def _get_project_or_404(db: Session, proyecto_id: int) -> Group:
    group = db.query(Group).filter(Group.id == proyecto_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return group


def _validate_voting_open(group: Group) -> None:
    now = datetime.now(timezone.utc)
    fecha_inicio = group.fecha_inicio if group.fecha_inicio.tzinfo else group.fecha_inicio.replace(tzinfo=timezone.utc)
    fecha_cierre = group.fecha_cierre if group.fecha_cierre.tzinfo else group.fecha_cierre.replace(tzinfo=timezone.utc)
    if now < fecha_inicio or now > fecha_cierre:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las votaciones solo están disponibles durante el periodo activo del proyecto")


# ---------------------------------------------------------------------------
# Perfil del alumno (su proyecto, ranking y contribuciones)
# ---------------------------------------------------------------------------

@router.get("/alumnos/mi-perfil", response_model=MiPerfilAlumno)
def get_mi_perfil(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)

    participant = db.query(Participant).filter(Participant.usuario_id == current_user.id).first()

    membership = (
        db.query(GroupUser)
        .filter(GroupUser.usuario_id == current_user.id)
        .filter(GroupUser.fecha_fin.is_(None))
        .order_by(GroupUser.id.desc())
        .first()
    )

    if not membership:
        return MiPerfilAlumno(
            usuario_id=current_user.id,
            nombre=current_user.nombre,
            github_username=participant.github_username if participant else None,
            github_contributions_total=participant.github_contributions_total if participant else None,
        )

    group = db.query(Group).filter(Group.id == membership.proyecto_id).first()

    from app.api.v1.endpoints.ranking import _build_group_ranking
    ranking_rows = _build_group_ranking(db, group, peer_voting_enabled=group.peer_voting_enabled if group else False)

    mi_fila = next((r for r in ranking_rows if r.usuario_id == current_user.id), None)

    return MiPerfilAlumno(
        usuario_id=current_user.id,
        nombre=current_user.nombre,
        github_username=participant.github_username if participant else None,
        github_contributions_total=participant.github_contributions_total if participant else None,
        proyecto_id=membership.proyecto_id,
        proyecto_nombre=group.nombre if group else None,
        peer_voting_enabled=group.peer_voting_enabled if group else False,
        mi_rank=mi_fila.rank if mi_fila else None,
        total_en_proyecto=len(ranking_rows),
        commits_count=mi_fila.commits_count if mi_fila else 0,
        streak_days=mi_fila.streak_days if mi_fila else 0,
        peer_vote_avg=mi_fila.peer_vote_avg if mi_fila else 0.0,
        promedio=mi_fila.promedio if mi_fila else 0.0,
    )


# ---------------------------------------------------------------------------
# Compañeros a los que puedo votar en este proyecto
# ---------------------------------------------------------------------------

@router.get("/proyectos/{proyecto_id}/votos/companeros", response_model=list[CompañeroVotable])
def get_companeros_votables(
    proyecto_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)
    _get_active_membership(db, proyecto_id, current_user.id)

    group = _get_project_or_404(db, proyecto_id)
    if not group.peer_voting_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Las votaciones no están habilitadas en este proyecto")
    _validate_voting_open(group)

    members = (
        db.query(GroupUser.usuario_id, User.nombre, Participant.github_username)
        .join(User, User.id == GroupUser.usuario_id)
        .outerjoin(Participant, Participant.usuario_id == User.id)
        .filter(GroupUser.proyecto_id == proyecto_id)
        .filter(GroupUser.fecha_fin.is_(None))
        .filter(User.rol == UserRole.alumno)
        .filter(User.id != current_user.id)
        .order_by(User.nombre.asc())
        .all()
    )

    mis_votos = {
        v.votado_id: v.estrellas
        for v in db.query(PeerVote)
        .filter(PeerVote.votante_id == current_user.id)
        .filter(PeerVote.proyecto_id == proyecto_id)
        .all()
    }

    return [
        CompañeroVotable(
            usuario_id=m.usuario_id,
            nombre=m.nombre,
            github_username=m.github_username,
            mi_voto=mis_votos.get(m.usuario_id),
        )
        for m in members
    ]


# ---------------------------------------------------------------------------
# Votar a un compañero (crea o actualiza el voto, una vez por proyecto)
# ---------------------------------------------------------------------------

@router.post("/proyectos/{proyecto_id}/votos", response_model=PeerVoteOut, status_code=status.HTTP_201_CREATED)
def votar_companero(
    proyecto_id: int,
    payload: PeerVoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)
    _get_active_membership(db, proyecto_id, current_user.id)

    group = _get_project_or_404(db, proyecto_id)
    if not group.peer_voting_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Las votaciones no están habilitadas en este proyecto")
    _validate_voting_open(group)

    if payload.votado_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes votarte a ti mismo")

    if payload.estrellas < 1 or payload.estrellas > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las estrellas deben ser entre 1 y 5")

    _get_active_membership(db, proyecto_id, payload.votado_id)

    votado = db.query(User).filter(User.id == payload.votado_id).first()
    if not votado or votado.rol != UserRole.alumno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compañero no encontrado")

    existing = (
        db.query(PeerVote)
        .filter(PeerVote.votante_id == current_user.id)
        .filter(PeerVote.votado_id == payload.votado_id)
        .filter(PeerVote.proyecto_id == proyecto_id)
        .first()
    )

    if existing:
        existing.estrellas = payload.estrellas
        db.commit()
        db.refresh(existing)
        vote = existing
    else:
        vote = PeerVote(
            votante_id=current_user.id,
            votado_id=payload.votado_id,
            proyecto_id=proyecto_id,
            estrellas=payload.estrellas,
        )
        db.add(vote)
        db.commit()
        db.refresh(vote)

    return PeerVoteOut(
        id=vote.id,
        votado_id=vote.votado_id,
        votado_nombre=votado.nombre,
        estrellas=vote.estrellas,
    )


# ---------------------------------------------------------------------------
# Mis votos emitidos en un proyecto
# ---------------------------------------------------------------------------

@router.get("/proyectos/{proyecto_id}/votos/mis-votos", response_model=list[PeerVoteOut])
def get_mis_votos(
    proyecto_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)
    _get_active_membership(db, proyecto_id, current_user.id)

    rows = (
        db.query(PeerVote, User)
        .join(User, User.id == PeerVote.votado_id)
        .filter(PeerVote.votante_id == current_user.id)
        .filter(PeerVote.proyecto_id == proyecto_id)
        .all()
    )
    return [
        PeerVoteOut(id=v.id, votado_id=v.votado_id, votado_nombre=u.nombre, estrellas=v.estrellas)
        for v, u in rows
    ]


# ---------------------------------------------------------------------------
# Votos recibidos por el alumno en un proyecto
# ---------------------------------------------------------------------------

@router.get("/proyectos/{proyecto_id}/votos/recibidos", response_model=list[VotoRecibidoOut])
def get_votos_recibidos(
    proyecto_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)
    _get_active_membership(db, proyecto_id, current_user.id)

    rows = (
        db.query(PeerVote, User)
        .join(User, User.id == PeerVote.votante_id)
        .filter(PeerVote.votado_id == current_user.id)
        .filter(PeerVote.proyecto_id == proyecto_id)
        .all()
    )
    return [
        VotoRecibidoOut(
            id=v.id,
            votante_id=v.votante_id,
            votante_nombre=u.nombre,
        )
        for v, u in rows
    ]


# ---------------------------------------------------------------------------
# Toggle peer voting (docente)
# ---------------------------------------------------------------------------

@router.patch("/proyectos/{proyecto_id}/peer-voting")
def toggle_peer_voting(
    proyecto_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden configurar votaciones")

    group = (
        db.query(Group)
        .filter(Group.id == proyecto_id)
        .filter(Group.created_by_user_id == current_user.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado o sin permisos")

    group.peer_voting_enabled = not group.peer_voting_enabled
    db.commit()
    return {"proyecto_id": group.id, "peer_voting_enabled": group.peer_voting_enabled}
