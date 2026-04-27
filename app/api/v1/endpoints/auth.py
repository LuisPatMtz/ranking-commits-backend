from datetime import date, datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.session import get_db
from app.models.docente_invite import DocenteInvite
from app.models.group import Group
from app.models.group_student_invite import GroupStudentInvite
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.user import User, UserRole
from app.schemas.auth import (
    InviteValidateResponse,
    LoginRequest,
    RegisterAlumnoRequest,
    RegisterDocenteRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

DOCENTE_INVITE_EXPIRES_HOURS = 72
STUDENT_INVITE_EXPIRES_DAYS = 30


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")

    if not user.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu cuenta esta inactiva")

    token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "nombre": user.nombre, "username": user.username, "rol": user.rol},
    )


# ---------------------------------------------------------------------------
# Validar invite antes de mostrar el formulario
# ---------------------------------------------------------------------------

@router.get("/invite/validate", response_model=InviteValidateResponse)
def validate_invite(token: str, tipo: str, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)

    if tipo == "docente":
        invite = db.query(DocenteInvite).filter(DocenteInvite.token == token).first()
        if not invite or invite.used_by_user_id is not None or invite.expires_at < now:
            return InviteValidateResponse(tipo="docente", valid=False)
        return InviteValidateResponse(tipo="docente", valid=True)

    if tipo == "alumno":
        invite = (
            db.query(GroupStudentInvite)
            .filter(GroupStudentInvite.token == token)
            .filter(GroupStudentInvite.activo.is_(True))
            .first()
        )
        if not invite or invite.expires_at < now or invite.usos_actuales >= invite.max_usos:
            return InviteValidateResponse(tipo="alumno", valid=False)
        group = db.query(Group).filter(Group.id == invite.grupo_id).first()
        return InviteValidateResponse(
            tipo="alumno",
            valid=True,
            grupo_nombre=group.nombre if group else None,
            grupo_id=invite.grupo_id,
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tipo debe ser 'docente' o 'alumno'")


# ---------------------------------------------------------------------------
# Registro de docente (requiere invite del admin)
# ---------------------------------------------------------------------------

@router.post("/register/docente", status_code=status.HTTP_201_CREATED)
def register_docente(payload: RegisterDocenteRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)

    invite = db.query(DocenteInvite).filter(DocenteInvite.token == payload.invite_token).first()
    if not invite or invite.used_by_user_id is not None or invite.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitacion invalida o expirada")

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username ya registrado")

    user = User(
        nombre=payload.nombre,
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        rol=UserRole.docente,
        activo=True,
    )
    db.add(user)
    db.flush()

    invite.used_by_user_id = user.id
    invite.used_at = now

    db.commit()
    return {"id": user.id, "username": user.username, "rol": user.rol}


# ---------------------------------------------------------------------------
# Registro de alumno (requiere invite de grupo del docente)
# ---------------------------------------------------------------------------

@router.post("/register/alumno", status_code=status.HTTP_201_CREATED)
def register_alumno(payload: RegisterAlumnoRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)

    invite = (
        db.query(GroupStudentInvite)
        .filter(GroupStudentInvite.token == payload.invite_token)
        .filter(GroupStudentInvite.activo.is_(True))
        .first()
    )
    if not invite or invite.expires_at < now or invite.usos_actuales >= invite.max_usos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitacion invalida, expirada o llena")

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username ya registrado")

    github_username = payload.github_username.strip() if payload.github_username else None
    if github_username:
        taken = db.query(Participant).filter(Participant.github_username == github_username).first()
        if taken:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ese username de GitHub ya esta registrado")

    user = User(
        nombre=payload.nombre,
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        rol=UserRole.alumno,
        activo=True,
    )
    db.add(user)
    db.flush()

    participant = Participant(
        usuario_id=user.id,
        github_username=github_username,
        activo=True,
    )
    db.add(participant)
    db.flush()

    membership = GroupUser(
        grupo_id=invite.grupo_id,
        usuario_id=user.id,
        fecha_inicio=date.today(),
    )
    db.add(membership)

    invite.usos_actuales += 1

    db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "rol": user.rol,
        "grupo_id": invite.grupo_id,
    }


# ---------------------------------------------------------------------------
# Admin: crear invite para un docente
# ---------------------------------------------------------------------------

@router.post("/invite/docente", status_code=status.HTTP_201_CREATED)
def create_docente_invite(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el admin puede crear invitaciones de docente")

    token = token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=DOCENTE_INVITE_EXPIRES_HOURS)

    invite = DocenteInvite(
        token=token,
        created_by_admin_id=current_user.id,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()

    return {
        "invite_token": token,
        "expires_in_hours": DOCENTE_INVITE_EXPIRES_HOURS,
        "registro_url": f"/registro?invite={token}&tipo=docente",
    }
