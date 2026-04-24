import re
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.group import Group
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.user import User, UserRole
from app.schemas.user import ParticipantCreate, ParticipantOut, ParticipantQuickCreate, ParticipantQuickOut

router = APIRouter(prefix="/participantes", tags=["participantes"])


def _build_unique_username(db: Session, nombre: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "", nombre).lower()[:18] or "participante"
    for _ in range(10):
        candidate = f"{base}{secrets.token_hex(2)}"
        exists = db.query(User).filter(User.username == candidate).first()
        if not exists:
            return candidate
    return f"part{secrets.token_hex(4)}"


@router.post("", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
def create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.usuario_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if user.rol != UserRole.alumno:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo usuarios con rol alumno pueden ser participantes")

    exists = db.query(Participant).filter(Participant.usuario_id == payload.usuario_id).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El participante ya existe")

    participant = Participant(
        usuario_id=payload.usuario_id,
        github_username=payload.github_username,
        activo=True,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


@router.get("", response_model=list[ParticipantOut])
def list_participants(db: Session = Depends(get_db)):
    return db.query(Participant).order_by(Participant.id.desc()).all()


@router.post("/registro-rapido", response_model=ParticipantQuickOut, status_code=status.HTTP_201_CREATED)
def create_participant_quick(
    payload: ParticipantQuickCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden registrar participantes")

    group = (
        db.query(Group)
        .filter(Group.id == payload.grupo_id)
        .filter(Group.created_by_user_id == current_user.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado o sin permisos")

    nombre = payload.nombre.strip()
    if len(nombre) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre completo demasiado corto")

    username = _build_unique_username(db, nombre)
    random_password = secrets.token_urlsafe(12)

    user = User(
        nombre=nombre,
        username=username,
        password_hash=get_password_hash(random_password),
        rol=UserRole.alumno,
        activo=True,
    )
    db.add(user)
    db.flush()

    participant = Participant(
        usuario_id=user.id,
        github_username=(payload.github_username or "").strip() or None,
        activo=True,
    )
    db.add(participant)
    db.flush()

    db.add(
        GroupUser(
            grupo_id=group.id,
            usuario_id=user.id,
            fecha_inicio=date.today(),
            fecha_fin=None,
        )
    )

    db.commit()

    return ParticipantQuickOut(
        participant_id=participant.id,
        usuario_id=user.id,
        nombre=user.nombre,
        username=user.username,
        github_username=participant.github_username,
        grupo_id=group.id,
    )
