from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ProjectEvaluation(Base):
    __tablename__ = "evaluaciones_proyecto"
    __table_args__ = (
        CheckConstraint("calificacion >= 0 AND calificacion <= 100", name="ck_proyecto_calificacion_range"),
        # Un docente tiene una sola nota de proyecto por alumno por proyecto
        UniqueConstraint("alumno_id", "docente_id", "proyecto_id", name="uq_eval_proyecto_alumno_docente_proyecto"),
        Index("ix_eval_proyecto_proyecto_alumno", "proyecto_id", "alumno_id"),
        Index("ix_eval_proyecto_docente_proyecto", "docente_id", "proyecto_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    docente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"), nullable=False, index=True)
    calificacion: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)