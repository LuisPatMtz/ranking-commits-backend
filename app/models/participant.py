from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Participant(Base):
    __tablename__ = "participantes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, unique=True, index=True)
    github_username: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    github_contributions_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_contributions_updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
