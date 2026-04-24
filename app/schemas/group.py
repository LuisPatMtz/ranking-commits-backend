from datetime import date

from pydantic import BaseModel


class GroupCreate(BaseModel):
    nombre: str
    carrera: str
    semestre: int


class GroupOut(BaseModel):
    id: int
    nombre: str
    carrera: str
    semestre: int
    created_by_user_id: int | None

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
    source_group_semestre: int
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
    docente_grade: float
    proyecto_grade: float
    promedio: float


class GroupRankingGradesUpdateRequest(BaseModel):
    usuario_id: int
    docente_grade: float | None = None
    proyecto_grade: float | None = None