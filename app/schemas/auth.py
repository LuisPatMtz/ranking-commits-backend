from pydantic import BaseModel

from app.models.user import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterDocenteRequest(BaseModel):
    invite_token: str
    nombre: str
    username: str
    password: str


class RegisterAlumnoRequest(BaseModel):
    invite_token: str
    nombre: str
    username: str
    password: str
    github_username: str | None = None


class AuthUserSummary(BaseModel):
    id: int
    nombre: str
    username: str
    rol: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserSummary


class InviteValidateResponse(BaseModel):
    tipo: str
    valid: bool
    grupo_nombre: str | None = None
    grupo_id: int | None = None
