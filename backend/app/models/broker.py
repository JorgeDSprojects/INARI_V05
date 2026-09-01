from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.uns import TimestampMixin, _uuid


class Broker(TimestampMixin, Base):
    __tablename__ = "brokers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=1883)
    api_port: Mapped[int] = mapped_column(Integer, nullable=False, default=18083)
    username: Mapped[str | None] = mapped_column(String(255))
    password: Mapped[str | None] = mapped_column(String(255))
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
