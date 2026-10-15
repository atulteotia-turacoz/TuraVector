"""Research projects — port of the project views/forms/model helpers in documents/.

Sources: documents/models.py (ResearchProject & friends), documents/forms.py
(ResearchProjectForm, ProjectAuthorFormSet, ProjectMilestoneFormSet,
create_default_milestones_for_project, ProjectCollaboratorForm, ProjectTaskForm,
CollaboratorSearchForm) and documents/views.py (projects_* views).
"""
import datetime
import os
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.files import get_valid_filename, media_url, save_upload
from app.core.utils import iso
from app.models import (
    ProjectAuthor,
    ProjectMilestone,
    ResearchProject,
    ResearchProjectCollaborator,
    ResearchProjectDocument,
    ResearchProjectTask,
    User,
)
from app.services.projects_forms import (
    FormErrors,
    clean_bool,
    clean_char,
    clean_choice,
    clean_date,
    clean_decimal,
    clean_email,
    clean_positive_int,
)

# ------------------------------------------------------------------ choices (models.py)
PROJECT_TYPE_CHOICES = [
    ("manuscript", "Manuscript"), ("abstract", "Abstract"), ("poster", "Poster"),
    ("review_article", "Review Article"), ("report", "Report"), ("patient_lay_summary", "Patient Lay Summary"),
    ("protocol", "Protocol"), ("clinical_study_report", "Clinical Study Report"), ("white_paper", "White Paper"),
    ("investigators_brochure", "Investigators Brochure"), ("other", "Other"),
]
CLIENT_TYPE_CHOICES = [("internal", "Internal"), ("other", "Other")]
THERAPEUTIC_AREA_CHOICES = [
    ("anesthesia", "Anesthesia"), ("cardiology", "Cardiology"), ("oncology", "Oncology"), ("radiology", "Radiology"),
    ("dentistry", "Dentistry"), ("ophthalmology", "Ophthalmology"), ("dermatology", "Dermatology"),
    ("virology", "Virology"), ("respiratory", "Respiratory"), ("rare_disease", "Rare Disease"),
    ("gynecology", "Gynecology"), ("hepatology", "Hepatology"), ("gastroenterology", "Gastroenterology"),
    ("others", "Others"),
]
STATUS_CHOICES = [("planning", "Planning"), ("active", "Active"), ("on_hold", "On Hold"),
                  ("completed", "Completed"), ("cancelled", "Cancelled")]
PRIORITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")]
ROLE_CHOICES = [("owner", "Owner"), ("co_investigator", "Co-Investigator"), ("researcher", "Researcher"),
                ("analyst", "Analyst"), ("contributor", "Contributor"), ("reviewer", "Reviewer")]
TASK_STATUS_CHOICES = [("todo", "To Do"), ("in_progress", "In Progress"), ("completed", "Completed"),
                       ("cancelled", "Cancelled")]
TASK_PRIORITY_CHOICES = PRIORITY_CHOICES
AUTHOR_TYPE_CHOICES = [("corresponding", "Corresponding Author"), ("other", "Other Author")]
MILESTONE_STATUS_CHOICES = [("not_started", "Not Started"), ("in_progress", "In Progress"),
                            ("completed", "Completed"), ("delayed", "Delayed")]
SORT_OPTIONS = ["-created_at", "created_at", "title", "-title", "deadline", "-deadline"]

DEFAULT_MILESTONES = [
    ("Kick off call", 1), ("Draft 1", 2), ("Draft 1 comments", 3), ("Draft 2", 4), ("Draft 2 comments", 5),
    ("Draft 3", 6), ("Draft 3 comments", 7), ("Final draft", 8), ("Final approved draft", 9),
    ("Final submitted draft", 10),
]


def display(choices: list[tuple[str, str]], value: str | None) -> str:
    """Model.get_FOO_display()"""
    return dict(choices).get(value, value or "")


def choices_payload() -> dict[str, list[dict[str, str]]]:
    as_list = lambda ch: [{"value": v, "label": label} for v, label in ch]  # noqa: E731
    return {
        "project_types": as_list(PROJECT_TYPE_CHOICES),
        "client_types": as_list(CLIENT_TYPE_CHOICES),
        "therapeutic_areas": as_list(THERAPEUTIC_AREA_CHOICES),
        "statuses": as_list(STATUS_CHOICES),
        "priorities": as_list(PRIORITY_CHOICES),
        "roles": as_list(ROLE_CHOICES),
        "task_statuses": as_list(TASK_STATUS_CHOICES),
        "task_priorities": as_list(TASK_PRIORITY_CHOICES),
        "author_types": as_list(AUTHOR_TYPE_CHOICES),
        "milestone_statuses": as_list(MILESTONE_STATUS_CHOICES),
    }


# ------------------------------------------------------------------ user helpers
def get_full_name(user: User | None) -> str:
    """AbstractUser.get_full_name — no username fallback."""
    if user is None:
        return ""
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


def initials(user: User | None) -> str:
    """{{ user.first_name.0 }}{{ user.last_name.0 }}"""
    if user is None:
        return ""
    return f"{(user.first_name or '')[:1]}{(user.last_name or '')[:1]}"


def user_option(user: User) -> dict[str, Any]:
    """UserModelChoiceField.label_from_instance: 'Full Name - email'."""
    return {"value": user.id, "label": f"{get_full_name(user)} - {user.email}"}


def user_payload(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {"id": user.id, "username": user.username, "email": user.email, "first_name": user.first_name,
            "last_name": user.last_name, "full_name": get_full_name(user), "initials": initials(user)}


def truncatewords(text: str | None, n: int) -> str:
    """Django |truncatewords:n"""
    words = (text or "").split()
    if len(words) <= n:
        return " ".join(words) if text else ""
    return " ".join(words[:n]) + " …"


def iso_date(d: datetime.date | None) -> str | None:
    return d.isoformat() if d else None


# ------------------------------------------------------------------ access helpers
def get_project_or_404(db: Session, project_id: int) -> ResearchProject:
    project = db.get(ResearchProject, project_id)
    if project is None:
        raise HTTPException(404, "No ResearchProject matches the given query.")
    return project


def is_collaborator(db: Session, project: ResearchProject, user: User) -> bool:
    """ResearchProject.is_collaborator / project.collaborators.filter(id=user.id).exists()"""
    return db.execute(
        select(ResearchProjectCollaborator.id).where(
            ResearchProjectCollaborator.project_id == project.id, ResearchProjectCollaborator.user_id == user.id
        ).limit(1)
    ).first() is not None


def is_owner(project: ResearchProject, user: User) -> bool:
    return project.owner_id == user.id


def has_access(db: Session, project: ResearchProject, user: User) -> bool:
    return is_owner(project, user) or is_collaborator(db, project, user)


def require_access(db: Session, project: ResearchProject, user: User, message: str) -> None:
    if not has_access(db, project, user):
        raise HTTPException(403, message)


def require_owner(project: ResearchProject, user: User, message: str) -> None:
    if not is_owner(project, user):
        raise HTTPException(403, message)


# ------------------------------------------------------------------ computed properties
def collaborator_count(db: Session, project_id: int) -> int:
    return db.execute(select(func.count()).select_from(ResearchProjectCollaborator)
                      .where(ResearchProjectCollaborator.project_id == project_id)).scalar_one()


def task_counts(db: Session, project_id: int) -> tuple[int, int]:
    total = db.execute(select(func.count()).select_from(ResearchProjectTask)
                       .where(ResearchProjectTask.project_id == project_id)).scalar_one()
    done = db.execute(select(func.count()).select_from(ResearchProjectTask)
                      .where(ResearchProjectTask.project_id == project_id,
                             ResearchProjectTask.status == "completed")).scalar_one()
    return total, done


def progress_percentage(db: Session, project_id: int) -> int:
    total, done = task_counts(db, project_id)
    if total == 0:
        return 0
    return int((done / total) * 100)


def days_remaining(project: ResearchProject) -> int | None:
    if project.deadline:
        today = datetime.date.today()
        if project.deadline > today:
            return (project.deadline - today).days
        if project.deadline == today:
            return 0
        return -1 * (today - project.deadline).days
    return None


def keywords_list(project: ResearchProject) -> list[str]:
    if not project.keywords:
        return []
    return [k.strip() for k in project.keywords.split(",") if k.strip()]


def project_fields(project: ResearchProject) -> dict[str, Any]:
    """Raw form values for ResearchProjectForm."""
    return {
        "project_type": project.project_type,
        "project_type_other": project.project_type_other,
        "client_type": project.client_type,
        "client_other": project.client_other,
        "title": project.title,
        "status": project.status,
        "client_poc_name": project.client_poc_name,
        "client_poc_email": project.client_poc_email,
        "has_authors": bool(project.has_authors),
        "journal_name": project.journal_name,
        "therapeutic_area": project.therapeutic_area,
        "therapeutic_area_other": project.therapeutic_area_other,
        "sub_therapy_area": project.sub_therapy_area,
        "start_date": iso_date(project.start_date),
        "estimated_end_date": iso_date(project.estimated_end_date),
        "actual_end_date": iso_date(project.actual_end_date),
        "description": project.description,
        "research_field": project.research_field,
        "keywords": project.keywords,
        "priority": project.priority,
        "budget": None if project.budget is None else str(project.budget),
    }


def project_summary(db: Session, project: ResearchProject, user: User) -> dict[str, Any]:
    data = project_fields(project)
    data.update({
        "id": project.id,
        "status_display": display(STATUS_CHOICES, project.status),
        "priority_display": display(PRIORITY_CHOICES, project.priority),
        "project_type_display": display(PROJECT_TYPE_CHOICES, project.project_type),
        "client_type_display": display(CLIENT_TYPE_CHOICES, project.client_type),
        "therapeutic_area_display": display(THERAPEUTIC_AREA_CHOICES, project.therapeutic_area),
        "description_short": truncatewords(project.description, 20),
        "owner": user_payload(project.owner),
        "is_owner": is_owner(project, user),
        "collaborator_count": collaborator_count(db, project.id),
        "deadline": iso_date(project.deadline),
        "end_date": iso_date(project.end_date),
        "days_remaining": days_remaining(project),
        "created_at": iso(project.created_at),
        "updated_at": iso(project.updated_at),
        "is_active": bool(project.is_active),
    })
    return data


def author_payload(a: ProjectAuthor) -> dict[str, Any]:
    return {"id": a.id, "name": a.name, "affiliation": a.affiliation, "email": a.email,
            "author_type": a.author_type, "author_type_display": display(AUTHOR_TYPE_CHOICES, a.author_type)}


def project_authors(db: Session, project_id: int) -> list[ProjectAuthor]:
    # Meta.ordering = ['author_type', 'name']
    return list(db.execute(select(ProjectAuthor).where(ProjectAuthor.project_id == project_id)
                           .order_by(ProjectAuthor.author_type, ProjectAuthor.name)).scalars())


def task_payload(t: ResearchProjectTask) -> dict[str, Any]:
    return {
        "id": t.id, "title": t.title, "description": t.description,
        "description_short": truncatewords(t.description, 15),
        "status": t.status, "status_display": display(TASK_STATUS_CHOICES, t.status),
        "priority": t.priority, "priority_display": display(TASK_PRIORITY_CHOICES, t.priority),
        "assigned_to": user_payload(t.assigned_to), "assigned_to_id": t.assigned_to_id,
        "due_date": iso_date(t.due_date), "created_at": iso(t.created_at), "updated_at": iso(t.updated_at),
        "completed_at": iso(t.completed_at),
    }


def collaborator_payload(c: ResearchProjectCollaborator) -> dict[str, Any]:
    return {
        "id": c.id, "role": c.role, "role_display": display(ROLE_CHOICES, c.role),
        "joined_at": iso(c.joined_at), "is_active": bool(c.is_active),
        "user": user_payload(c.user), "project_id": c.project_id,
    }


def document_payload(d: ResearchProjectDocument, project: ResearchProject, user: User) -> dict[str, Any]:
    return {
        "id": d.id, "title": d.title, "description": d.description,
        "description_short": truncatewords(d.description, 10),
        "file": d.file, "file_name": os.path.basename(d.file or ""), "file_url": media_url(d.file),
        "uploaded_by": user_payload(d.uploaded_by), "uploaded_at": iso(d.uploaded_at),
        "can_delete": is_owner(project, user) or d.uploaded_by_id == user.id,
    }


def milestone_payload(m: ProjectMilestone) -> dict[str, Any]:
    return {
        "id": m.id, "milestone_name": m.milestone_name, "description": m.description,
        "responsible_person_name": m.responsible_person_name,
        "responsible_person_contact": m.responsible_person_contact,
        "start_date": iso_date(m.start_date), "end_date": iso_date(m.end_date), "tat_days": m.tat_days,
        "status": m.status, "status_display": display(MILESTONE_STATUS_CHOICES, m.status), "order": m.order,
        "attachment": m.attachment or None,
        # {{ attachment.name|cut:"milestones/" }}
        "attachment_name": (m.attachment or "").replace("milestones/", "") or None,
        "attachment_url": media_url(m.attachment) if m.attachment else None,
    }


# ------------------------------------------------------------------ list (projects_list_view)
def list_projects(db: Session, user: User, search: str, status: str, priority: str, sort: str, page: Any,
                  per_page: int = 6) -> dict[str, Any]:
    collab_ids = select(ResearchProjectCollaborator.project_id).where(ResearchProjectCollaborator.user_id == user.id)
    stmt = select(ResearchProject).where(or_(ResearchProject.owner_id == user.id, ResearchProject.id.in_(collab_ids)))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(ResearchProject.title.ilike(like), ResearchProject.description.ilike(like),
                              ResearchProject.keywords.ilike(like), ResearchProject.research_field.ilike(like)))
    if status:
        stmt = stmt.where(ResearchProject.status == status)
    if priority:
        stmt = stmt.where(ResearchProject.priority == priority)
    sort_by = sort or "-created_at"
    key = sort_by if sort_by in SORT_OPTIONS else "-created_at"
    col = getattr(ResearchProject, key.lstrip("-"))
    stmt = stmt.order_by(col.desc() if key.startswith("-") else col.asc())

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    num_pages = max(1, -(-total // per_page))
    # Paginator.page(): non-integer -> 1, out of range -> last page
    try:
        page_no = int(page)
        if page_no < 1:
            page_no = num_pages
    except (TypeError, ValueError):
        page_no = 1
    if page_no > num_pages:
        page_no = num_pages
    rows = db.execute(stmt.limit(per_page).offset((page_no - 1) * per_page)).scalars().all()
    start_index = (page_no - 1) * per_page + 1 if total else 0
    end_index = start_index + len(rows) - 1 if total else 0
    return {
        "items": [project_summary(db, p, user) for p in rows],
        "total": total, "page": page_no, "pages": num_pages,
        "start_index": start_index, "end_index": end_index,
        "search_query": search, "status_filter": status, "priority_filter": priority, "sort_by": sort_by,
        "status_choices": [{"value": v, "label": label} for v, label in STATUS_CHOICES],
        "priority_choices": [{"value": v, "label": label} for v, label in PRIORITY_CHOICES],
        "page_title": "My Projects",
    }


# ------------------------------------------------------------------ detail (project_detail_view)
def project_detail(db: Session, project: ResearchProject, user: User) -> dict[str, Any]:
    tasks = db.execute(select(ResearchProjectTask).where(ResearchProjectTask.project_id == project.id)
                       .order_by(ResearchProjectTask.created_at.desc())).scalars().all()
    documents = db.execute(select(ResearchProjectDocument).where(ResearchProjectDocument.project_id == project.id)
                           .order_by(ResearchProjectDocument.uploaded_at.desc())).scalars().all()
    collaborators = db.execute(select(ResearchProjectCollaborator)
                               .where(ResearchProjectCollaborator.project_id == project.id)
                               .order_by(ResearchProjectCollaborator.id)).scalars().all()
    data = project_summary(db, project, user)
    data.update({
        "tasks": [task_payload(t) for t in tasks],
        "documents": [document_payload(d, project, user) for d in documents],
        "collaborators": [collaborator_payload(c) for c in collaborators],
        "authors": [author_payload(a) for a in project_authors(db, project.id)],
        "keywords_list": keywords_list(project),
        "progress_percentage": progress_percentage(db, project.id),
        "is_collaborator": is_collaborator(db, project, user),
        "page_title": f"Project: {project.title}",
    })
    return data


# ------------------------------------------------------------------ ResearchProjectForm
def clean_project_form(data: dict[str, Any]) -> tuple[dict[str, Any], FormErrors]:
    errs = FormErrors()
    c: dict[str, Any] = {}
    c["project_type"] = clean_choice(errs, "project_type", data.get("project_type"), PROJECT_TYPE_CHOICES)
    c["project_type_other"] = clean_char(errs, "project_type_other", data.get("project_type_other"), max_length=255, null=True)
    c["client_type"] = clean_choice(errs, "client_type", data.get("client_type"), CLIENT_TYPE_CHOICES)
    c["client_other"] = clean_char(errs, "client_other", data.get("client_other"), max_length=255, null=True)
    c["title"] = clean_char(errs, "title", data.get("title"), max_length=255, required=True)
    c["status"] = clean_choice(errs, "status", data.get("status"), STATUS_CHOICES)
    c["client_poc_name"] = clean_char(errs, "client_poc_name", data.get("client_poc_name"), max_length=255, null=True)
    c["client_poc_email"] = clean_email(errs, "client_poc_email", data.get("client_poc_email"), null=True)
    c["has_authors"] = clean_bool(data.get("has_authors"))
    c["journal_name"] = clean_char(errs, "journal_name", data.get("journal_name"), max_length=255, null=True)
    c["therapeutic_area"] = clean_choice(errs, "therapeutic_area", data.get("therapeutic_area"), THERAPEUTIC_AREA_CHOICES)
    c["therapeutic_area_other"] = clean_char(errs, "therapeutic_area_other", data.get("therapeutic_area_other"), max_length=255, null=True)
    c["sub_therapy_area"] = clean_char(errs, "sub_therapy_area", data.get("sub_therapy_area"), max_length=255, null=True)
    c["start_date"] = clean_date(errs, "start_date", data.get("start_date"))
    c["estimated_end_date"] = clean_date(errs, "estimated_end_date", data.get("estimated_end_date"))
    c["actual_end_date"] = clean_date(errs, "actual_end_date", data.get("actual_end_date"))
    # models.TextField(blank=True) -> forms.CharField(strip=True)
    c["description"] = clean_char(errs, "description", data.get("description"), max_length=10**9)
    c["research_field"] = clean_char(errs, "research_field", data.get("research_field"), max_length=255)
    c["keywords"] = clean_char(errs, "keywords", data.get("keywords"), max_length=10**9)
    c["priority"] = clean_choice(errs, "priority", data.get("priority"), PRIORITY_CHOICES)
    c["budget"] = clean_decimal(errs, "budget", data.get("budget"), max_digits=10, decimal_places=2)

    # ResearchProjectForm.clean() runs on cleaned_data (fields that failed validation are absent)
    ok = lambda f: None if f in errs.errors else c.get(f)  # noqa: E731
    if ok("project_type") == "other" and not ok("project_type_other"):
        errs.add(None, "Please specify the project type when 'Other' is selected.")
    elif ok("client_type") == "other" and not ok("client_other"):
        errs.add(None, "Please specify the client when 'Other' is selected.")
    elif ok("therapeutic_area") == "others" and not ok("therapeutic_area_other"):
        errs.add(None, "Please specify the therapeutic area when 'Others' is selected.")
    return c, errs


def apply_project_fields(project: ResearchProject, c: dict[str, Any]) -> None:
    for key, value in c.items():
        if key == "has_authors":
            project.has_authors = 1 if value else 0
        else:
            setattr(project, key, value)


# ------------------------------------------------------------------ ProjectAuthorFormSet
def process_author_formset(db: Session, project: ResearchProject, authors: list[dict[str, Any]],
                           existing_project: bool) -> bool:
    """Validate + save the author formset. Returns False (and saves nothing) when the formset is invalid,
    exactly like the Django view which silently skipped invalid author formsets."""
    existing = {a.id: a for a in db.execute(select(ProjectAuthor)
                                             .where(ProjectAuthor.project_id == project.id)).scalars()} \
        if existing_project else {}
    to_save: list[tuple[ProjectAuthor | None, dict[str, Any]]] = []
    to_delete: list[ProjectAuthor] = []
    seen_emails: set[str] = set()
    valid = True

    for row in authors or []:
        raw_id = row.get("id")
        instance = None
        if raw_id not in (None, "", 0):
            try:
                instance = existing.get(int(raw_id))
            except (TypeError, ValueError):
                instance = None
            if instance is None:
                valid = False  # "Select a valid choice" on the hidden id field
                continue
        deleted = clean_bool(row.get("DELETE"))
        if deleted:
            if instance is not None:
                to_delete.append(instance)
            continue
        name = (row.get("name") or "").strip()
        affiliation = (row.get("affiliation") or "").strip()
        email = (row.get("email") or "").strip()
        author_type = (row.get("author_type") or "other").strip()
        if instance is None and not name and not affiliation and not email and author_type == "other":
            continue  # untouched extra form
        if instance is not None and (name, affiliation, email, author_type) == (
                instance.name, instance.affiliation, instance.email, instance.author_type):
            seen_emails.add(email)
            continue  # unchanged existing form
        errs = FormErrors()
        name = clean_char(errs, "name", name, max_length=255, required=True)
        affiliation = clean_char(errs, "affiliation", affiliation, max_length=500, required=True)
        email = clean_email(errs, "email", email, required=True)
        author_type = clean_choice(errs, "author_type", author_type, AUTHOR_TYPE_CHOICES)
        if errs:
            valid = False
            continue
        if email in seen_emails:
            valid = False  # formset unique_together check
            continue
        seen_emails.add(email)
        if existing_project:
            clash = db.execute(select(ProjectAuthor.id).where(
                ProjectAuthor.project_id == project.id, ProjectAuthor.email == email,
                ProjectAuthor.id != (instance.id if instance else -1)).limit(1)).first()
            if clash:
                valid = False
                continue
        to_save.append((instance, {"name": name, "affiliation": affiliation, "email": email,
                                   "author_type": author_type}))

    if not valid:
        return False
    for instance, values in to_save:
        if instance is None:
            instance = ProjectAuthor(project_id=project.id)
            db.add(instance)
        for k, v in values.items():
            setattr(instance, k, v)
    db.flush()
    for a in to_delete:
        db.delete(a)
    return True


# ------------------------------------------------------------------ default milestones
def create_default_milestones_for_project(db: Session, project: ResearchProject, user: User) -> None:
    for name, order in DEFAULT_MILESTONES:
        db.add(ProjectMilestone(project_id=project.id, milestone_name=name, order=order, created_by_id=user.id,
                                status="not_started"))
    db.commit()


def project_milestones(db: Session, project_id: int) -> list[ProjectMilestone]:
    return list(db.execute(select(ProjectMilestone).where(ProjectMilestone.project_id == project_id)
                           .order_by(ProjectMilestone.order)).scalars())


def _field_text(value: Any) -> str:
    return "" if value is None else str(value)


def process_milestone_formset(db: Session, project: ResearchProject, user: User, rows: list[dict[str, Any]],
                              files: dict[str, UploadFile]) -> list[str]:
    """ProjectMilestoneFormSet validation + save. Returns error strings (empty on success)."""
    existing = {m.id: m for m in project_milestones(db, project.id)}
    error_messages: list[str] = []
    non_form_errors: list[str] = []
    pending: list[tuple[ProjectMilestone | None, dict[str, Any], UploadFile | None]] = []
    deletions: list[ProjectMilestone] = []
    seen_orders: set[int] = set()

    for i, row in enumerate(rows):
        raw_id = row.get("id")
        instance = None
        errs = FormErrors()
        if raw_id not in (None, "", 0):
            try:
                instance = existing.get(int(raw_id))
            except (TypeError, ValueError):
                instance = None
            if instance is None:
                errs.add("id", "Select a valid choice. That choice is not one of the available choices.")
        if clean_bool(row.get("DELETE")):
            if instance is not None:
                deletions.append(instance)
            continue
        upload = files.get(str(row.get("file_key") or f"attachment-{i}"))
        name = clean_char(errs, "milestone_name", row.get("milestone_name"), max_length=255, required=True)
        description = clean_char(errs, "description", row.get("description"), max_length=10**9, null=True)
        rp_name = clean_char(errs, "responsible_person_name", row.get("responsible_person_name"), max_length=255, null=True)
        rp_contact = clean_char(errs, "responsible_person_contact", row.get("responsible_person_contact"), max_length=255, null=True)
        start = clean_date(errs, "start_date", row.get("start_date"))
        end = clean_date(errs, "end_date", row.get("end_date"))
        status = clean_choice(errs, "status", row.get("status"), MILESTONE_STATUS_CHOICES)
        order = clean_positive_int(errs, "order", row.get("order"))
        if upload is not None and upload.filename:
            fname = os.path.basename(upload.filename)
            if len(fname) > 100:
                errs.add("attachment", f"Ensure this filename has at most 100 characters (it has {len(fname)}).")
        else:
            upload = None
        if start and end and start > end:
            errs.add(None, "End date must be after start date.")
        # model validate_unique: (project, order) against stored rows other than this one
        if order is not None and "order" not in errs.errors:
            clash = db.execute(select(ProjectMilestone.id).where(
                ProjectMilestone.project_id == project.id, ProjectMilestone.order == order,
                ProjectMilestone.id != (instance.id if instance else -1)).limit(1)).first()
            if clash:
                errs.add(None, "Project milestone with this Project and Order already exists.")
        if errs:
            parts = [f"{k}: {' '.join(v)}" for k, v in errs.errors.items()]
            parts += errs.non_field
            error_messages.append(f"Form {i}: {'; '.join(parts)}")
            continue
        values = {"milestone_name": name, "description": description, "responsible_person_name": rp_name,
                  "responsible_person_contact": rp_contact, "start_date": start, "end_date": end,
                  "status": status, "order": order}
        if order in seen_orders:
            non_form_errors.append("Please correct the duplicate data for project and order, which must be unique.")
        seen_orders.add(order)
        if instance is not None:
            changed = upload is not None or any(
                _field_text(getattr(instance, k)) != _field_text(v) for k, v in values.items())
            if not changed:
                continue
        pending.append((instance, values, upload))

    if error_messages or non_form_errors:
        msgs = list(error_messages)
        if non_form_errors:
            msgs.append(f"General errors: {' '.join(dict.fromkeys(non_form_errors))}")
        return msgs

    for instance, values, upload in pending:
        if instance is None:
            instance = ProjectMilestone(project_id=project.id)
            db.add(instance)
        for k, v in values.items():
            setattr(instance, k, v)
        instance.created_by_id = user.id
        if upload is not None:
            instance.attachment = save_limited(upload, "milestones")
        # ProjectMilestone.save(): TAT only recalculated when both dates are present
        if instance.start_date and instance.end_date:
            instance.tat_days = (instance.end_date - instance.start_date).days
        db.flush()
    for m in deletions:
        db.delete(m)
    db.commit()
    return []


def save_limited(upload: UploadFile, directory: str, max_length: int = 100) -> str:
    """FileField(max_length=100): Django's storage truncates the file root to fit the column."""
    name = get_valid_filename(os.path.basename(upload.filename or "file"))
    full_len = len(directory.strip("/")) + 1 + len(name)
    if full_len > max_length:
        stem, ext = os.path.splitext(name)
        cut = full_len - max_length + 8  # room for Django's _xxxxxxx suffix
        stem = stem[: max(1, len(stem) - cut)]
        name = stem + ext
    return save_upload(upload, directory, filename=name)


# ------------------------------------------------------------------ project delete (CASCADE)
def delete_project(db: Session, project: ResearchProject) -> None:
    for model in (ProjectAuthor, ProjectMilestone, ResearchProjectCollaborator, ResearchProjectDocument,
                  ResearchProjectTask):
        db.execute(delete(model).where(model.project_id == project.id))
    db.delete(project)
    db.commit()


# ------------------------------------------------------------------ ProjectCollaboratorForm
def available_collaborator_users(db: Session, project: ResearchProject) -> list[User]:
    existing_ids = select(ResearchProjectCollaborator.user_id).where(
        ResearchProjectCollaborator.project_id == project.id)
    return list(db.execute(select(User).where(User.is_active == 1, User.id != project.owner_id,
                                              User.id.not_in(existing_ids))
                           .order_by(User.first_name, User.last_name)).scalars())


def clean_collaborator_form(db: Session, project: ResearchProject, data: dict[str, Any],
                            instance: ResearchProjectCollaborator | None) -> tuple[User | None, str | None, FormErrors]:
    errs = FormErrors()
    user: User | None = None
    if instance is not None:
        user = instance.user  # user cannot be changed when editing
    else:
        raw = data.get("user")
        if raw in (None, ""):
            errs.add("user", REQUIRED_USER)
        else:
            allowed = {u.id: u for u in available_collaborator_users(db, project)}
            try:
                user = allowed.get(int(raw))
            except (TypeError, ValueError):
                user = None
            if user is None:
                errs.add("user", "Select a valid choice. That choice is not one of the available choices.")
        if user is not None:
            # ProjectCollaboratorForm.clean_user
            if not user.is_active:
                errs.add("user", "This user account is inactive and cannot be added as a collaborator.")
            elif db.execute(select(ResearchProjectCollaborator.id).where(
                    ResearchProjectCollaborator.project_id == project.id,
                    ResearchProjectCollaborator.user_id == user.id)).first():
                errs.add("user", "This user is already a collaborator on this project.")
            elif project.owner_id == user.id:
                errs.add("user", "The project owner cannot be added as a collaborator.")
    role = clean_choice(errs, "role", data.get("role"), ROLE_CHOICES)
    return user, role, errs


REQUIRED_USER = "This field is required."


# ------------------------------------------------------------------ ProjectTaskForm
def assignable_users(db: Session, project: ResearchProject) -> list[User]:
    collab_ids = select(ResearchProjectCollaborator.user_id).where(
        ResearchProjectCollaborator.project_id == project.id)
    return list(db.execute(select(User).where(or_(User.id == project.owner_id, User.id.in_(collab_ids)),
                                              User.is_active == 1)
                           .order_by(User.first_name, User.last_name)).scalars())


def clean_task_form(db: Session, project: ResearchProject, data: dict[str, Any]) -> tuple[dict[str, Any], FormErrors]:
    errs = FormErrors()
    c: dict[str, Any] = {}
    c["title"] = clean_char(errs, "title", data.get("title"), max_length=255, required=True)
    c["description"] = clean_char(errs, "description", data.get("description"), max_length=10**9)
    c["status"] = clean_choice(errs, "status", data.get("status"), TASK_STATUS_CHOICES)
    c["priority"] = clean_choice(errs, "priority", data.get("priority"), TASK_PRIORITY_CHOICES)
    raw = data.get("assigned_to")
    c["assigned_to_id"] = None
    if raw not in (None, ""):
        allowed = {u.id for u in assignable_users(db, project)}
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            uid = None
        if uid is None or uid not in allowed:
            errs.add("assigned_to", "Select a valid choice. That choice is not one of the available choices.")
        else:
            c["assigned_to_id"] = uid
    c["due_date"] = clean_date(errs, "due_date", data.get("due_date"))
    return c, errs


# ------------------------------------------------------------------ CollaboratorSearchForm projects
def user_project_options(db: Session, user: User) -> list[ResearchProject]:
    collab_ids = select(ResearchProjectCollaborator.project_id).where(ResearchProjectCollaborator.user_id == user.id)
    return list(db.execute(select(ResearchProject).where(
        or_(ResearchProject.owner_id == user.id, ResearchProject.id.in_(collab_ids))
    ).order_by(ResearchProject.title)).scalars())
