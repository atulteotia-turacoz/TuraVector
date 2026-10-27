"""Tools catalogue, subscription plans and workspace subscriptions — hand-written models for
scripts/subscriptions.sql."""
import datetime
import decimal
from typing import Optional

from sqlalchemy import DECIMAL, JSON, BigInteger, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import DATETIME, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.generated import Base

TOOL_KINDS = {"dashboard": "TuraVector dashboard", "app": "Application"}
BILLING_PERIODS = {"monthly": "Monthly", "quarterly": "Quarterly", "half_yearly": "Half-yearly", "yearly": "Yearly",
                   "lifetime": "Lifetime"}
PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "half_yearly": 6, "yearly": 12, "lifetime": None}
PLAN_AUDIENCES = {"individual": "Individuals", "organisation": "Universities / organisations", "all": "Everyone"}
SUBSCRIPTION_STATUSES = ("pending", "active", "cancelled")


class PlatformTool(Base):
    __tablename__ = "platform_tool"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    features: Mapped[Optional[list]] = mapped_column(JSON)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="app")
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    is_builtin: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)
    is_free: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class SubscriptionPlanTool(Base):
    __tablename__ = "subscription_plan_tool"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("subscription_plan.id"), nullable=False)
    tool_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_tool.id"), nullable=False)

    tool: Mapped[PlatformTool] = relationship()


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plan"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    price: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audience: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    is_featured: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_percent: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, default=18)  # GST, added on top
    sac_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    plan_tools: Mapped[list[SubscriptionPlanTool]] = relationship(cascade="all, delete-orphan")


class OrgSubscription(Base):
    __tablename__ = "org_subscription"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org_organisation.id"), nullable=False)
    plan_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("subscription_plan.id"))
    plan_name: Mapped[str] = mapped_column(String(150), nullable=False)
    tool_keys: Mapped[Optional[list]] = mapped_column(JSON)
    price: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    is_trial: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="self")
    starts_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    ends_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    gateway: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    gateway_order_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    payment_ref: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    tax_percent: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, default=0)
    tax_amount: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=0)  # GST charged on top of price
    tax_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="")  # intra | inter | overseas
    invoice_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("invoice.id"))
    cancelled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))  # runs until ends_at, then stops
    created_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    plan: Mapped[Optional[SubscriptionPlan]] = relationship()
    organisation = relationship("Organisation")
