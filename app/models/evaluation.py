from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TeacherEvaluation(Base):
    __tablename__ = "evaluaciones_docente"
    __table_args__ = (
        CheckConstraint("calificacion >= 0 AND calificacion <= 100", name="ck_calificacion_range"),
        # Queries de ranking: filtran por grupo y luego por alumno o por docente
        Index("ix_eval_docente_grupo_alumno", "grupo_id", "alumno_id"),
        Index("ix_eval_docente_docente_grupo", "docente_id", "grupo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    docente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id"), nullable=False, index=True)
    calificacion: Mapped[int] = mapped_column(Integer, nullable=False)
    comentario: Mapped[str | None] = mapped_column(String(600), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
