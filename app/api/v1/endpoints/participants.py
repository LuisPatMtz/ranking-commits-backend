from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.participant import Participant
from app.models.user import User, UserRole
from app.schemas.user import ParticipantCreate, ParticipantOut

router = APIRouter(prefix="/participantes", tags=["participantes"])


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
