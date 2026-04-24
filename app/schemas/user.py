from pydantic import BaseModel

from app.models.user import UserRole


class UserCreate(BaseModel):
    nombre: str
    username: str
    password: str
    rol: UserRole


class UserOut(BaseModel):
    id: int
    nombre: str
    username: str
    rol: UserRole
    activo: bool

    class Config:
        from_attributes = True


class ParticipantCreate(BaseModel):
    usuario_id: int
    github_username: str | None = None


class ParticipantOut(BaseModel):
    id: int
    usuario_id: int
    github_username: str | None
    activo: bool

    class Config:
        from_attributes = True
