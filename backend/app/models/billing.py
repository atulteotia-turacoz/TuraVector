"""Billing — hand-written models for scripts/billing.sql."""
import datetime
import decimal
from typing import Optional

from sqlalchemy import DECIMAL, JSON, BigInteger, Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import DATETIME, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.generated import AuthenticationUser, Base
from app.models.organisations import Organisation

BILLING_CYCLES = {"per_submission": "Per submission", "monthly": "Monthly"}
INVOICE_STATUSES = {
    "pending_turacoz": "Awaiting Turacoz approval",
    "pending_client": "Awaiting your approval",
    "awaiting_payment": "Approved · awaiting payment",
    "paid": "Paid",
    "rejected": "Cancelled",
}


class BillingSettings(Base):
    """Turacoz's own billing details (one row) and the invoice number counter."""
    __tablename__ = "billing_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    state_code: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India")
    gstin: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    pan: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    invoice_prefix: Mapped[str] = mapped_column(String(10), nullable=False, default="TC")
    bank_details: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    terms: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    sequence_year: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    sequence_next: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # invoice reminders (platform default; a workspace may switch them off or customise them)
    reminders_enabled: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=1)
    reminder_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    reminder_repeat_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    reminder_max: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    remind_turacoz: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=1)
    remind_client: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=1)
    remind_payment: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=1)
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class OrgBillingProfile(Base):
    """Who a university / organisation's invoices are made out to, and how often."""
    __tablename__ = "org_billing_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org_organisation.id"), nullable=False, unique=True)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    state_code: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India")
    gstin: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    billing_email: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    billing_cycle: Mapped[str] = mapped_column(String(20), nullable=False, default="per_submission")
    reminder_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="default")  # default | off | custom
    reminder_after_days: Mapped[Optional[int]] = mapped_column(Integer)
    reminder_repeat_days: Mapped[Optional[int]] = mapped_column(Integer)
    reminder_max: Mapped[Optional[int]] = mapped_column(Integer)
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class BillingApprover(Base):
    """A Turacoz user who may approve invoices (superusers always may)."""
    __tablename__ = "billing_approver"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("authentication_user.id"), nullable=False, unique=True)
    added_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    user: Mapped[AuthenticationUser] = relationship(foreign_keys=[user_id])


class Invoice(Base):
    __tablename__ = "invoice"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    organisation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org_organisation.id"), nullable=False)
    cycle: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[Optional[datetime.date]] = mapped_column(Date)
    period_end: Mapped[Optional[datetime.date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    tax_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    subtotal: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)
    cgst: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)
    sgst: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)
    igst: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)
    total: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)
    seller: Mapped[Optional[dict]] = mapped_column(JSON)
    buyer: Mapped[Optional[dict]] = mapped_column(JSON)
    turacoz_approved_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    turacoz_approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    client_approved_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    client_approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    turacoz_remarks: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    client_remarks: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    gateway: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    gateway_order_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    payment_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    status_changed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    reminders_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reminder_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    organisation: Mapped[Organisation] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", order_by="InvoiceLine.id",
                                                      cascade="all, delete-orphan")
    events: Mapped[list["InvoiceEvent"]] = relationship(order_by="InvoiceEvent.id", cascade="all, delete-orphan")
    requests: Mapped[list["BillingRequest"]] = relationship(back_populates="invoice", order_by="BillingRequest.id")


class BillingRequest(Base):
    """Services a member asked for with one submission (a document upload or written text)."""
    __tablename__ = "billing_request"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org_organisation.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("authentication_user.id"), nullable=False)
    document_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    document_version_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    requirement: Mapped[Optional[str]] = mapped_column(Text)
    invoice_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("invoice.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    user: Mapped[AuthenticationUser] = relationship(foreign_keys=[user_id])
    invoice: Mapped[Optional[Invoice]] = relationship(back_populates="requests")
    items: Mapped[list["BillingRequestItem"]] = relationship(back_populates="request", order_by="BillingRequestItem.id",
                                                             cascade="all, delete-orphan")


class BillingRequestItem(Base):
    __tablename__ = "billing_request_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("billing_request.id"), nullable=False)
    service_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("rate_service.id"))
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    sac_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    quantity: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=1)
    rate: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    tax_percent: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, default=0)
    tax_overseas: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)

    request: Mapped[BillingRequest] = relationship(back_populates="items")


class InvoiceLine(Base):
    __tablename__ = "invoice_line"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("invoice.id"), nullable=False)
    request_item_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("billing_request_item.id"))
    description: Mapped[str] = mapped_column(String(400), nullable=False)
    sac_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    quantity: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    rate: Mapped[decimal.Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False)
    tax_percent: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, default=0)
    tax_overseas: Mapped[int] = mapped_column(TINYINT(1), nullable=False, default=0)
    cgst: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)
    sgst: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)
    igst: Mapped[decimal.Decimal] = mapped_column(DECIMAL(14, 2), nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class InvoiceEvent(Base):
    __tablename__ = "invoice_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("invoice.id"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("authentication_user.id"))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    user: Mapped[Optional[AuthenticationUser]] = relationship(foreign_keys=[user_id])
