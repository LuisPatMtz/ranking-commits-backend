from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GroupStudentInvite(Base):
    __tablename__ = "invitaciones_alumno_proyecto"
    __table_args__ = (
        Index("ix_student_invite_proyecto_activo", "proyecto_id", "activo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"), nullable=False, index=True)
    created_by_docente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    max_usos: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    usos_actuales: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
