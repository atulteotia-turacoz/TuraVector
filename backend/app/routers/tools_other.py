"""Other Documents dashboard, analytics, export data and journal selector.

Port of documents.views.other_documents_dashboard_view, analytics_view, export_data_view,
journal_selector_view, journal_search_api and save_journal_api.
(conference_selector_view only renders a static "coming soon" page — no API needed.)
"""
import csv
import datetime
import io
import json

from fastapi import APIRouter, Body, Depends, Form, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.files import media_url
from app.core.permissions import can
from app.core.utils import format_datetime_for_user, iso, localize_datetime, user_tz
from app.database import get_db
from app.models import (
    AssignedReviewer, Document, Journal, User, UserJournalSelection, utcnow,
)
from app.services import tools_journals

router = APIRouter(prefix="/api/tools", tags=["tools"])

STAGE_DISPLAY = {0: 'Draft', 1: 'Under Review', 2: 'Approved', 3: 'Draft Under Revision'}


def _full_name(u: User) -> str:
    return f"{u.first_name or ''} {u.last_name or ''}".strip()


# ---------------------------------------------------------------- Other Documents dashboard
@router.get('/other-documents')
def other_documents_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can(db, user, 'can_access_other_documents_dashboard'):
        raise HTTPException(403, 'You do not have permission to access the Other Document Types dashboard.')
    saved_journals_count = db.execute(
        select(func.count(UserJournalSelection.id)).where(UserJournalSelection.user_id == user.id)).scalar_one()
    return {
        'dashboard_type': 'other_documents',
        'saved_journals_count': saved_journals_count,
    }


# ---------------------------------------------------------------- Analytics
PERIODS = {
    '7': (7, 'Last 7 days'), '30': (30, 'Last 30 days'), '90': (90, 'Last 3 months'),
    '180': (180, 'Last 6 months'), '365': (365, 'Last year'),
}


@router.get('/analytics')
def analytics(period: str = '30', user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    time_period = period
    end_date = utcnow()
    if time_period in PERIODS:
        days, period_label = PERIODS[time_period]
        start_date = end_date - datetime.timedelta(days=days)
    elif time_period == 'all':
        tz = user_tz(user)
        start_date = tz.localize(datetime.datetime(2000, 1, 1)).astimezone(datetime.timezone.utc).replace(tzinfo=None)
        period_label = "All time"
    else:
        start_date = end_date - datetime.timedelta(days=30)
        period_label = "Last 30 days"

    def scalar(stmt):
        return db.execute(stmt).scalar_one()

    total_documents = scalar(select(func.count(Document.id)).where(Document.is_active == 1))
    documents_in_period = scalar(select(func.count(Document.id)).where(Document.is_active == 1,
                                                                      Document.created_at >= start_date))
    documents_by_status = [
        {'stage_status': s, 'count': c} for s, c in db.execute(
            select(Document.stage_status, func.count(Document.id)).where(Document.is_active == 1)
            .group_by(Document.stage_status).order_by(Document.stage_status)).all()
    ]
    total_users = scalar(select(func.count(User.id)).where(User.is_active == 1))
    active_users_in_period = scalar(select(func.count(User.id)).where(User.is_active == 1, User.last_login >= start_date))
    total_reviews = scalar(select(func.count(AssignedReviewer.id)).where(AssignedReviewer.is_active == 1))
    completed_reviews = scalar(select(func.count(AssignedReviewer.id)).where(
        AssignedReviewer.is_active == 1, AssignedReviewer.completed_at.is_not(None)))
    pending_reviews = scalar(select(func.count(AssignedReviewer.id)).where(
        AssignedReviewer.is_active == 1, AssignedReviewer.completed_at.is_(None)))
    total_journals = scalar(select(func.count(Journal.id)).where(Journal.is_active == 1))

    monthly_uploads = []
    now = utcnow()
    for i in range(6):
        month_start = now - datetime.timedelta(days=30 * (i + 1))
        month_end = now - datetime.timedelta(days=30 * i)
        c = scalar(select(func.count(Document.id)).where(Document.is_active == 1, Document.created_at >= month_start,
                                                         Document.created_at < month_end))
        monthly_uploads.append({'month': month_start.strftime('%b %Y'), 'count': c})
    monthly_uploads.reverse()

    user_type_distribution = [
        {'user_type': t, 'count': c} for t, c in db.execute(
            select(User.user_type, func.count(User.id)).where(User.is_active == 1)
            .group_by(User.user_type).order_by(User.user_type)).all()
    ]

    upload_count = func.count(Document.id).label('upload_count')
    top = db.execute(
        select(User, upload_count).join(Document, Document.user_id == User.id)
        .where(User.is_active == 1, Document.created_at >= start_date, Document.is_active == 1)
        .group_by(User.id).order_by(upload_count.desc()).limit(5)
    ).all()

    return {
        'page_title': 'Analytics Dashboard',
        'total_documents': total_documents,
        'documents_in_period': documents_in_period,
        'documents_by_status': documents_by_status,
        'total_users': total_users,
        'active_users_in_period': active_users_in_period,
        'total_reviews': total_reviews,
        'completed_reviews': completed_reviews,
        'pending_reviews': pending_reviews,
        'total_journals': total_journals,
        'monthly_uploads': monthly_uploads,
        'user_type_distribution': user_type_distribution,
        'top_uploaders': [{'id': u.id, 'full_name': _full_name(u), 'email': u.email, 'upload_count': n} for u, n in top],
        'start_date': iso(start_date),
        'end_date': iso(end_date),
        'period_label': period_label,
        'selected_period': time_period,
    }


# ---------------------------------------------------------------- Export data
@router.get('/export-data')
def export_data_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        'page_title': 'Export Data',
        'documents_count': db.execute(select(func.count(Document.id)).where(
            Document.user_id == user.id, Document.is_active == 1)).scalar_one(),
        'journals_count': db.execute(select(func.count(UserJournalSelection.id)).where(
            UserJournalSelection.user_id == user.id)).scalar_one(),
    }


def _export_payload(db: Session, user: User, export_type: str) -> dict:
    data: dict = {}
    if export_type in ['all', 'documents']:
        documents = db.execute(select(Document).where(Document.user_id == user.id, Document.is_active == 1)
                               .order_by(Document.id)).scalars().all()
        data['documents'] = [{
            'id': doc.id,
            'title': doc.document_name,
            'document_number': doc.document_number,
            'description': getattr(doc, 'description', ''),
            'stage_status': STAGE_DISPLAY.get(doc.stage_status, doc.stage_status),
            'document_type': doc.document_type.name if doc.document_type else '',
            'brand': doc.brand.name if doc.brand else '',
            'country': doc.country.name if doc.country else '',
            'therapeutic_area': doc.therapeutic_area.name if doc.therapeutic_area else '',
            'course': doc.course.name if doc.course else '',
            'project': doc.project.name if doc.project else '',
            'created_at': format_datetime_for_user(doc.created_at, user),
            'updated_at': format_datetime_for_user(doc.updated_at, user),
        } for doc in documents]

    if export_type in ['all', 'journals']:
        selections = db.execute(select(UserJournalSelection).where(UserJournalSelection.user_id == user.id)
                                .order_by(UserJournalSelection.selected_at.desc())).scalars().all()
        data['saved_journals'] = [{
            'journal_name': js.journal.name,
            'publisher': js.journal.publisher or '',
            'impact_factor': float(js.journal.journal_impact_factor) if js.journal.journal_impact_factor else None,
            'impact_factor_year': js.journal.impact_factor_year,
            'publishing_model': tools_journals.PUBLISHING_MODEL_DISPLAY.get(js.journal.publishing_model,
                                                                            js.journal.publishing_model),
            'issn': js.journal.issn or '',
            'eissn': js.journal.eissn or '',
            'is_favorite': bool(js.is_favorite),
            'manuscript_title': js.manuscript_title or '',
            'notes': js.notes or '',
            'selected_at': format_datetime_for_user(js.selected_at, user),
        } for js in selections]

    return data


@router.post('/export-data')
def export_data(export_type: str = Form('all'), export_format: str = Form('json'),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = _export_payload(db, user, export_type)
    stamp = localize_datetime(utcnow(), user).strftime("%Y%m%d_%H%M%S")
    if export_format == 'json':
        return Response(json.dumps(data, indent=2), media_type='application/json',
                        headers={'Content-Disposition': f'attachment; filename="turavector_export_{stamp}.json"'})
    if export_format == 'csv':
        buf = io.StringIO()
        writer = csv.writer(buf)
        if 'documents' in data:
            writer.writerow(['=== DOCUMENTS ==='])
            writer.writerow(['ID', 'Title', 'Document Number', 'Description', 'Status', 'Type', 'Brand', 'Country',
                             'Therapeutic Area', 'Created', 'Updated'])
            for doc in data['documents']:
                writer.writerow([
                    doc['id'], doc['title'], doc['document_number'], doc.get('description', ''), doc['stage_status'],
                    doc['document_type'], doc['brand'], doc['country'],
                    doc['therapeutic_area'], doc['created_at'], doc['updated_at'],
                ])
            writer.writerow([])
        if 'saved_journals' in data:
            writer.writerow(['=== SAVED JOURNALS ==='])
            writer.writerow(['Journal Name', 'Publisher', 'Impact Factor', 'Favorite', 'Manuscript Title', 'Notes',
                             'Selected Date'])
            for journal in data['saved_journals']:
                writer.writerow([
                    journal['journal_name'], journal['publisher'], journal['impact_factor'],
                    'Yes' if journal['is_favorite'] else 'No', journal['manuscript_title'],
                    journal['notes'], journal['selected_at'],
                ])
            writer.writerow([])
        return Response(buf.getvalue(), media_type='text/csv',
                        headers={'Content-Disposition': f'attachment; filename="turavector_export_{stamp}.csv"'})
    # Django left `response` unbound for any other format (UnboundLocalError → 500)
    raise HTTPException(500, "cannot access local variable 'response' where it is not associated with a value")


# ---------------------------------------------------------------- Journal selector
def _saved_journal(sel: UserJournalSelection) -> dict:
    j = sel.journal
    return {
        'id': sel.id,
        'manuscript_title': sel.manuscript_title,
        'notes': sel.notes,
        'is_favorite': bool(sel.is_favorite),
        'selected_at': iso(sel.selected_at),
        'journal': {
            'id': j.id, 'name': j.name, 'publisher': j.publisher,
            'publishing_model': tools_journals.PUBLISHING_MODEL_DISPLAY.get(j.publishing_model, j.publishing_model),
            'impact_factor': str(j.journal_impact_factor) if j.journal_impact_factor else None,
            'impact_factor_year': j.impact_factor_year,
            'submission_to_decision_days': j.submission_to_decision_days,
            'cover_image_url': media_url(j.cover_image) if j.cover_image else None,
            'submission_url': j.submission_url, 'website_url': j.website_url,
        },
    }


@router.get('/journal-selector')
def journal_selector(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    selections = db.execute(select(UserJournalSelection).where(UserJournalSelection.user_id == user.id)
                            .order_by(UserJournalSelection.selected_at.desc())).scalars().all()
    return {
        'page_title': 'Journal Selector',
        'user_selections': [_saved_journal(s) for s in selections],
        'saved_journals_count': len(selections),
    }


@router.post('/journal-search')
def journal_search(payload: dict = Body(default_factory=dict), user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    search_query = str(payload.get('query', '') or '').strip()
    if not search_query:
        raise HTTPException(400, 'Search query is required')
    try:
        return tools_journals.search_journals(db, user, search_query)
    except Exception as fallback_error:  # noqa: BLE001
        raise HTTPException(500, f'Search failed: {str(fallback_error)}')


@router.post('/save-journal')
def save_journal(payload: dict = Body(default_factory=dict), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    journal_id = payload.get('journal_id')
    action = payload.get('action', 'save')
    if not journal_id:
        raise HTTPException(400, 'Journal ID is required')
    try:
        journal = db.execute(select(Journal).where(Journal.id == int(journal_id), Journal.is_active == 1)).scalar_one_or_none()
    except (TypeError, ValueError) as e:
        raise HTTPException(500, f'An error occurred: {str(e)}')
    if journal is None:
        raise HTTPException(404, 'No Journal matches the given query.')
    try:
        if action == 'save':
            selection = db.execute(select(UserJournalSelection).where(
                UserJournalSelection.user_id == user.id, UserJournalSelection.journal_id == journal.id)).scalar_one_or_none()
            if selection is None:
                db.add(UserJournalSelection(
                    user_id=user.id, journal_id=journal.id,
                    manuscript_title=payload.get('manuscript_title', ''),
                    manuscript_abstract=payload.get('manuscript_abstract', ''),
                    notes=payload.get('notes', ''),
                    is_favorite=0,
                ))
            else:
                selection.manuscript_title = payload.get('manuscript_title', selection.manuscript_title)
                selection.manuscript_abstract = payload.get('manuscript_abstract', selection.manuscript_abstract)
                selection.notes = payload.get('notes', selection.notes)
                selection.updated_at = utcnow()
            db.commit()
            return {'message': 'Journal saved successfully', 'is_saved': True}
        if action == 'unsave':
            for sel in db.execute(select(UserJournalSelection).where(
                    UserJournalSelection.user_id == user.id, UserJournalSelection.journal_id == journal.id)).scalars():
                db.delete(sel)
            db.commit()
            return {'message': 'Journal removed from saved list', 'is_saved': False}
        raise HTTPException(400, 'Invalid action. Use "save" or "unsave"')
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(500, f'An error occurred: {str(e)}')

