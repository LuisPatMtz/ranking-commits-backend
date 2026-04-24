from datetime import date, datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.group import Group
from app.models.group_share_token import GroupShareToken
from app.models.group_user import GroupUser
from app.models.participant import Participant
from app.models.user import User, UserRole
from app.schemas.group import (
    GroupCreate,
    GroupInviteCreatedResponse,
    GroupInviteNotificationOut,
    GroupOut,
    GroupStudentAddRequest,
    GroupStudentCandidateOut,
    GroupStudentOut,
    GroupShareLinkResponse,
    GroupShareRequest,
    GroupShareResponse,
    TeacherShareTarget,
)

router = APIRouter(prefix="/grupos", tags=["grupos"])

SHARE_LINK_EXPIRES_MINUTES = 60 * 24


def _generate_invite_code() -> str:
    # 8-10 chars URL-safe keeps links short and easy to share.
    return token_urlsafe(6).replace("-", "").replace("_", "")[:10]


def _resolve_source_group_or_404(db: Session, group_id: int, owner_docente_id: int) -> Group:
    source_group = (
        db.query(Group)
        .filter(Group.id == group_id)
        .filter(Group.created_by_user_id == owner_docente_id)
        .first()
    )
    if not source_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado o sin permisos")
    return source_group


def _resolve_target_docente_or_404(db: Session, payload: GroupShareRequest, current_user_id: int) -> User:
    has_username = bool(payload.docente_username and payload.docente_username.strip())
    has_docente_id = payload.docente_id is not None
    if has_username == has_docente_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes enviar solo docente_username o docente_id",
        )

    target_query = db.query(User).filter(User.rol == UserRole.docente).filter(User.activo.is_(True))
    if has_docente_id:
        target_docente = target_query.filter(User.id == payload.docente_id).first()
    else:
        target_docente = target_query.filter(User.username == payload.docente_username.strip()).first()

    if not target_docente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Docente destino no encontrado")
    if target_docente.id == current_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes invitarte a ti mismo")

    return target_docente


def _ensure_invite_not_expired(invite: GroupShareToken) -> None:
    if invite.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La invitacion ha expirado")


def _resolve_owned_group_or_404(db: Session, group_id: int, current_user: User) -> Group:
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden administrar grupos")

    group = (
        db.query(Group)
        .filter(Group.id == group_id)
        .filter(Group.created_by_user_id == current_user.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado o sin permisos")
    return group


def _clone_group_for_docente(db: Session, source_group: Group, target_docente: User) -> tuple[Group, int]:
    already_exists = (
        db.query(Group)
        .filter(Group.created_by_user_id == target_docente.id)
        .filter(Group.nombre == source_group.nombre)
        .filter(Group.carrera == source_group.carrera)
        .filter(Group.semestre == source_group.semestre)
        .first()
    )
    if already_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese docente ya tiene una copia de este grupo",
        )

    shared_group = Group(
        nombre=source_group.nombre,
        carrera=source_group.carrera,
        semestre=source_group.semestre,
        created_by_user_id=target_docente.id,
    )
    db.add(shared_group)
    db.flush()

    source_members = db.query(GroupUser).filter(GroupUser.grupo_id == source_group.id).all()
    copied_students = 0
    for membership in source_members:
        db.add(
            GroupUser(
                grupo_id=shared_group.id,
                usuario_id=membership.usuario_id,
                fecha_inicio=membership.fecha_inicio,
                fecha_fin=membership.fecha_fin,
            )
        )
        copied_students += 1

    return shared_group, copied_students


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden crear grupos")

    group = Group(
        nombre=payload.nombre,
        carrera=payload.carrera,
        semestre=payload.semestre,
        created_by_user_id=current_user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("", response_model=list[GroupOut])
def list_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden consultar grupos")

    return (
        db.query(Group)
        .filter(Group.created_by_user_id == current_user.id)
        .order_by(Group.id.desc())
        .all()
    )


@router.get("/{group_id}/alumnos", response_model=list[GroupStudentOut])
def list_group_students(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = _resolve_owned_group_or_404(db, group_id, current_user)

    rows = (
        db.query(GroupUser, User, Participant)
        .join(User, User.id == GroupUser.usuario_id)
        .join(Participant, Participant.usuario_id == User.id)
        .filter(GroupUser.grupo_id == group.id)
        .order_by(User.nombre.asc())
        .all()
    )

    return [
        GroupStudentOut(
            participant_id=participant.id,
            usuario_id=user.id,
            nombre=user.nombre,
            username=user.username,
            github_username=participant.github_username,
            fecha_inicio=membership.fecha_inicio,
            fecha_fin=membership.fecha_fin,
        )
        for membership, user, participant in rows
    ]


@router.get("/{group_id}/alumnos/disponibles", response_model=list[GroupStudentCandidateOut])
def list_group_student_candidates(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = _resolve_owned_group_or_404(db, group_id, current_user)

    current_member_ids = {
        row[0]
        for row in db.query(GroupUser.usuario_id)
        .filter(GroupUser.grupo_id == group.id)
        .all()
    }

    rows = (
        db.query(User, Participant)
        .join(Participant, Participant.usuario_id == User.id)
        .filter(User.rol == UserRole.alumno)
        .filter(User.activo.is_(True))
        .filter(Participant.activo.is_(True))
        .order_by(User.nombre.asc())
        .all()
    )

    result: list[GroupStudentCandidateOut] = []
    for user, participant in rows:
        if user.id in current_member_ids:
            continue
        result.append(
            GroupStudentCandidateOut(
                participant_id=participant.id,
                usuario_id=user.id,
                nombre=user.nombre,
                username=user.username,
                github_username=participant.github_username,
            )
        )
    return result


@router.post("/{group_id}/alumnos", response_model=GroupStudentOut, status_code=status.HTTP_201_CREATED)
def add_student_to_group(
    group_id: int,
    payload: GroupStudentAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _resolve_owned_group_or_404(db, group_id, current_user)

    participant: Participant | None = None
    if payload.participant_id is not None:
        participant = db.query(Participant).filter(Participant.id == payload.participant_id).first()
    elif payload.usuario_id is not None:
        participant = db.query(Participant).filter(Participant.usuario_id == payload.usuario_id).first()
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debes enviar participant_id o usuario_id")

    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante no encontrado")
    if not participant.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El participante esta inactivo")

    user = db.query(User).filter(User.id == participant.usuario_id).first()
    if not user or user.rol != UserRole.alumno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alumno no encontrado")
    if not user.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El alumno esta inactivo")

    exists = (
        db.query(GroupUser)
        .filter(GroupUser.grupo_id == group.id)
        .filter(GroupUser.usuario_id == user.id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El alumno ya pertenece al grupo")

    membership = GroupUser(
        grupo_id=group.id,
        usuario_id=user.id,
        fecha_inicio=payload.fecha_inicio or date.today(),
        fecha_fin=None,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    participant = db.query(Participant).filter(Participant.usuario_id == user.id).first()
    return GroupStudentOut(
        participant_id=participant.id,
        usuario_id=user.id,
        nombre=user.nombre,
        username=user.username,
        github_username=participant.github_username,
        fecha_inicio=membership.fecha_inicio,
        fecha_fin=membership.fecha_fin,
    )


@router.delete("/{group_id}/alumnos/{usuario_id}")
def remove_student_from_group(
    group_id: int,
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _resolve_owned_group_or_404(db, group_id, current_user)

    membership = (
        db.query(GroupUser)
        .filter(GroupUser.grupo_id == group.id)
        .filter(GroupUser.usuario_id == usuario_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alumno no pertenece al grupo")

    db.delete(membership)
    db.commit()
    return {"message": "Alumno removido del grupo"}


@router.delete("/{group_id}/alumnos/participantes/{participant_id}")
def remove_participant_from_group(
    group_id: int,
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = _resolve_owned_group_or_404(db, group_id, current_user)

    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante no encontrado")

    membership = (
        db.query(GroupUser)
        .filter(GroupUser.grupo_id == group.id)
        .filter(GroupUser.usuario_id == participant.usuario_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante no pertenece al grupo")

    db.delete(membership)
    db.commit()
    return {"message": "Participante removido del grupo"}


@router.get("/docentes/buscar", response_model=list[TeacherShareTarget])
def search_docentes(q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden buscar destinatarios")

    query = q.strip()
    if len(query) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ingresa al menos 2 caracteres")

    return (
        db.query(User)
        .filter(User.rol == UserRole.docente)
        .filter(User.activo.is_(True))
        .filter(User.id != current_user.id)
        .filter((User.username.ilike(f"%{query}%")) | (User.nombre.ilike(f"%{query}%")))
        .order_by(User.username.asc())
        .limit(10)
        .all()
    )


@router.post("/{group_id}/compartir", response_model=GroupInviteCreatedResponse)
def share_group(
    group_id: int,
    payload: GroupShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden compartir grupos")

    source_group = _resolve_source_group_or_404(db, group_id, current_user.id)
    target_docente = _resolve_target_docente_or_404(db, payload, current_user.id)

    already_pending = (
        db.query(GroupShareToken)
        .filter(GroupShareToken.group_id == source_group.id)
        .filter(GroupShareToken.owner_docente_id == current_user.id)
        .filter(GroupShareToken.invited_docente_id == target_docente.id)
        .filter(GroupShareToken.used_by_docente_id.is_(None))
        .filter(GroupShareToken.expires_at > datetime.now(timezone.utc))
        .first()
    )
    if already_pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una invitacion pendiente para ese docente")

    invite_code = _generate_invite_code()
    expire = datetime.now(timezone.utc) + timedelta(minutes=SHARE_LINK_EXPIRES_MINUTES)
    db.add(
        GroupShareToken(
            token_jti=invite_code,
            group_id=source_group.id,
            owner_docente_id=current_user.id,
            invited_docente_id=target_docente.id,
            expires_at=expire,
        )
    )
    db.commit()

    return GroupInviteCreatedResponse(
        message="Invitacion enviada correctamente",
        invite_code=invite_code,
        target_docente_id=target_docente.id,
        target_docente_username=target_docente.username,
    )


@router.post("/{group_id}/compartir/link", response_model=GroupShareLinkResponse)
def create_group_share_link(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden generar links")

    source_group = _resolve_source_group_or_404(db, group_id, current_user.id)

    expire = datetime.now(timezone.utc) + timedelta(minutes=SHARE_LINK_EXPIRES_MINUTES)
    invite_code = _generate_invite_code()

    db.add(
        GroupShareToken(
            token_jti=invite_code,
            group_id=source_group.id,
            owner_docente_id=current_user.id,
            expires_at=expire,
        )
    )
    db.commit()

    return GroupShareLinkResponse(
        message="Link de compartir generado correctamente",
        invite_code=invite_code,
        invite_link=f"/docente?invite={invite_code}",
        expires_in_minutes=SHARE_LINK_EXPIRES_MINUTES,
    )


@router.get("/invitaciones/mias", response_model=list[GroupInviteNotificationOut])
def list_my_group_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden consultar invitaciones")

    rows = (
        db.query(GroupShareToken, Group, User)
        .join(Group, Group.id == GroupShareToken.group_id)
        .join(User, User.id == GroupShareToken.owner_docente_id)
        .filter(GroupShareToken.used_by_docente_id.is_(None))
        .filter(GroupShareToken.expires_at > datetime.now(timezone.utc))
        .filter(GroupShareToken.invited_docente_id == current_user.id)
        .order_by(GroupShareToken.created_at.desc())
        .all()
    )

    items: list[GroupInviteNotificationOut] = []
    for invite, group, owner in rows:
        items.append(
            GroupInviteNotificationOut(
                invite_code=invite.token_jti,
                source_group_id=group.id,
                source_group_nombre=group.nombre,
                source_group_carrera=group.carrera,
                source_group_semestre=group.semestre,
                invited_by_docente_id=owner.id,
                invited_by_docente_username=owner.username,
            )
        )

    return items


@router.post("/invitaciones/{invite_code}/aceptar", response_model=GroupShareResponse)
def accept_group_invite(
    invite_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != UserRole.docente:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo docentes pueden aceptar invitaciones")

    link_token = db.query(GroupShareToken).filter(GroupShareToken.token_jti == invite_code).first()
    if not link_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitacion no encontrada")
    if link_token.used_by_docente_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta invitacion ya fue utilizada")
    _ensure_invite_not_expired(link_token)

    if link_token.owner_docente_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes aceptar tu propia invitacion")

    if link_token.invited_docente_id is not None and link_token.invited_docente_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Esta invitacion no esta dirigida a tu cuenta")

    source_group = (
        db.query(Group)
        .filter(Group.id == link_token.group_id)
        .filter(Group.created_by_user_id == link_token.owner_docente_id)
        .first()
    )
    if not source_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El grupo de origen ya no existe")

    shared_group, copied_students = _clone_group_for_docente(db, source_group, current_user)
    link_token.used_by_docente_id = current_user.id
    link_token.used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(shared_group)

    return GroupShareResponse(
        message="Grupo compartido correctamente",
        source_group_id=source_group.id,
        shared_group_id=shared_group.id,
        target_docente_id=current_user.id,
        target_docente_username=current_user.username,
        copied_students=copied_students,
    )
