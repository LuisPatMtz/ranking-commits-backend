from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Ranking(Base):
    __tablename__ = "ranking"
    __table_args__ = (
        # Cada alumno tiene un único snapshot por proyecto
        UniqueConstraint("usuario_id", "proyecto_id", name="uq_ranking_usuario_proyecto"),
        CheckConstraint("total >= 0 AND total <= 100", name="ck_total_range"),
        # Consultas de ranking ordenadas por total descendente dentro de un proyecto
        Index("ix_ranking_proyecto_total", "proyecto_id", "total"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"), nullable=False, index=True)
    commits_365: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    puntos_commits: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    puntos_docente: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    puntos_proyecto: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fecha_calculo: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
