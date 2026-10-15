"""Reports & exports — port of library.views.reports_view, export_report_view, export_section_view,
plus a custom From–To date range."""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.utils import user_tz
from app.database import get_db
from app.models import User, utcnow
from app.services import users_dashboard as dash
from app.services import users_exports as exp
from app.services.users_common import deny, document_counts, manager_only

router = APIRouter(prefix="/api/users/reports", tags=["users"])

MANAGER_DASHBOARD = "/content-lab-management/dashboard/"
REPORTS = "/content-lab-management/reports/"


def _file(content: bytes, filename: str) -> Response:
    media = exp.XLSX if filename.endswith(".xlsx") else "application/pdf"
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _period(user: User, date_range: str, date_from: str, date_to: str) -> dash.Period:
    """Preset (7/30/90/365 days) or a custom From–To range, in the viewer's own days."""
    try:
        return dash.resolve_period(date_range, date_from, date_to, user_tz(user))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.get("")
def reports(date_range: str = "30", date_from: str = "", date_to: str = "", user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    if not manager_only(user):
        deny("You do not have permission to view reports", MANAGER_DASHBOARD)
    return dash.reports(db, date_range, _period(user, date_range, date_from, date_to))


@router.get("/export")
def export_report(format: str = "excel", date_range: str = "30", date_from: str = "", date_to: str = "",
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_only(user):
        deny("You do not have permission to export reports", REPORTS)
    period = _period(user, date_range, date_from, date_to)
    report = {
        "period": period.name, "start_date": period.start,
        "end_date": (period.end - datetime.timedelta(seconds=1)) if period.end else utcnow(),
        **dash.report_numbers(db, period.start, period.end),
        "recent_documents": dash.recent_documents(db, 10, period),
    }
    if format == "excel":
        return _file(*exp.excel_report(report))
    if format == "pdf":
        return _file(*exp.pdf_report(report))
    raise HTTPException(400, "Invalid export format")


@router.get("/export-section")
def export_section(section: str = "recent_documents", format: str = "excel", date_range: str = "30",
                   date_from: str = "", date_to: str = "", user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if not manager_only(user):
        deny("You do not have permission to export reports", REPORTS)
    period = _period(user, date_range, date_from, date_to)
    period_name = period.name
    if section == "recent_documents":
        data = dash.recent_documents(db, 50, period)
        return _file(*(exp.recent_documents_excel(data, period_name) if format == "excel"
                       else exp.recent_documents_pdf(data, period_name)))
    if section == "top_users":
        data = dash.top_users(db, 50, period)
        return _file(*(exp.top_users_excel(data, period_name) if format == "excel"
                       else exp.top_users_pdf(data, period_name)))
    if section == "recent_users":
        users = dash.recent_users(db, 50, period)
        if format == "excel":
            return _file(*exp.recent_users_excel(users, document_counts(db, [u.id for u in users]), period_name))
        return _file(*exp.recent_users_pdf(users, period_name))
    raise HTTPException(400, "Invalid section")
