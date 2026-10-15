"""Superadmin API — replacement for Django's /admin/ site.

Every endpoint requires `is_superuser` (in this database no staff user holds Django model
permissions, so effectively only superusers could use the Django admin).
"""
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.database import get_db
from app.models import User
from app.schemas.superadmin_schemas import ActionIn, ListEditIn, PasswordIn, UserAddIn
from app.services import superadmin_core as core
from app.services import superadmin_custom as custom
from app.services import superadmin_extra as extra

router = APIRouter(prefix="/api/superadmin", tags=["superadmin"])


def _ctx(db: Session, user: User) -> core.Ctx:
    return core.Ctx(db, user)


def _guard(db: Session, fn):
    """Database constraint failures become a form error (Django would show a 500 page)."""
    try:
        return fn()
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        detail = str(getattr(exc, "orig", exc))
        raise HTTPException(400, {"message": "The database rejected this change.", "errors": {},
                                  "non_field_errors": [detail]})


def _label(app: str, model: str) -> str:
    return core.label_for(app, model)


async def _form_payload(request: Request) -> tuple[dict, dict[str, UploadFile]]:
    """Body is either JSON or multipart (`payload` = JSON string, files as `file__<field>`)."""
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        return (await request.json()) or {}, {}
    form = await request.form()
    raw = form.get("payload") or "{}"
    try:
        payload = json.loads(raw if isinstance(raw, str) else "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid payload")
    uploads = {k[len("file__"):]: v for k, v in form.multi_items()
               if k.startswith("file__") and hasattr(v, "filename") and v.filename}
    return payload, uploads


# ------------------------------------------------------------------ dashboard
@router.get("/index")
def admin_index(db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return core.index(_ctx(db, user))


@router.get("/recent-actions")
def recent(limit: int = 10, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return {"entries": core.recent_actions(_ctx(db, user), min(max(limit, 1), 100))}


# ------------------------------------------------------------------ generic model admin
@router.get("/models/{app}/{model}/config")
def model_config(app: str, model: str, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return core.model_config(_ctx(db, user), _label(app, model))


@router.get("/models/{app}/{model}/")
@router.get("/models/{app}/{model}")
def changelist(app: str, model: str, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_superuser)):
    label = _label(app, model)
    params = {k: v for k, v in request.query_params.items() if k != "token"}
    return core.changelist(_ctx(db, user), label, params)


@router.get("/models/{app}/{model}/autocomplete")
def autocomplete(app: str, model: str, field: str, q: str = "", page: int = 1, all: bool = False,
                 db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return core.autocomplete(_ctx(db, user), _label(app, model), field, q.strip(), max(1, page), all)


@router.post("/models/{app}/{model}/action")
def run_action(app: str, model: str, body: ActionIn, db: Session = Depends(get_db),
               user: User = Depends(require_superuser)):
    label = _label(app, model)
    c = _ctx(db, user)
    a = core.admin(label)
    names = [n for n, _ in a["actions"]]
    if not body.action or body.action not in names:
        return {"messages": [{"level": "warning", "message": "No action selected."}]}
    pks = core.selected_pks(c, label, body.ids, body.select_across, body.params)
    if not pks:
        return {"messages": [{"level": "warning", "message":
                              "Items must be selected in order to perform actions on them. No items have been changed."}]}
    if body.action == "delete_selected":
        s = core.MODELS[label]
        if not body.post:
            return {"confirm": True, "ids": [core.pk_to_str(label, p) for p in pks],
                    "summary": core.delete_summary(c, label, pks)}
        deleted = _guard(db, lambda: core.delete_objects(c, label, pks))
        n = len(deleted)
        items = s["verbose_name"] if n == 1 else s["verbose_name_plural"]
        return {"messages": [{"level": "success", "message": f"Successfully deleted {n} {items}."}]}
    fn = custom.ACTIONS.get(label, {}).get(body.action)
    if fn is None:
        raise HTTPException(400, "No action selected.")
    msgs = _guard(db, lambda: fn(c, pks))
    return {"messages": [{"level": lvl, "message": m} for lvl, m in msgs]}


@router.post("/models/{app}/{model}/list-edit")
def list_edit(app: str, model: str, body: ListEditIn, db: Session = Depends(get_db),
              user: User = Depends(require_superuser)):
    label = _label(app, model)
    return _guard(db, lambda: core.list_edit(_ctx(db, user), label, [r.model_dump() for r in body.rows]))


@router.get("/models/{app}/{model}/add")
def add_form(app: str, model: str, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    label = _label(app, model)
    if not core.admin(label)["perms"]["add"]:
        raise HTTPException(403, "You do not have permission to add this object.")
    return core.initial_data(_ctx(db, user), label)


@router.post("/models/{app}/{model}/add")
@router.post("/models/{app}/{model}/")
async def create(app: str, model: str, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_superuser)):
    label = _label(app, model)
    payload, uploads = await _form_payload(request)
    c = _ctx(db, user)
    if label == "authentication.User":
        return _guard(db, lambda: extra.add_user(c, UserAddIn(**(payload.get("data") or payload)).model_dump()))
    res = _guard(db, lambda: core.save_object(c, label, None, payload.get("data") or {}, uploads,
                                              set(payload.get("clear") or []), payload.get("inlines")))
    res["message"] = core.save_message(label, res["str"], True, payload.get("then"))
    return res


@router.get("/models/{app}/{model}/{pk}")
def get_object(app: str, model: str, pk: str, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    label = _label(app, model)
    c = _ctx(db, user)
    return core.object_data(c, label, core.get_row(c, label, pk))


@router.post("/models/{app}/{model}/{pk}")
@router.put("/models/{app}/{model}/{pk}")
async def update_object(app: str, model: str, pk: str, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(require_superuser)):
    label = _label(app, model)
    payload, uploads = await _form_payload(request)
    c = _ctx(db, user)
    res = _guard(db, lambda: core.save_object(c, label, pk, payload.get("data") or {}, uploads,
                                              set(payload.get("clear") or []), payload.get("inlines")))
    res["message"] = core.save_message(label, res["str"], False, payload.get("then"))
    return res


@router.get("/models/{app}/{model}/{pk}/delete")
def delete_confirmation(app: str, model: str, pk: str, db: Session = Depends(get_db),
                        user: User = Depends(require_superuser)):
    label = _label(app, model)
    c = _ctx(db, user)
    row = core.get_row(c, label, pk)
    pkv = row[core.MODELS[label]["pk_column"]]
    return {"pk": core.pk_to_str(label, pkv), "str": c.str(label, row), "summary": core.delete_summary(c, label, [pkv])}


@router.delete("/models/{app}/{model}/{pk}")
def delete_object(app: str, model: str, pk: str, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    label = _label(app, model)
    c = _ctx(db, user)
    row = core.get_row(c, label, pk)
    rep = c.str(label, row)
    _guard(db, lambda: core.delete_objects(c, label, [row[core.MODELS[label]["pk_column"]]]))
    return {"message": f"The {core.MODELS[label]['verbose_name']} “{rep}” was deleted successfully."}


@router.get("/models/{app}/{model}/{pk}/history")
def object_history(app: str, model: str, pk: str, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return core.history(_ctx(db, user), _label(app, model), pk)


# ------------------------------------------------------------------ UserAdmin password form
@router.get("/users/{pk}/password")
def password_form(pk: str, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return extra.password_form(_ctx(db, user), pk)


@router.post("/users/{pk}/password")
def password_change(pk: str, body: PasswordIn, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return _guard(db, lambda: extra.change_password(_ctx(db, user), pk, body.model_dump()))


# ------------------------------------------------------------------ DocumentVersion change file
@router.get("/documentversion/{pk}/change-file")
def change_file_form(pk: str, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return extra.change_file_form(_ctx(db, user), pk)


@router.post("/documentversion/{pk}/change-file")
async def change_file(pk: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    form = await request.form()
    up: Any = form.get("new_file")
    confirm = str(form.get("confirm_delete_annotations") or "").lower() in ("1", "true", "on", "yes")
    return extra.change_file(_ctx(db, user), pk, up if hasattr(up, "filename") else None, confirm)


# ------------------------------------------------------------------ timezone management
@router.get("/timezone")
def timezone_overview(user: User = Depends(require_superuser)):
    return extra.timezone_overview()


@router.get("/timezone/stats")
def timezone_stats(db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    return extra.timezone_stats(_ctx(db, user))


@router.get("/timezone/timezones")
def timezones(all: bool = False, user: User = Depends(require_superuser)):
    return {"timezones": extra.list_timezones(all)}
