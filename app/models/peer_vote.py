from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PeerVote(Base):
    __tablename__ = "votos_pares"
    __table_args__ = (
        UniqueConstraint("votante_id", "votado_id", "proyecto_id", name="uq_voto_par_proyecto"),
        CheckConstraint("estrellas >= 1 AND estrellas <= 5", name="ck_estrellas_rango"),
        CheckConstraint("votante_id != votado_id", name="ck_no_self_vote"),
        Index("ix_votos_pares_votado_proyecto", "votado_id", "proyecto_id"),
        Index("ix_votos_pares_votante_proyecto", "votante_id", "proyecto_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    votante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    votado_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"), nullable=False, index=True)
    estrellas: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
