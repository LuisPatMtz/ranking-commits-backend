from pydantic import BaseModel

from app.models.user import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    nombre: str
    username: str
    password: str


class AuthUserSummary(BaseModel):
    id: int
    nombre: str
    username: str
    rol: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserSummary
