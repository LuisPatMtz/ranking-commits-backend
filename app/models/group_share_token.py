from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GroupShareToken(Base):
    __tablename__ = "group_share_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("grupos.id"), nullable=False, index=True)
    owner_docente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    invited_docente_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_by_docente_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    used_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)