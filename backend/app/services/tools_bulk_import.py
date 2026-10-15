"""Bulk import of categories — port of documents/bulk_import_views.py, the BulkImportForm /
CountryUploadForm validation, and documents.views.country_upload_view.

Row processing is identical to Django (pandas for bulk import, csv/openpyxl for the
legacy country upload) including the error texts. Django wrapped the bulk loop in
`transaction.atomic()`: once a database error was swallowed inside the block every
later query failed and the whole batch was rolled back at the end — reproduced by
`_AtomicBatch`.
"""
import csv
import io
import os
from dataclasses import dataclass, field

import chardet
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Brand, Country, DocumentType, TherapeuticArea, utcnow

MAX_BULK_SIZE = 5 * 1024 * 1024


@dataclass
class UploadedFile:
    name: str
    content: bytes

    @property
    def size(self) -> int:
        return len(self.content)


# ---------------------------------------------------------------- form validation
def _extension_error(name: str, allowed: list[str]) -> str | None:
    """django.core.validators.FileExtensionValidator"""
    extension = os.path.splitext(name)[1][1:].lower()
    if extension not in allowed:
        return (f"File extension “{extension}” is not allowed. "
                f"Allowed extensions are: {', '.join(allowed)}.")
    return None


def validate_bulk_form(file: UploadedFile | None) -> str | None:
    """BulkImportForm.is_valid() → first error message, or None."""
    if file is None or not file.name:
        return "This field is required."
    if file.size == 0:
        return "The submitted file is empty."
    err = _extension_error(file.name, ['csv', 'xlsx', 'xls'])
    if err:
        return err
    if file.size > MAX_BULK_SIZE:
        return 'File size must not exceed 5MB'
    return None


def validate_country_upload_form(file: UploadedFile | None) -> str | None:
    """CountryUploadForm.is_valid()"""
    if file is None or not file.name:
        return "This field is required."
    if file.size == 0:
        return "The submitted file is empty."
    return _extension_error(file.name, ['csv', 'xls', 'xlsx'])


# ---------------------------------------------------------------- bulk import
IMPORT_TYPES = {
    'document-types': 'Document Types',
    'brands': 'Brands',
    'therapeutic-areas': 'Therapeutic Areas',
    'countries': 'Countries',
}
# noun used in the success/error messages
IMPORT_NOUNS = {
    'document-types': 'document types',
    'brands': 'brands',
    'therapeutic-areas': 'therapeutic areas',
    'countries': 'countries',
}


class _BrokenTransaction(Exception):
    pass


@dataclass
class _AtomicBatch:
    db: Session
    broken: bool = False
    created: list = field(default_factory=list)

    def run(self, fn):
        if self.broken:
            raise _BrokenTransaction(
                "An error occurred in the current transaction. You can't execute queries until the end of the 'atomic' block."
            )
        try:
            with self.db.begin_nested():
                return fn()
        except Exception:
            self.broken = True
            raise


def _read_dataframe(file: UploadedFile):
    if file.name.endswith('.csv'):
        file_content = file.content
        detected = chardet.detect(file_content)
        encoding = detected.get('encoding', 'latin-1')
        encodings_to_try = [encoding, 'latin-1', 'cp1252', 'iso-8859-1', 'utf-8-sig', 'utf-16']
        df = None
        for enc in encodings_to_try:
            try:
                df = pd.read_csv(io.BytesIO(file_content), encoding=enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if df is None:
            df = pd.read_csv(io.BytesIO(file_content), encoding='latin-1', errors='replace')
        return df
    return pd.read_excel(io.BytesIO(file.content))


def _exists(db: Session, model, column, value) -> bool:
    return db.execute(select(model.id).where(column == value).limit(1)).first() is not None


def _row_document_type(db, row):
    name = str(row.get('name', '')).strip()
    is_active = str(row.get('is_active', 'True')).lower() == 'true'
    if not name:
        return "Name is required"
    if _exists(db, DocumentType, DocumentType.name, name):
        return f"Document type '{name}' already exists"
    db.add(DocumentType(name=name, is_active=int(is_active)))
    db.flush()
    return None


def _row_brand(db, row):
    name = str(row.get('name', '')).strip()
    code_name = str(row.get('code_name', '')).strip()
    is_active = str(row.get('is_active', 'True')).lower() == 'true'
    if not name or not code_name:
        return "Name and code_name are required"
    if _exists(db, Brand, Brand.code_name, code_name):
        return f"Brand code '{code_name}' already exists"
    db.add(Brand(name=name, code_name=code_name.upper()[:50], is_active=int(is_active)))
    db.flush()
    return None


def _row_therapeutic_area(db, row):
    name = str(row.get('name', '')).strip()
    is_active = str(row.get('is_active', 'True')).lower() == 'true'
    if not name:
        return "Name is required"
    if _exists(db, TherapeuticArea, TherapeuticArea.name, name):
        return f"Therapeutic area '{name}' already exists"
    db.add(TherapeuticArea(name=name, is_active=int(is_active)))
    db.flush()
    return None


def _row_country(db, row):
    name = str(row.get('name', '')).strip()
    code_name = str(row.get('code_name', '')).strip()
    is_active = str(row.get('is_active', 'True')).lower() == 'true'
    if not name or not code_name:
        return "Name and code_name are required"
    if _exists(db, Country, Country.name, name):
        return f"Country '{name}' already exists"
    db.add(Country(name=name, code_name=code_name.upper()[:10], is_active=int(is_active)))
    db.flush()
    return None


_ROW_HANDLERS = {
    'document-types': _row_document_type,
    'brands': _row_brand,
    'therapeutic-areas': _row_therapeutic_area,
    'countries': _row_country,
}


def process_file(db: Session, kind: str, file: UploadedFile) -> tuple[int, int, list[str]]:
    """process_<kind>_file(file) → (success_count, error_count, errors)."""
    handler = _ROW_HANDLERS[kind]
    success_count = 0
    error_count = 0
    errors: list[str] = []
    df = None
    outer = None
    try:
        df = _read_dataframe(file)
        outer = db.begin_nested()  # transaction.atomic()
        batch = _AtomicBatch(db)
        for index, row in df.iterrows():
            try:
                err = batch.run(lambda: handler(db, row))
                if err:
                    errors.append(f"Row {index + 2}: {err}")
                    error_count += 1
                    continue
                success_count += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"Row {index + 2}: {str(e)}")
                error_count += 1
        if batch.broken:
            outer.rollback()
        else:
            outer.commit()
        db.commit()
    except Exception as e:  # noqa: BLE001
        if outer is not None and outer.is_active:
            outer.rollback()
        errors.append(f"File processing error: {str(e)}")
        error_count = len(df) if df is not None else 0
    return success_count, error_count, errors


def bulk_import_messages(kind: str, success_count: int, error_count: int) -> list[dict]:
    noun = IMPORT_NOUNS[kind]
    out = []
    if success_count > 0:
        out.append({'level': 'success', 'text': f'Successfully imported {success_count} {noun}.'})
    if error_count > 0:
        out.append({'level': 'error', 'text': f'Failed to import {error_count} {noun}. Check the error log.'})
    return out


# ---------------------------------------------------------------- template downloads
def template_csv(kind: str) -> tuple[bytes, str, str]:
    """download_template_<kind>: (body, content_type, filename) — same rows as Django."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    if kind == 'document-types':
        writer.writerow(['name', 'is_active'])
        writer.writerow(['Protocol', 'True'])
        writer.writerow(['Clinical Study Report', 'True'])
        writer.writerow(['Statistical Analysis Plan', 'True'])
        return buf.getvalue().encode('utf-8'), 'text/csv', 'document_types_template.csv'
    if kind == 'brands':
        writer.writerow(['name', 'code_name', 'is_active'])
        writer.writerow(['Pfizer', 'PFZ', 'True'])
        writer.writerow(['Johnson & Johnson', 'JNJ', 'True'])
        writer.writerow(['Roche', 'ROCHE', 'True'])
        return buf.getvalue().encode('utf-8'), 'text/csv', 'brands_template.csv'
    if kind == 'therapeutic-areas':
        writer.writerow(['name', 'is_active'])
        writer.writerow(['Oncology', 'True'])
        writer.writerow(['Cardiology', 'True'])
        writer.writerow(['Neurology', 'True'])
        writer.writerow(['Dermatology', 'True'])
        # BOM for Excel compatibility
        return buf.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8-sig', 'therapeutic_areas_template.csv'
    writer.writerow(['name', 'code_name', 'is_active'])
    writer.writerow(['United States', 'US', 'True'])
    writer.writerow(['United Kingdom', 'UK', 'True'])
    writer.writerow(['India', 'IN', 'True'])
    writer.writerow(['Canada', 'CA', 'True'])
    return buf.getvalue().encode('utf-8'), 'text/csv', 'countries_template.csv'


# ---------------------------------------------------------------- legacy country upload
class CountryUploadError(Exception):
    """Errors that make Django redirect back to the upload page with messages.error."""


def country_upload(db: Session, file: UploadedFile, update_existing: bool) -> list[dict]:
    """country_upload_view POST → list of messages (Django then redirected to the countries list)."""
    try:
        file_content = file.content
        data_rows = []
        if file.name.endswith('.csv'):
            csv_data = file_content.decode('utf-8')
            reader = csv.DictReader(io.StringIO(csv_data))
            data_rows = list(reader)
            headers = reader.fieldnames or []
        else:
            import openpyxl
            workbook = openpyxl.load_workbook(io.BytesIO(file_content))
            worksheet = workbook.active
            headers = [cell.value for cell in worksheet[1]]
            for row in worksheet.iter_rows(min_row=2, values_only=True):
                if any(row):
                    row_dict = {}
                    for i, value in enumerate(row):
                        if i < len(headers) and headers[i]:
                            row_dict[headers[i]] = value
                    data_rows.append(row_dict)

        required_columns = ['name', 'code_name']
        missing_columns = [col for col in required_columns if col not in headers]
        if missing_columns:
            raise CountryUploadError(f'Missing required columns: {", ".join(missing_columns)}')

        created_count = 0
        updated_count = 0
        error_count = 0
        errors = []
        for index, row in enumerate(data_rows):
            try:
                name = str(row.get('name', '')).strip()
                code_name = str(row.get('code_name', '')).strip()
                if not name or not code_name or name == 'None' or code_name == 'None':
                    errors.append(f'Row {index + 2}: Name and code are required')
                    error_count += 1
                    continue
                with db.begin_nested():
                    existing_country = db.execute(select(Country).where(Country.name == name).limit(1)).scalar_one_or_none()
                    if existing_country:
                        if update_existing:
                            existing_country.code_name = code_name
                            existing_country.updated_at = utcnow()
                            db.flush()
                            updated_count += 1
                        else:
                            errors.append(f'Row {index + 2}: Country with name "{name}" already exists')
                            error_count += 1
                    else:
                        db.add(Country(name=name, code_name=code_name, is_active=1))
                        db.flush()
                        created_count += 1
                db.commit()
            except Exception as e:  # noqa: BLE001
                errors.append(f'Row {index + 2}: {str(e)}')
                error_count += 1

        messages = []
        summary_parts = []
        if created_count > 0:
            summary_parts.append(f'{created_count} countries created')
        if updated_count > 0:
            summary_parts.append(f'{updated_count} countries updated')
        if error_count > 0:
            summary_parts.append(f'{error_count} errors')
        if summary_parts:
            messages.append({'level': 'success', 'text': f'Import completed: {", ".join(summary_parts)}'})
        for error in errors[:5]:
            messages.append({'level': 'warning', 'text': error})
        if len(errors) > 5:
            messages.append({'level': 'warning', 'text': f'... and {len(errors) - 5} more errors'})
        return messages
    except CountryUploadError:
        raise
    except Exception as e:  # noqa: BLE001
        raise CountryUploadError(f'Error processing file: {str(e)}') from e
