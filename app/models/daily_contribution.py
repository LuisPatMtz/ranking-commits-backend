from sqlalchemy import Date, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DailyContribution(Base):
    __tablename__ = "contribuciones_diarias"
    __table_args__ = (
        UniqueConstraint("usuario_id", "fecha", name="uq_daily_contribution_user_date"),
        Index("ix_daily_contribution_usuario_fecha", "usuario_id", "fecha"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    fecha: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
