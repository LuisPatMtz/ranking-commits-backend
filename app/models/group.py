from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Group(Base):
    __tablename__ = "grupos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    carrera: Mapped[str] = mapped_column(String(120), nullable=False)
    semestre: Mapped[int] = mapped_column(Integer, nullable=False)
    turno: Mapped[str] = mapped_column(String(40), nullable=False)
    periodo: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
