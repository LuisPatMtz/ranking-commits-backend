from sqlalchemy import Date, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GroupUser(Base):
    __tablename__ = "grupo_usuarios"
    __table_args__ = (
        # Un alumno no puede estar activo dos veces en el mismo grupo
        Index(
            "uq_grupo_usuarios_activo",
            "grupo_id",
            "usuario_id",
            unique=True,
            postgresql_where=text("fecha_fin IS NULL"),
        ),
        Index("ix_grupo_usuarios_grupo_usuario", "grupo_id", "usuario_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    fecha_inicio: Mapped[Date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[Date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
