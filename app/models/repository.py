from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Repository(Base):
    __tablename__ = "repositorios"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    repo: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    proyecto_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
