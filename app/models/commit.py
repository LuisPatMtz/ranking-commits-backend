from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("sha", name="uq_commit_sha"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sha: Mapped[str] = mapped_column(String(100), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    repositorio_id: Mapped[int] = mapped_column(ForeignKey("repositorios.id"), nullable=False, index=True)
    mensaje: Mapped[str] = mapped_column(String(500), nullable=False)
    fecha: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    puntos: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
