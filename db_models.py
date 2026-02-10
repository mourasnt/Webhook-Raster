from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    webhook_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(Text)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    placa_encrypted: Mapped[str | None] = mapped_column(Text)
    cpf_encrypted: Mapped[str | None] = mapped_column(Text)
    placa_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    cpf_hash: Mapped[str | None] = mapped_column(String(64), index=True)
