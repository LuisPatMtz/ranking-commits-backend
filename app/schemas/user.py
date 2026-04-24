from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class UserCreate(BaseModel):
    nombre: str
    email: EmailStr
    password: str
    rol: UserRole
    github_username: str | None = None


class UserOut(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    github_username: str | None = None
    rol: UserRole
    activo: bool

    class Config:
        from_attributes = True
