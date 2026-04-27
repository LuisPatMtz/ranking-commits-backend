from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PeerVote(Base):
    __tablename__ = "votos_pares"
    __table_args__ = (
        # Un alumno solo puede votar una vez por compañero por mes por grupo
        UniqueConstraint("votante_id", "votado_id", "grupo_id", "periodo", name="uq_voto_par_periodo"),
        CheckConstraint("estrellas >= 1 AND estrellas <= 5", name="ck_estrellas_rango"),
        CheckConstraint("votante_id != votado_id", name="ck_no_self_vote"),
        Index("ix_votos_pares_votado_grupo", "votado_id", "grupo_id"),
        Index("ix_votos_pares_votante_grupo_periodo", "votante_id", "grupo_id", "periodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    votante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    votado_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id"), nullable=False, index=True)
    estrellas: Mapped[int] = mapped_column(Integer, nullable=False)
    # "YYYY-MM" — limita a un voto por par por mes
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
