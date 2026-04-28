from datetime import date, datetime

from pydantic import BaseModel


class GroupCreate(BaseModel):
    nombre: str
    carrera: str
    fecha_inicio: datetime
    fecha_cierre: datetime


class GroupUpdate(BaseModel):
    nombre: str
    carrera: str
    fecha_inicio: datetime
    fecha_cierre: datetime


class GroupOut(BaseModel):
    id: int
    nombre: str
    carrera: str
    fecha_inicio: datetime
    fecha_cierre: datetime
    created_by_user_id: int | None
    peer_voting_enabled: bool = False

    class Config:
        from_attributes = True


class TeacherShareTarget(BaseModel):
    id: int
    nombre: str
    username: str

    class Config:
        from_attributes = True


class GroupShareRequest(BaseModel):
    docente_username: str | None = None
    docente_id: int | None = None


class GroupShareResponse(BaseModel):
    message: str
    source_group_id: int
    shared_group_id: int
    target_docente_id: int
    target_docente_username: str
    copied_students: int


class GroupShareLinkResponse(BaseModel):
    message: str
    invite_code: str
    invite_link: str
    expires_in_minutes: int


class GroupShareAcceptRequest(BaseModel):
    token: str


class GroupInviteNotificationOut(BaseModel):
    invite_code: str
    source_group_id: int
    source_group_nombre: str
    source_group_carrera: str
    source_group_fecha_inicio: datetime
    source_group_fecha_cierre: datetime
    invited_by_docente_id: int
    invited_by_docente_username: str


class GroupInviteCreatedResponse(BaseModel):
    message: str
    invite_code: str
    target_docente_id: int
    target_docente_username: str


class GroupStudentAddRequest(BaseModel):
    participant_id: int | None = None
    usuario_id: int | None = None
    fecha_inicio: date | None = None


class GroupStudentOut(BaseModel):
    participant_id: int
    usuario_id: int
    nombre: str
    username: str
    github_username: str | None = None
    fecha_inicio: date
    fecha_fin: date | None = None


class GroupStudentCandidateOut(BaseModel):
    participant_id: int
    usuario_id: int
    nombre: str
    username: str
    github_username: str | None = None


class GroupRankingItemOut(BaseModel):
    rank: int
    usuario_id: int
    nombre: str
    github_username: str | None = None
    commits_count: int
    commits_points: float
    streak_days: int = 0
    streak_points: float = 0.0
    peer_vote_avg: float = 0.0
    peer_vote_points: float = 0.0
    promedio: float


# --- Peer voting ---

class PeerVoteCreate(BaseModel):
    votado_id: int
    estrellas: int  # 1-5


class PeerVoteOut(BaseModel):
    id: int
    votado_id: int
    votado_nombre: str
    estrellas: int

    class Config:
        from_attributes = True


class CompañeroVotable(BaseModel):
    usuario_id: int
    nombre: str
    github_username: str | None = None
    mi_voto: int | None = None


class VotoRecibidoOut(BaseModel):
    id: int
    votante_id: int
    votante_nombre: str

    class Config:
        from_attributes = True


class MiPerfilAlumno(BaseModel):
    usuario_id: int
    nombre: str
    github_username: str | None = None
    github_contributions_total: int | None = None
    proyecto_id: int | None = None
    proyecto_nombre: str | None = None
    peer_voting_enabled: bool = False
    mi_rank: int | None = None
    total_en_proyecto: int | None = None
    commits_count: int = 0
    streak_days: int = 0
    peer_vote_avg: float = 0.0
    promedio: float = 0.0


class GeneralRankingItemOut(BaseModel):
    rank: int
    group_id: int
    group_name: str
    usuario_id: int
    nombre: str
    github_username: str | None = None
    commits_count: int
    contributions_count: int
    metric_value: int
    metric_points: float
    streak_days: int = 0
    streak_points: float = 0.0
    total_score: float


class GroupStudentInviteResponse(BaseModel):
    message: str
    invite_token: str
    proyecto_id: int
    proyecto_nombre: str
    registro_url: str
    expires_in_days: int


# --- Competidores anónimos ---

class AnonymousCompetitorCreate(BaseModel):
    nombre: str
    github_username: str | None = None


class AnonymousCompetitorOut(BaseModel):
    id: int
    nombre: str
    github_username: str | None = None
    is_claimed: bool

    class Config:
        from_attributes = True
