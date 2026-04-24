from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Ranking(Base):
    __tablename__ = "ranking"
    __table_args__ = (CheckConstraint("total >= 0 AND total <= 500", name="ck_total_range"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id"), nullable=False, index=True)
    commits_365: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    puntos_commits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    puntos_docente: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    puntos_proyecto: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fecha_calculo: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
