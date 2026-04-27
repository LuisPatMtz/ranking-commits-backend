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
from app.schemas.group import CompañeroVotable, MiPerfilAlumno, PeerVoteCreate, PeerVoteOut

router = APIRouter(tags=["votos"])


def _current_periodo() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


def _require_alumno(current_user: User) -> None:
    if current_user.rol != UserRole.alumno:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo alumnos pueden acceder a esta sección")


def _get_active_membership(db: Session, grupo_id: int, usuario_id: int) -> GroupUser:
    membership = (
        db.query(GroupUser)
        .filter(GroupUser.grupo_id == grupo_id)
        .filter(GroupUser.usuario_id == usuario_id)
        .filter(GroupUser.fecha_fin.is_(None))
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No perteneces a este grupo")
    return membership


# ---------------------------------------------------------------------------
# Perfil del alumno (su grupo, ranking y contribuciones)
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

    group = db.query(Group).filter(Group.id == membership.grupo_id).first()

    from app.models.commit import Commit
    commit_count = (
        db.query(func.count(Commit.id))
        .filter(Commit.usuario_id == current_user.id)
        .scalar() or 0
    )

    return MiPerfilAlumno(
        usuario_id=current_user.id,
        nombre=current_user.nombre,
        github_username=participant.github_username if participant else None,
        github_contributions_total=participant.github_contributions_total if participant else None,
        grupo_id=membership.grupo_id,
        grupo_nombre=group.nombre if group else None,
        peer_voting_enabled=group.peer_voting_enabled if group else False,
        commits_count=commit_count,
    )


# ---------------------------------------------------------------------------
# Compañeros a los que puedo votar en este periodo
# ---------------------------------------------------------------------------

@router.get("/grupos/{grupo_id}/votos/companeros", response_model=list[CompañeroVotable])
def get_companeros_votables(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)
    _get_active_membership(db, grupo_id, current_user.id)

    group = db.query(Group).filter(Group.id == grupo_id).first()
    if not group or not group.peer_voting_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Las votaciones no están habilitadas en este grupo")

    periodo = _current_periodo()

    members = (
        db.query(GroupUser.usuario_id, User.nombre, Participant.github_username)
        .join(User, User.id == GroupUser.usuario_id)
        .outerjoin(Participant, Participant.usuario_id == User.id)
        .filter(GroupUser.grupo_id == grupo_id)
        .filter(GroupUser.fecha_fin.is_(None))
        .filter(User.rol == UserRole.alumno)
        .filter(User.id != current_user.id)
        .order_by(User.nombre.asc())
        .all()
    )

    mis_votos_this_period = {
        v.votado_id: v.estrellas
        for v in db.query(PeerVote)
        .filter(PeerVote.votante_id == current_user.id)
        .filter(PeerVote.grupo_id == grupo_id)
        .filter(PeerVote.periodo == periodo)
        .all()
    }

    return [
        CompañeroVotable(
            usuario_id=m.usuario_id,
            nombre=m.nombre,
            github_username=m.github_username,
            mi_voto=mis_votos_this_period.get(m.usuario_id),
        )
        for m in members
    ]


# ---------------------------------------------------------------------------
# Votar a un compañero (crea o actualiza el voto del periodo actual)
# ---------------------------------------------------------------------------

@router.post("/grupos/{grupo_id}/votos", response_model=PeerVoteOut, status_code=status.HTTP_201_CREATED)
def votar_companero(
    grupo_id: int,
    payload: PeerVoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)
    _get_active_membership(db, grupo_id, current_user.id)

    group = db.query(Group).filter(Group.id == grupo_id).first()
    if not group or not group.peer_voting_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Las votaciones no están habilitadas en este grupo")

    if payload.votado_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes votarte a ti mismo")

    if payload.estrellas < 1 or payload.estrellas > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las estrellas deben ser entre 1 y 5")

    _get_active_membership(db, grupo_id, payload.votado_id)

    votado = db.query(User).filter(User.id == payload.votado_id).first()
    if not votado or votado.rol != UserRole.alumno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compañero no encontrado")

    periodo = _current_periodo()

    existing = (
        db.query(PeerVote)
        .filter(PeerVote.votante_id == current_user.id)
        .filter(PeerVote.votado_id == payload.votado_id)
        .filter(PeerVote.grupo_id == grupo_id)
        .filter(PeerVote.periodo == periodo)
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
            grupo_id=grupo_id,
            estrellas=payload.estrellas,
            periodo=periodo,
        )
        db.add(vote)
        db.commit()
        db.refresh(vote)

    return PeerVoteOut(
        id=vote.id,
        votado_id=vote.votado_id,
        votado_nombre=votado.nombre,
        estrellas=vote.estrellas,
        periodo=vote.periodo,
    )


# ---------------------------------------------------------------------------
# Mis votos emitidos este periodo en un grupo
# ---------------------------------------------------------------------------

@router.get("/grupos/{grupo_id}/votos/mis-votos", response_model=list[PeerVoteOut])
def get_mis_votos(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_alumno(current_user)
    _get_active_membership(db, grupo_id, current_user.id)

    periodo = _current_periodo()
    rows = (
        db.query(PeerVote, User)
        .join(User, User.id == PeerVote.votado_id)
        .filter(PeerVote.votante_id == current_user.id)
        .filter(PeerVote.grupo_id == grupo_id)
        .filter(PeerVote.periodo == periodo)
        .all()
    )
    return [
        PeerVoteOut(id=v.id, votado_id=v.votado_id, votado_nombre=u.nombre, estrellas=v.estrellas, periodo=v.periodo)
        for v, u in rows
    ]


# ---------------------------------------------------------------------------
# Toggle peer voting (docente)
# ---------------------------------------------------------------------------

@router.patch("/grupos/{grupo_id}/peer-voting")
def toggle_peer_voting(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden configurar votaciones")

    group = (
        db.query(Group)
        .filter(Group.id == grupo_id)
        .filter(Group.created_by_user_id == current_user.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado o sin permisos")

    group.peer_voting_enabled = not group.peer_voting_enabled
    db.commit()
    return {"grupo_id": group.id, "peer_voting_enabled": group.peer_voting_enabled}
