"""Research projects (Other Documents dashboard) — port of the projects_* / *_collaborator_* /
*_task_* views in documents/views.py.

Django redirected with `messages.error(...)` on permission failures; here those become
403 responses carrying the very same message (the UI toasts it and navigates to the
page Django redirected to).
"""
import json
import mimetypes
import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.core.files import delete_file, media_path
from app.core.utils import iso
from app.database import get_db
from app.models import (
    ProjectMilestone,
    ResearchProject,
    ResearchProjectCollaborator,
    ResearchProjectDocument,
    ResearchProjectTask,
    User,
)
from app.schemas.projects_schemas import CollaboratorIn, LegacyCollaboratorIn, ProjectIn, TaskIn
from app.services import projects_service as svc

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _file_response(rel: str | None) -> FileResponse:
    path = media_path(rel) if rel else None
    if path is None or not path.is_file():
        raise HTTPException(404, "File not found")
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=ctype, filename=os.path.basename(rel or path.name))


# ====================================================================== static paths first
@router.get("/choices")
def choices(user: User = Depends(get_current_user)):
    return svc.choices_payload()


@router.get("")
def projects_list(
    search: str = "", status: str = "", priority: str = "", sort: str = "-created_at", page: str | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """projects_list_view"""
    return svc.list_projects(db, user, search, status, priority, sort, page)


@router.post("")
def project_create(body: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """project_create_view"""
    cleaned, errs = svc.clean_project_form(body.model_dump())
    errs.raise_if_any("Please correct the errors in the form.")
    project = ResearchProject(owner_id=user.id, is_active=1, end_date=None, deadline=None)
    svc.apply_project_fields(project, cleaned)
    project.status = "planning"
    db.add(project)
    db.commit()
    if project.has_authors:
        svc.process_author_formset(db, project, [a.model_dump() for a in body.authors], existing_project=False)
        db.commit()
    return {"id": project.id, "message": f'Project "{project.title}" created successfully!'}


@router.get("/collaborators")
def collaborators_list(
    search: str = "", project: str = "", role: str = "",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """collaborators_list_view (+ CollaboratorSearchForm)"""
    projects = svc.user_project_options(db, user)
    stmt = (select(ResearchProjectCollaborator)
            .join(ResearchProject, ResearchProjectCollaborator.project_id == ResearchProject.id)
            .join(User, ResearchProjectCollaborator.user_id == User.id)
            .where(or_(ResearchProject.owner_id == user.id, ResearchProjectCollaborator.user_id == user.id))
            .options(joinedload(ResearchProjectCollaborator.user), joinedload(ResearchProjectCollaborator.project)))

    # Form validation: an unknown project / role makes the whole form invalid -> no filters applied
    form_valid = len(search) <= 255
    project_obj = None
    if project:
        try:
            project_obj = next((p for p in projects if p.id == int(project)), None)
        except ValueError:
            project_obj = None
        if project_obj is None:
            form_valid = False
    if role and role not in {v for v, _ in svc.ROLE_CHOICES}:
        form_valid = False
    if form_valid:
        q = search.strip()
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like),
                                  ResearchProjectCollaborator.role.ilike(like)))
        if project_obj is not None:
            stmt = stmt.where(ResearchProjectCollaborator.project_id == project_obj.id)
        if role:
            stmt = stmt.where(ResearchProjectCollaborator.role == role)
    stmt = stmt.order_by(ResearchProject.title, User.first_name, User.last_name)
    rows = db.execute(stmt).scalars().unique().all()
    return {
        "collaborators": [
            {**svc.collaborator_payload(c), "project": {"id": c.project.id, "title": c.project.title},
             "can_manage": c.project.owner_id == user.id}
            for c in rows
        ],
        "projects": [{"value": p.id, "label": p.title} for p in projects],
        "roles": [{"value": v, "label": label} for v, label in svc.ROLE_CHOICES],
        "form_errors": not form_valid,
        "page_title": "Project Collaborators",
    }


@router.get("/all-collaborators")
def all_collaborators_projects(
    search: str = "", role: str = "", project: str = "",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """all_collaborators_projects_view — every collaboration in the system, grouped by user."""
    stmt = (select(ResearchProjectCollaborator)
            .join(User, ResearchProjectCollaborator.user_id == User.id)
            .join(ResearchProject, ResearchProjectCollaborator.project_id == ResearchProject.id)
            .options(joinedload(ResearchProjectCollaborator.user), joinedload(ResearchProjectCollaborator.project))
            .order_by(User.first_name, User.last_name, ResearchProject.title))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like),
                              ResearchProject.title.ilike(like)))
    if role:
        stmt = stmt.where(ResearchProjectCollaborator.role == role)
    if project:
        try:
            stmt = stmt.where(ResearchProjectCollaborator.project_id == int(project))
        except ValueError:
            stmt = stmt.where(ResearchProjectCollaborator.id == -1)
    rows = db.execute(stmt).scalars().unique().all()

    grouped: dict[int, dict[str, Any]] = {}
    for c in rows:
        entry = grouped.setdefault(c.user_id, {"user": svc.user_payload(c.user), "projects": []})
        entry["projects"].append({
            "project": {"id": c.project.id, "title": c.project.title,
                        "start_date": svc.iso_date(c.project.start_date)},
            "role": c.role, "role_display": svc.display(svc.ROLE_CHOICES, c.role), "joined_at": iso(c.joined_at),
        })
    all_projects = db.execute(
        select(ResearchProject).where(ResearchProject.id.in_(select(ResearchProjectCollaborator.project_id)))
        .order_by(ResearchProject.title)).scalars().all()
    return {
        "collaborators_data": list(grouped.values()),
        "search_query": search, "role_filter": role, "project_filter": project,
        "all_projects": [{"value": p.id, "label": p.title} for p in all_projects],
        "role_choices": [{"value": v, "label": label} for v, label in svc.ROLE_CHOICES],
        "total_collaborators": len(grouped),
        "total_collaborations": len(rows),
        "page_title": "All Project Collaborators",
    }


@router.get("/milestones/{milestone_id}/attachment")
def milestone_attachment(milestone_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.get(ProjectMilestone, milestone_id)
    if m is None or not m.attachment:
        raise HTTPException(404, "File not found")
    project = svc.get_project_or_404(db, m.project_id)
    svc.require_access(db, project, user, "You do not have permission to view this project timeline.")
    return _file_response(m.attachment)


# ====================================================================== single project
@router.get("/{project_id}")
def project_detail(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """project_detail_view"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_access(db, project, user, "You do not have permission to view this project.")
    return svc.project_detail(db, project, user)


@router.get("/{project_id}/edit")
def project_edit_form(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """project_edit_view (GET)"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_owner(project, user, "Only the project owner can edit this project.")
    data = svc.project_fields(project)
    data["id"] = project.id
    data["authors"] = [svc.author_payload(a) for a in svc.project_authors(db, project.id)]
    data["page_title"] = f"Edit Project: {project.title}"
    return data


@router.put("/{project_id}")
def project_update(project_id: int, body: ProjectIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """project_edit_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_owner(project, user, "Only the project owner can edit this project.")
    cleaned, errs = svc.clean_project_form(body.model_dump())
    errs.raise_if_any("Please correct the errors in the form.")
    svc.apply_project_fields(project, cleaned)
    db.commit()
    if project.has_authors:
        svc.process_author_formset(db, project, [a.model_dump() for a in body.authors], existing_project=True)
        db.commit()
    # Django redirected without a success message
    return {"id": project.id}


@router.get("/{project_id}/delete")
def project_delete_confirm(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """project_delete_view (GET confirmation page)"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_owner(project, user, "Only the project owner can delete this project.")
    total_tasks, _ = svc.task_counts(db, project.id)
    docs = db.execute(select(ResearchProjectDocument.id).where(
        ResearchProjectDocument.project_id == project.id)).all()
    return {
        "id": project.id, "title": project.title, "description": project.description,
        "description_short": svc.truncatewords(project.description, 30),
        "project_type_display": svc.display(svc.PROJECT_TYPE_CHOICES, project.project_type),
        "status_display": svc.display(svc.STATUS_CHOICES, project.status),
        "collaborator_count": svc.collaborator_count(db, project.id),
        "task_count": total_tasks, "document_count": len(docs),
        "page_title": f"Delete Project: {project.title}",
    }


@router.delete("/{project_id}")
def project_delete(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """project_delete_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_owner(project, user, "Only the project owner can delete this project.")
    title = project.title
    svc.delete_project(db, project)
    return {"message": f'Project "{title}" has been deleted successfully.'}


# ---------------------------------------------------------------------- timeline
@router.get("/{project_id}/timeline")
def project_timeline(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """project_timeline_view (GET) — creates the default milestones when the project has none."""
    project = svc.get_project_or_404(db, project_id)
    svc.require_access(db, project, user, "You do not have permission to view this project timeline.")
    if not svc.project_milestones(db, project.id):
        svc.create_default_milestones_for_project(db, project, user)
    return {
        "project": {
            "id": project.id, "title": project.title, "description": project.description,
            "start_date": svc.iso_date(project.start_date),
            "estimated_end_date": svc.iso_date(project.estimated_end_date),
            "status": project.status, "status_display": svc.display(svc.STATUS_CHOICES, project.status),
        },
        "milestones": [svc.milestone_payload(m) for m in svc.project_milestones(db, project.id)],
        "milestone_statuses": [{"value": v, "label": label} for v, label in svc.MILESTONE_STATUS_CHOICES],
        "can_edit": svc.is_owner(project, user),
        "page_title": f"Timeline: {project.title}",
    }


@router.post("/{project_id}/timeline")
async def project_timeline_save(project_id: int, request: Request, user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    """project_timeline_view (POST). Multipart: `milestones` = JSON list of rows, files `attachment-<index>`
    (or the row's `file_key`)."""
    project = svc.get_project_or_404(db, project_id)
    svc.require_access(db, project, user, "You do not have permission to view this project timeline.")
    if not svc.is_owner(project, user):
        raise HTTPException(403, "Only the project owner can edit the timeline.")
    form = await request.form()
    try:
        rows = json.loads(str(form.get("milestones") or "[]"))
        if not isinstance(rows, list):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "Please correct the errors in the timeline.")
    files = {k: v for k, v in form.items() if hasattr(v, "filename") and hasattr(v, "file")}
    errors = svc.process_milestone_formset(db, project, user, rows, files)  # type: ignore[arg-type]
    if errors:
        raise HTTPException(400, f'Timeline errors: {"; ".join(errors)}')
    return {"message": "Project timeline updated successfully!",
            "milestones": [svc.milestone_payload(m) for m in svc.project_milestones(db, project.id)]}


# ---------------------------------------------------------------------- documents
@router.get("/{project_id}/upload-document")
def upload_document_page(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = svc.get_project_or_404(db, project_id)
    svc.require_access(db, project, user, "You do not have permission to upload documents to this project.")
    return {"id": project.id, "title": project.title, "page_title": f"Upload Document - {project.title}"}


@router.post("/{project_id}/upload-document")
def upload_document(
    project_id: int, title: str = Form(""), description: str = Form(""),
    document_file: UploadFile | None = File(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """project_upload_document"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_access(db, project, user, "You do not have permission to upload documents to this project.")
    if not title or document_file is None or not document_file.filename:
        raise HTTPException(400, "Title and file are required.")
    try:
        if len(title) > 255:
            raise ValueError("(1406, \"Data too long for column 'title' at row 1\")")
        rel = svc.save_limited(document_file, "projects/documents")
        doc = ResearchProjectDocument(project_id=project.id, title=title, description=description or "",
                                      file=rel, uploaded_by_id=user.id)
        db.add(doc)
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — Django showed the exception text
        db.rollback()
        raise HTTPException(400, f"Error uploading document: {exc}")
    return {"id": doc.id, "message": f'Document "{title}" uploaded successfully!'}


@router.get("/{project_id}/documents/{document_id}/download")
def download_document(project_id: int, document_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    project = svc.get_project_or_404(db, project_id)
    doc = db.get(ResearchProjectDocument, document_id)
    if doc is None or doc.project_id != project.id:
        raise HTTPException(404, "No ResearchProjectDocument matches the given query.")
    svc.require_access(db, project, user, "You do not have permission to view this project.")
    return _file_response(doc.file)


@router.delete("/{project_id}/documents/{document_id}")
def delete_document(project_id: int, document_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """project_delete_document"""
    project = svc.get_project_or_404(db, project_id)
    doc = db.get(ResearchProjectDocument, document_id)
    if doc is None or doc.project_id != project.id:
        raise HTTPException(404, "No ResearchProjectDocument matches the given query.")
    if not (svc.is_owner(project, user) or doc.uploaded_by_id == user.id):
        raise HTTPException(403, "You do not have permission to delete this document.")
    if doc.file:
        delete_file(doc.file)
    title = doc.title
    db.delete(doc)
    db.commit()
    return {"message": f'Document "{title}" deleted successfully!'}


# ---------------------------------------------------------------------- collaborators
@router.post("/{project_id}/collaborators/by-email", status_code=201)
def add_project_collaborator_legacy(project_id: int, body: LegacyCollaboratorIn,
                                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """add_project_collaborator (legacy JSON API at documents/api/projects/<id>/collaborators/)"""
    project = svc.get_project_or_404(db, project_id)
    if project.owner_id != user.id:
        raise HTTPException(403, "Only the project owner can add collaborators")
    if not body.email:
        raise HTTPException(400, "Email is required")
    matches = db.execute(select(User).where(User.email == body.email)).scalars().all()
    if not matches:
        raise HTTPException(404, "User not found")
    if len(matches) > 1:
        raise HTTPException(500, "get() returned more than one User -- it returned %d!" % len(matches))
    target = matches[0]
    if db.execute(select(ResearchProjectCollaborator.id).where(
            ResearchProjectCollaborator.project_id == project.id,
            ResearchProjectCollaborator.user_id == target.id)).first():
        raise HTTPException(400, "User is already a collaborator")
    collab = ResearchProjectCollaborator(project_id=project.id, user_id=target.id, role=body.role, is_active=1)
    db.add(collab)
    db.commit()
    return {"message": f"{svc.get_full_name(target)} added as {body.role}", "collaborator_id": collab.id}


@router.get("/{project_id}/collaborators")
def project_collaborators(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """project_collaborators_view"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_access(db, project, user, "You do not have permission to view this project's collaborators.")
    rows = db.execute(select(ResearchProjectCollaborator)
                      .join(User, ResearchProjectCollaborator.user_id == User.id)
                      .where(ResearchProjectCollaborator.project_id == project.id)
                      .order_by(ResearchProjectCollaborator.role, User.first_name)).scalars().all()
    return {
        "project": {"id": project.id, "title": project.title,
                    "description_short": svc.truncatewords(project.description, 20),
                    "owner": svc.user_payload(project.owner), "created_at": iso(project.created_at)},
        "collaborators": [svc.collaborator_payload(c) for c in rows],
        "can_manage": svc.is_owner(project, user),
        "page_title": f"Collaborators - {project.title}",
    }


@router.get("/{project_id}/collaborators/form")
def add_collaborator_form(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """add_collaborator_view (GET)"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_owner(project, user, "Only the project owner can add collaborators.")
    return {
        "project": {"id": project.id, "title": project.title,
                    "description_short": svc.truncatewords(project.description, 20)},
        "users": [svc.user_option(u) for u in svc.available_collaborator_users(db, project)],
        "roles": [{"value": v, "label": label} for v, label in svc.ROLE_CHOICES],
        "default_role": "contributor",
        "page_title": f"Add Collaborator to {project.title}",
    }


@router.post("/{project_id}/collaborators")
def add_collaborator(project_id: int, body: CollaboratorIn, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """add_collaborator_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    svc.require_owner(project, user, "Only the project owner can add collaborators.")
    target, role, errs = svc.clean_collaborator_form(db, project, body.model_dump(), None)
    errs.raise_if_any("Please correct the following errors:")
    collab = ResearchProjectCollaborator(project_id=project.id, user_id=target.id, role=role, is_active=1)
    db.add(collab)
    db.commit()
    return {"id": collab.id,
            "message": f"{svc.get_full_name(target)} has been added as {svc.display(svc.ROLE_CHOICES, role)}."}


def _get_collaborator(db: Session, project: ResearchProject, collaborator_id: int) -> ResearchProjectCollaborator:
    c = db.get(ResearchProjectCollaborator, collaborator_id)
    if c is None or c.project_id != project.id:
        raise HTTPException(404, "No ResearchProjectCollaborator matches the given query.")
    return c


@router.get("/{project_id}/collaborators/{collaborator_id}")
def collaborator_detail(project_id: int, collaborator_id: int, action: str = Query("edit"),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """edit_collaborator_view / delete_collaborator_view (GET)"""
    project = svc.get_project_or_404(db, project_id)
    c = _get_collaborator(db, project, collaborator_id)
    svc.require_owner(project, user, "Only the project owner can remove collaborators." if action == "delete"
                      else "Only the project owner can edit collaborators.")
    return {
        "project": {"id": project.id, "title": project.title},
        "collaborator": svc.collaborator_payload(c),
        "user_option": svc.user_option(c.user),
        "roles": [{"value": v, "label": label} for v, label in svc.ROLE_CHOICES],
    }


@router.put("/{project_id}/collaborators/{collaborator_id}")
def edit_collaborator(project_id: int, collaborator_id: int, body: CollaboratorIn,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """edit_collaborator_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    c = _get_collaborator(db, project, collaborator_id)
    svc.require_owner(project, user, "Only the project owner can edit collaborators.")
    _, role, errs = svc.clean_collaborator_form(db, project, body.model_dump(), c)
    errs.raise_if_any("Please correct the following errors:")
    c.role = role
    db.commit()
    return {"message": f"{svc.get_full_name(c.user)}'s role has been updated to {svc.display(svc.ROLE_CHOICES, role)}."}


@router.delete("/{project_id}/collaborators/{collaborator_id}")
def delete_collaborator(project_id: int, collaborator_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """delete_collaborator_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    c = _get_collaborator(db, project, collaborator_id)
    svc.require_owner(project, user, "Only the project owner can remove collaborators.")
    name = svc.get_full_name(c.user)
    db.delete(c)
    db.commit()
    return {"message": f"{name} has been removed from the project."}


# ---------------------------------------------------------------------- tasks
def _require_task_permission(db: Session, project: ResearchProject, user: User, message: str) -> None:
    if not (svc.is_owner(project, user) or svc.is_collaborator(db, project, user)):
        raise HTTPException(403, message)


def _get_task(db: Session, project: ResearchProject, task_id: int) -> ResearchProjectTask:
    t = db.get(ResearchProjectTask, task_id)
    if t is None or t.project_id != project.id:
        raise HTTPException(404, "No ResearchProjectTask matches the given query.")
    return t


def _task_form_context(db: Session, project: ResearchProject) -> dict[str, Any]:
    return {
        "project": {"id": project.id, "title": project.title,
                    "description_short": svc.truncatewords(project.description, 20)},
        "users": [svc.user_option(u) for u in svc.assignable_users(db, project)],
        "statuses": [{"value": v, "label": label} for v, label in svc.TASK_STATUS_CHOICES],
        "priorities": [{"value": v, "label": label} for v, label in svc.TASK_PRIORITY_CHOICES],
    }


@router.get("/{project_id}/tasks/form")
def add_task_form(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """add_task_view (GET)"""
    project = svc.get_project_or_404(db, project_id)
    _require_task_permission(db, project, user, "You do not have permission to add tasks to this project.")
    ctx = _task_form_context(db, project)
    ctx["initial"] = {"status": "todo", "priority": "medium"}
    ctx["page_title"] = f"Add Task to {project.title}"
    return ctx


@router.post("/{project_id}/tasks")
def add_task(project_id: int, body: TaskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """add_task_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    _require_task_permission(db, project, user, "You do not have permission to add tasks to this project.")
    cleaned, errs = svc.clean_task_form(db, project, body.model_dump())
    errs.raise_if_any("Please correct the following errors:")
    task = ResearchProjectTask(project_id=project.id, **cleaned)
    db.add(task)
    db.commit()
    return {"id": task.id, "message": f'Task "{task.title}" has been added to the project.'}


@router.get("/{project_id}/tasks/{task_id}")
def task_detail(project_id: int, task_id: int, action: str = Query("edit"),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """edit_task_view / delete_task_view (GET)"""
    project = svc.get_project_or_404(db, project_id)
    task = _get_task(db, project, task_id)
    _require_task_permission(db, project, user, "You do not have permission to delete tasks in this project."
                             if action == "delete" else "You do not have permission to edit tasks in this project.")
    ctx = _task_form_context(db, project)
    ctx["task"] = svc.task_payload(task)
    ctx["page_title"] = f"{'Delete' if action == 'delete' else 'Edit'} Task - {task.title}"
    return ctx


@router.put("/{project_id}/tasks/{task_id}")
def edit_task(project_id: int, task_id: int, body: TaskIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """edit_task_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    task = _get_task(db, project, task_id)
    _require_task_permission(db, project, user, "You do not have permission to edit tasks in this project.")
    cleaned, errs = svc.clean_task_form(db, project, body.model_dump())
    errs.raise_if_any("Please correct the following errors:")
    for k, v in cleaned.items():
        setattr(task, k, v)
    db.commit()
    return {"message": f'Task "{task.title}" has been updated.'}


@router.delete("/{project_id}/tasks/{task_id}")
def delete_task(project_id: int, task_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """delete_task_view (POST)"""
    project = svc.get_project_or_404(db, project_id)
    task = _get_task(db, project, task_id)
    _require_task_permission(db, project, user, "You do not have permission to delete tasks in this project.")
    title = task.title
    db.delete(task)
    db.commit()
    return {"message": f'Task "{title}" has been deleted.'}
