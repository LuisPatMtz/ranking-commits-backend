from sqlalchemy import Date, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GroupUser(Base):
    __tablename__ = "proyecto_usuarios"
    __table_args__ = (
        Index(
            "uq_proyecto_usuarios_activo",
            "proyecto_id",
            "usuario_id",
            unique=True,
            postgresql_where=text("fecha_fin IS NULL"),
        ),
        Index("ix_proyecto_usuarios_proyecto_usuario", "proyecto_id", "usuario_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    fecha_inicio: Mapped[Date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[Date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
