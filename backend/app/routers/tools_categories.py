"""Category management (document types, countries, brands, therapeutic areas), the legacy
country upload, bulk import and template downloads.

Port of documents.views.document_types_view … therapeutic_area_toggle_view,
country_upload_view and documents/bulk_import_views.py.
"""
import math

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import is_admin_like
from app.core.utils import iso
from app.database import get_db
from app.models import Brand, Country, DocumentType, TherapeuticArea, User, utcnow
from app.services import tools_bulk_import as bulk

router = APIRouter(prefix="/api/tools", tags=["tools"])

# kind -> (model, has_code, category_name (list page), singular (forms), message label, required message)
CATEGORIES = {
    'document-types': (DocumentType, False, 'Document Types', 'Document Type', 'Document type',
                       'Document type name is required'),
    'countries': (Country, True, 'Countries', 'Country', 'Country', 'Country name and code are required'),
    'brands': (Brand, True, 'Brands', 'Brand', 'Brand', 'Brand name and code are required'),
    'therapeutic-areas': (TherapeuticArea, False, 'Therapeutic Areas', 'Therapeutic Area', 'Therapeutic area',
                          'Therapeutic area name is required'),
}
PAGE_TITLES = {
    'document-types': 'Document Types Management',
    'countries': 'Countries Management',
    'brands': 'Brands Management',
    'therapeutic-areas': 'Therapeutic Areas Management',
}


def require_category_admin(user: User = Depends(get_current_user)) -> User:
    """check_admin_permission(request)"""
    if not is_admin_like(user):
        raise HTTPException(403, 'You do not have permission to manage categories')
    return user


def _category(kind: str):
    if kind not in CATEGORIES:
        raise HTTPException(404, 'Not found')
    return CATEGORIES[kind]


def _item(obj, has_code: bool) -> dict:
    d = {
        'id': obj.id,
        'name': obj.name,
        'is_active': bool(obj.is_active),
        'created_at': iso(obj.created_at),
        'updated_at': iso(obj.updated_at),
    }
    if has_code:
        d['code_name'] = obj.code_name
    return d


def _db_error(e: Exception) -> str:
    orig = getattr(e, 'orig', None)
    return str(orig) if orig is not None else str(e)


@router.get('/categories/{kind}')
def category_list(kind: str, search: str = '', page: str | None = None,
                  user: User = Depends(require_category_admin), db: Session = Depends(get_db)):
    model, has_code, category_name, singular, _label, _req = _category(kind)
    stmt = select(model)
    search_query = search.strip() if kind == 'countries' else ''
    if search_query:
        stmt = stmt.where(or_(model.name.ilike(f'%{search_query}%'), model.code_name.ilike(f'%{search_query}%')))
    stmt = stmt.order_by(model.name)
    filtered = stmt.subquery()
    total = db.execute(select(func.count()).select_from(filtered)).scalar_one()
    active_count = db.execute(select(func.count()).select_from(filtered).where(filtered.c.is_active == 1)).scalar_one()
    inactive_count = db.execute(select(func.count()).select_from(filtered).where(filtered.c.is_active == 0)).scalar_one()

    pagination = None
    if kind == 'countries':
        per_page = 10
        num_pages = max(1, math.ceil(total / per_page))
        try:
            number = int(page) if page is not None else 1
            if number < 1:
                raise ValueError
        except (TypeError, ValueError):
            number = 1 if page is None or not str(page).lstrip('-').isdigit() else num_pages
        if number > num_pages:
            number = num_pages
        rows = db.execute(stmt.limit(per_page).offset((number - 1) * per_page)).scalars().all()
        pagination = {
            'page': number,
            'num_pages': num_pages,
            'start_index': 0 if total == 0 else (number - 1) * per_page + 1,
            'end_index': (number - 1) * per_page + len(rows),
            'has_pagination': num_pages > 1,
        }
    else:
        rows = db.execute(stmt).scalars().all()

    return {
        'page_title': PAGE_TITLES[kind],
        'category_name': category_name,
        'singular': singular,
        'has_code': has_code,
        'search_query': search_query,
        'total_items': total,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'items': [_item(r, has_code) for r in rows],
        'pagination': pagination,
    }


@router.post('/categories/{kind}')
def category_add(kind: str, name: str = Form(''), code_name: str = Form(''),
                 user: User = Depends(require_category_admin), db: Session = Depends(get_db)):
    model, has_code, _cn, _singular, label, required_msg = _category(kind)
    name = name.strip()
    code_name = code_name.strip()
    if not name or (has_code and not code_name):
        raise HTTPException(400, required_msg)
    try:
        obj = model(name=name, is_active=1, **({'code_name': code_name} if has_code else {}))
        db.add(obj)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f'Error adding {label.lower()}: {_db_error(e)}')
    return {'message': f'{label} "{name}" added successfully', 'item': _item(obj, has_code)}


@router.get('/categories/{kind}/{item_id}')
def category_get(kind: str, item_id: int, user: User = Depends(require_category_admin), db: Session = Depends(get_db)):
    model, has_code, category_name, singular, _l, _r = _category(kind)
    obj = db.get(model, item_id)
    if obj is None:
        raise HTTPException(404, 'Not found')
    return {'category_name': category_name, 'singular': singular, 'has_code': has_code, 'item': _item(obj, has_code)}


@router.post('/categories/{kind}/{item_id}')
def category_edit(kind: str, item_id: int, name: str = Form(''), code_name: str = Form(''),
                  user: User = Depends(require_category_admin), db: Session = Depends(get_db)):
    model, has_code, _cn, _s, label, required_msg = _category(kind)
    obj = db.get(model, item_id)
    if obj is None:
        raise HTTPException(404, 'Not found')
    name = name.strip()
    code_name = code_name.strip()
    if not name or (has_code and not code_name):
        raise HTTPException(400, required_msg)
    try:
        obj.name = name
        if has_code:
            obj.code_name = code_name
        obj.updated_at = utcnow()  # save() always bumps auto_now
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f'Error updating {label.lower()}: {_db_error(e)}')
    return {'message': f'{label} updated successfully', 'item': _item(obj, has_code)}


@router.post('/categories/{kind}/{item_id}/toggle')
def category_toggle(kind: str, item_id: int, user: User = Depends(require_category_admin), db: Session = Depends(get_db)):
    model, has_code, _cn, _s, label, _r = _category(kind)
    obj = db.get(model, item_id)
    if obj is None:
        raise HTTPException(404, 'Not found')
    obj.is_active = 0 if obj.is_active else 1
    db.commit()
    status = 'activated' if obj.is_active else 'deactivated'
    return {'message': f'{label} "{obj.name}" {status} successfully', 'item': _item(obj, has_code)}


# ---------------------------------------------------------------- legacy country upload
COUNTRY_SAMPLE_DATA = [
    {'name': 'United States', 'code_name': 'US'},
    {'name': 'United Kingdom', 'code_name': 'UK'},
    {'name': 'Canada', 'code_name': 'CA'},
    {'name': 'Australia', 'code_name': 'AU'},
    {'name': 'United States - East Coast', 'code_name': 'US'},
    {'name': 'United States - West Coast', 'code_name': 'US'},
]


@router.get('/country-upload')
def country_upload_info(user: User = Depends(require_category_admin)):
    return {'page_title': 'Upload Countries', 'sample_data': COUNTRY_SAMPLE_DATA}


@router.post('/country-upload')
async def country_upload(file: UploadFile | None = File(None), update_existing: str | None = Form(None),
                         user: User = Depends(require_category_admin), db: Session = Depends(get_db)):
    uploaded = bulk.UploadedFile(file.filename or '', await file.read()) if file is not None else None
    err = bulk.validate_country_upload_form(uploaded)
    if err:
        raise HTTPException(400, err)
    flag = (update_existing or '').lower() in ('on', 'true', '1', 'yes')
    try:
        messages = bulk.country_upload(db, uploaded, flag)
    except bulk.CountryUploadError as e:
        raise HTTPException(400, str(e))
    return {'messages': messages}


# ---------------------------------------------------------------- bulk import (login only, like Django)
@router.get('/bulk-import/{kind}')
def bulk_import_info(kind: str, user: User = Depends(get_current_user)):
    if kind not in bulk.IMPORT_TYPES:
        raise HTTPException(404, 'Not found')
    return {'import_type': bulk.IMPORT_TYPES[kind], 'template_url': f'/api/tools/bulk-import/{kind}/template'}


@router.post('/bulk-import/{kind}')
async def bulk_import(kind: str, file: UploadFile | None = File(None),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if kind not in bulk.IMPORT_TYPES:
        raise HTTPException(404, 'Not found')
    uploaded = bulk.UploadedFile(file.filename or '', await file.read()) if file is not None else None
    err = bulk.validate_bulk_form(uploaded)
    if err:
        raise HTTPException(400, err)
    success_count, error_count, errors = bulk.process_file(db, kind, uploaded)
    return {
        'import_type': bulk.IMPORT_TYPES[kind],
        'success_count': success_count,
        'error_count': error_count,
        'errors': errors,
        'messages': bulk.bulk_import_messages(kind, success_count, error_count),
    }


@router.get('/bulk-import/{kind}/template')
def bulk_import_template(kind: str):
    # Django's download_template_* views had no login_required
    if kind not in bulk.IMPORT_TYPES:
        raise HTTPException(404, 'Not found')
    body, content_type, filename = bulk.template_csv(kind)
    return Response(body, media_type=content_type,
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})
