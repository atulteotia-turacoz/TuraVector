"""Rate cards — hand-written models for scripts/rates.sql."""
import datetime
import decimal
from typing import Optional

from sqlalchemy import DECIMAL, BigInteger, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import DATETIME, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.generated import Base

RATE_UNITS = {"per_document": "Per document", "per_page": "Per page", "per_word": "Per word",
              "per_hour": "Per hour", "fixed": "Fixed"}


class RateService(Base):
    """A service on the standard rate card."""
    __tablename__ = "rate_service"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")  # "" = no unit
    sac_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")  # GST service code
    standard_rate: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=0)
    tax_percent: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, default=0)
    tax_overseas: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)  # taxed for clients abroad
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class RateCardItem(Base):
    """A standard service on one university / organisation's rate card, at that workspace's rate."""
    __tablename__ = "rate_card_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org_organisation.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rate_service.id"), nullable=False)
    rate: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    notes: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    service: Mapped[RateService] = relationship()
