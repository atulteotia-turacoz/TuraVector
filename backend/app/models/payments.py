"""Payment gateway settings — hand-written model for scripts/payments.sql."""
import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import DATETIME, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated import Base


class PaymentGateway(Base):
    __tablename__ = "payment_gateway"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="test")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    public_config: Mapped[Optional[dict]] = mapped_column(JSON)
    secrets: Mapped[Optional[str]] = mapped_column(Text)
    last_tested_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    last_test_ok: Mapped[Optional[int]] = mapped_column(TINYINT(1))
    last_test_message: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
