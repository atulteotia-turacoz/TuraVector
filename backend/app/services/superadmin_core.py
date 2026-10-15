"""Generic, metadata-driven port of django.contrib.admin.

Everything is driven by `superadmin_registry` (a snapshot of the Django ModelAdmins and
model `_meta`) plus the hand-written bits in `superadmin_custom`. Tables are accessed with
SQLAlchemy Core (`Base.metadata.tables[...]`), so one engine serves every model.

Behaviour mirrors Django admin:
  * changelist: list_display, list_filter (boolean / choices / related / date / all-values),
    search_fields (^ = @ prefixes, related lookups, AND-of-terms), ordering via `o`,
    date_hierarchy drill-down, 100 rows per page, "show all" up to 200
  * change form: fieldsets, readonly_fields, inlines, M2M, FK, file fields, unique checks
  * delete: NestedObjects-style collector honouring each FK's on_delete
    (CASCADE / SET_NULL / PROTECT), "objects that will be deleted" summary
  * django_admin_log rows for every add / change / delete, with Django's JSON change_message
"""
from __future__ import annotations

import datetime
import decimal
import ipaddress
import json
import math
import re
import uuid
from collections import defaultdict
from typing import Any

import pytz
from fastapi import HTTPException, UploadFile
from sqlalchemy import Table, and_, delete, func, insert, literal_column, not_, null, or_, select, update
from sqlalchemy.orm import Session

from app.core import files as files_core
from app.core.utils import iso, user_tz
from app.models import Base, User, utcnow
from app.services import superadmin_custom as custom
from app.services import superadmin_scope as ws_scope
from app.services.superadmin_registry import APPS, MODELS, REGISTERED, RELS, TABLES

EMPTY = "-"  # ModelAdmin.empty_value_display
LIST_PER_PAGE = 100
LIST_MAX_SHOW_ALL = 200
ADDITION, CHANGE, DELETION = 1, 2, 3

INT_TYPES = {"IntegerField", "PositiveIntegerField", "SmallIntegerField", "BigIntegerField", "PositiveSmallIntegerField",
             "AutoField", "BigAutoField"}
TEXTISH = {"CharField", "EmailField", "URLField", "GenericIPAddressField", "SlugField", "TextField"}
FK_TYPES = {"ForeignKey", "OneToOneField"}
FILE_TYPES = {"FileField", "ImageField"}
REG_SET = set(REGISTERED)


# =============================================================================== registry helpers
def capfirst(s: Any) -> str:
    s = str(s)
    return s[:1].upper() + s[1:] if s else s


def text_list(items: list[str], last: str = "and") -> str:
    """django.utils.text.get_text_list"""
    items = [str(i) for i in items]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} {last} {items[-1]}"


def spec(label: str) -> dict:
    return MODELS[label]


def table(label: str) -> Table:
    return Base.metadata.tables[MODELS[label]["table"]]


def pkcol(label: str):
    return table(label).c[MODELS[label]["pk_column"]]


def is_uuid_pk(label: str) -> bool:
    return MODELS[label]["pk_type"] == "UUIDField"


def label_for(app: str, model: str) -> str:
    for label in REGISTERED:
        s = MODELS[label]
        if s["app_label"] == app and s["model_name"] == model.lower():
            return label
    raise HTTPException(404, "Not found")


def admin(label: str) -> dict:
    return MODELS[label]["admin"]


def url_info(label: str, pk: Any = None) -> dict:
    s = MODELS[label]
    d = {"app": s["app_label"], "model": s["model_name"]}
    if pk is not None:
        d["pk"] = pk_to_str(label, pk)
    return d


def pk_to_db(label: str, raw: Any):
    if raw is None or raw == "":
        return None
    if is_uuid_pk(label):
        try:
            return uuid.UUID(str(raw)).hex
        except ValueError:
            raise HTTPException(404, "Not found")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise HTTPException(404, "Not found")


def pk_to_str(label: str, value: Any) -> str:
    if value is None:
        return ""
    if label in MODELS and is_uuid_pk(label):
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            return str(value)
    return str(value)


def field_label(label: str, name: str) -> str:
    """Form / column label: capfirst(verbose_name) or ModelAdmin method short_description."""
    if name == "__str__":
        return capfirst(MODELS[label]["verbose_name"])
    comp = custom.COMPUTED.get((label, name))
    if comp:
        return comp["label"]
    f = MODELS[label]["fields"].get(name)
    return capfirst(f["verbose_name"]) if f else capfirst(name.replace("_", " "))


def kind_of(f: dict) -> str:
    t = f["type"]
    if f.get("choices") and t not in FK_TYPES:
        return "choice"
    return {
        "CharField": "char", "SlugField": "char", "EmailField": "email", "URLField": "url",
        "GenericIPAddressField": "ip", "TextField": "text", "FloatField": "float", "DecimalField": "decimal",
        "BooleanField": "nullbool" if f.get("null") else "bool", "NullBooleanField": "nullbool",
        "DateField": "date", "DateTimeField": "datetime", "JSONField": "json", "ForeignKey": "fk",
        "OneToOneField": "fk", "ManyToManyField": "m2m", "FileField": "file", "ImageField": "image",
        "UUIDField": "uuid",
    }.get(t, "int" if t in INT_TYPES else "char")


# =============================================================================== request context
class Ctx:
    """Per-request cache of related rows (avoids N+1 when rendering __str__ for 100 rows)."""

    def __init__(self, db: Session, user: User | None = None):
        self.db = db
        self.user = user
        self._cache: dict[tuple[str, Any], dict | None] = {}
        self._ct_by_id: dict[int, dict] | None = None
        # workspace chosen in the superadmin top bar (None = whole platform)
        self.org_id: int | None = ws_scope.workspace_of(db)

    def scope(self, label: str) -> list:
        """[condition] limiting a workspace-level model to the chosen workspace, else []."""
        cond = ws_scope.condition(table(label), self.org_id)
        return [cond] if cond is not None else []

    def fetch(self, label: str, pk: Any) -> dict | None:
        if pk is None:
            return None
        key = (label, pk)
        if key not in self._cache:
            row = self.db.execute(select(table(label)).where(pkcol(label) == pk)).mappings().first()
            self._cache[key] = dict(row) if row else None
        return self._cache[key]

    def prefetch(self, label: str, pks) -> None:
        need = list({p for p in pks if p is not None and (label, p) not in self._cache})
        for i in range(0, len(need), 500):
            chunk = need[i:i + 500]
            rows = self.db.execute(select(table(label)).where(pkcol(label).in_(chunk))).mappings().all()
            pcol = MODELS[label]["pk_column"]
            found = {r[pcol]: dict(r) for r in rows}
            for p in chunk:
                self._cache[(label, p)] = found.get(p)

    def remember(self, label: str, row: dict) -> None:
        self._cache[(label, row[MODELS[label]["pk_column"]])] = row

    def rel(self, label: str, row: dict | None, fname: str) -> dict | None:
        if not row:
            return None
        f = MODELS[label]["fields"][fname]
        return self.fetch(f["rel"], row.get(f["column"]))

    def str(self, label: str, row: dict | None) -> str:
        if row is None:
            return "None"
        fn = custom.STR.get(label)
        if fn:
            try:
                return str(fn(self, row))
            except Exception:  # noqa: BLE001 — broken related data must not break the admin
                pass
        s = MODELS.get(label)
        pk = row.get(s["pk_column"]) if s else row.get("id")
        obj = s["object_name"] if s else label.split(".")[-1]
        return f"{obj} object ({pk_to_str(label, pk)})"

    def choice_label(self, label: str, field: str, value: Any) -> str:
        f = MODELS[label]["fields"][field]
        for k, v in f.get("choices") or []:
            if k == value or str(k) == str(value):
                return v
        return "" if value is None else str(value)

    def content_type_str(self, ct: dict | None) -> str:
        """ContentType.__str__ → app_labeled_name"""
        if not ct:
            return "None"
        app_v = APPS.get(ct["app_label"], ct["app_label"])
        model_v = ct["model"]
        for t in TABLES.values():
            lab = t["label"]
            if lab.split(".")[0] == ct["app_label"] and lab.split(".")[1].lower() == ct["model"]:
                model_v = t["verbose_name"]
                break
        return f"{app_v} | {model_v}"


# =============================================================================== value rendering
def _float(v):
    return float(v) if isinstance(v, decimal.Decimal) else v


def json_value(f: dict, v: Any) -> Any:
    """DB column value → JSON-safe form value."""
    if v is None:
        return None
    k = kind_of(f)
    if k in ("bool", "nullbool"):
        return bool(v)
    if k == "datetime" and isinstance(v, datetime.datetime):
        return iso(v)
    if k == "date" and isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()[:10]
    if k == "decimal":
        return str(v)
    if k == "float":
        return _float(v)
    if k == "uuid":
        try:
            return str(uuid.UUID(str(v)))
        except ValueError:
            return str(v)
    if k == "json":
        return json.dumps(v, indent=2, ensure_ascii=False) if not isinstance(v, str) else v
    if f.get("choices") and kind_of(f) == "choice" and f["type"] in INT_TYPES:
        return v
    if isinstance(v, (datetime.datetime, datetime.date)):
        return iso(v)
    if isinstance(v, decimal.Decimal):
        return str(v)
    return v


def cell(c: Ctx, label: str, name: str, row: dict) -> dict:
    """Render one list_display / readonly value like display_for_field + AdminReadonlyField."""
    if name == "__str__":
        return {"text": c.str(label, row)}
    comp = custom.COMPUTED.get((label, name))
    if comp:
        val = comp["fn"](c, row)
        if comp["kind"] == "boolean":
            return {"bool": bool(val), "kind": "bool"}
        if comp["kind"] == "link":
            return {"kind": "link", **val}
        return {"text": EMPTY if val in (None, "") else str(val)}
    f = MODELS[label]["fields"][name]
    k = kind_of(f)
    if k == "m2m":
        return {"text": ", ".join(o["label"] for o in m2m_current(c, label, name, row)) or EMPTY}
    v = row.get(f["column"])
    if k in FK_TYPES or k == "fk":
        if v is None:
            return {"text": EMPTY}
        rel = c.fetch(f["rel"], v)
        out = {"text": c.str(f["rel"], rel) if rel else str(v)}
        if rel and f["rel"] in REG_SET:
            out["link"] = url_info(f["rel"], v)
        return out
    if k in ("bool", "nullbool"):
        return {"kind": "bool", "bool": None if v is None else bool(v)}
    if v is None or v == "":
        return {"text": EMPTY}
    if k == "choice":
        return {"text": c.choice_label(label, name, v)}
    if k == "datetime":
        return {"kind": "datetime", "value": iso(v)}
    if k == "date":
        return {"kind": "date", "value": v.isoformat()[:10]}
    if k in ("file", "image"):
        return {"kind": "file", "text": str(v), "url": files_core.media_url(v)}
    if k == "json":
        return {"text": json.dumps(v, ensure_ascii=False)}
    if k == "uuid":
        return {"text": json_value(f, v)}
    if k == "float":
        return {"text": str(_float(v))}
    if k == "url":
        return {"text": str(v), "href": str(v)}
    return {"text": str(v)}


# =============================================================================== M2M helpers
def m2m_current(c: Ctx, label: str, name: str, row: dict) -> list[dict]:
    f = MODELS[label]["fields"][name]
    m = f["m2m"]
    through = Base.metadata.tables[m["through"]]
    pk = row[MODELS[label]["pk_column"]]
    ids = [r[0] for r in c.db.execute(select(through.c[m["dst"]]).where(through.c[m["src"]] == pk)).all()]
    c.prefetch(f["rel"], ids)
    rows = [c.fetch(f["rel"], i) for i in ids]
    out = [{"value": r[MODELS[f["rel"]]["pk_column"]], "label": c.str(f["rel"], r)} for r in rows if r]
    return sorted(out, key=lambda o: o["label"])


# =============================================================================== ordering helpers
def _order_cols(label: str, ordering: list[str]):
    t = table(label)
    cols = []
    for o in ordering:
        desc = o.startswith("-")
        name = o.lstrip("-")
        if name == "pk":
            col = pkcol(label)
        elif "__" in name:
            continue  # related ordering (only auth.Permission's Meta, handled separately)
        else:
            f = MODELS[label]["fields"].get(name)
            if not f or "column" not in f:
                continue
            col = t.c[f["column"]]
        cols.append(col.desc() if desc else col.asc())
    return cols


def default_ordering(label: str) -> list[str]:
    s = MODELS[label]
    a = s.get("admin") or {}
    return list(a.get("ordering") or s.get("meta_ordering") or [])


def related_options(c: Ctx, label: str, limit: int | None = None, q: str = "") -> list[dict]:
    """All objects of `label` as {value,label}, ordered like Django's get_choices (admin/Meta ordering)."""
    t = table(label)
    stmt = select(t)
    if label == "auth.Permission":
        ct = Base.metadata.tables["django_content_type"]
        stmt = select(t).join(ct, ct.c.id == t.c.content_type_id).order_by(ct.c.app_label, ct.c.model, t.c.codename)
    else:
        cols = _order_cols(label, default_ordering(label))
        stmt = stmt.order_by(*(cols or [pkcol(label).asc()]))
    stmt = stmt.where(*c.scope(label))  # e.g. only the chosen workspace's users in a "user" dropdown
    if q and label in REG_SET and admin(label).get("search_fields"):
        stmt = stmt.where(search_condition(label, admin(label)["search_fields"], q))
    rows = c.db.execute(stmt.limit(limit) if limit else stmt).mappings().all()
    out = []
    for r in rows:
        r = dict(r)
        c.remember(label, r)
        out.append({"value": json_value(MODELS[label]["fields"][MODELS[label]["pk"]], r[MODELS[label]["pk_column"]]),
                    "label": c.str(label, r)})
    return out


# =============================================================================== lookups (search / filters)
LOOKUPS = {"exact", "iexact", "icontains", "contains", "istartswith", "gte", "gt", "lte", "lt", "isnull", "in",
           "year", "month", "day"}


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def path_condition(label: str, parts: list[str], make):
    """Resolve a Django lookup path (user__username) to an SQL condition on `label`'s table.

    `make(column, field_spec)` builds the final condition. Relations become IN-subqueries.
    """
    t = table(label)
    name = parts[0]
    if name == "pk":
        name = MODELS[label]["pk"]
    f = MODELS[label]["fields"].get(name)
    if f is None:
        raise KeyError(name)
    col = t.c[f["column"]] if "column" in f else None
    if len(parts) == 1:
        if f["type"] in FK_TYPES:
            target = f["rel"]
            return make(col, MODELS[target]["fields"][MODELS[target]["pk"]])
        return make(col, f)
    if f["type"] in FK_TYPES:
        target = f["rel"]
        rest = parts[1:]
        if rest in (["id"], ["pk"]) or rest == [MODELS[target]["pk"]]:
            return make(col, MODELS[target]["fields"][MODELS[target]["pk"]])
        sub = select(pkcol(target)).where(path_condition(target, rest, make))
        return col.in_(sub)
    if f["type"] == "ManyToManyField":
        m = f["m2m"]
        through = Base.metadata.tables[m["through"]]
        target = f["rel"]
        inner = select(through.c[m["src"]]).where(
            through.c[m["dst"]].in_(select(pkcol(target)).where(path_condition(target, parts[1:], make))))
        return pkcol(label).in_(inner)
    raise KeyError(parts[1])


def field_at_path(label: str, parts: list[str]) -> tuple[str, dict]:
    f = MODELS[label]["fields"][parts[0]]
    if len(parts) == 1:
        return label, f
    if f["type"] in FK_TYPES or f["type"] == "ManyToManyField":
        target = f["rel"]
        if parts[1:] in (["id"], ["pk"]):
            return target, MODELS[target]["fields"][MODELS[target]["pk"]]
        return field_at_path(target, parts[1:])
    raise KeyError(parts[1])


def split_terms(q: str) -> list[str]:
    """django.utils.text.smart_split + unescape_string_literal"""
    out = []
    for m in re.finditer(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\S+', q):
        term = m.group(0)
        if len(term) >= 2 and term[0] == term[-1] and term[0] in "\"'":
            term = term[1:-1].replace("\\" + term[0], term[0]).replace("\\\\", "\\")
        out.append(term)
    return out


def search_condition(label: str, search_fields: list[str], q: str):
    """ModelAdmin.get_search_results: each term must match at least one search field."""
    conds = []
    for term in split_terms(q):
        ors = []
        for sf in search_fields:
            if sf.startswith("^"):
                lookup, path = "istartswith", sf[1:]
            elif sf.startswith("="):
                lookup, path = "iexact", sf[1:]
            elif sf.startswith("@"):
                lookup, path = "icontains", sf[1:]
            else:
                lookup, path = "icontains", sf

            def make(col, f, _lookup=lookup, _term=term):
                s = func.lower(col)
                if _lookup == "iexact":
                    return s == _term.lower()
                if _lookup == "istartswith":
                    return s.like(_like_escape(_term.lower()) + "%", escape="\\")
                return s.like("%" + _like_escape(_term.lower()) + "%", escape="\\")
            ors.append(path_condition(label, path.split("__"), make))
        if ors:
            conds.append(or_(*ors))
    return and_(*conds) if conds else None


def _to_utc_naive(dt: datetime.datetime, tz) -> datetime.datetime:
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt.astimezone(pytz.UTC).replace(tzinfo=None)


def coerce_lookup_value(f: dict, raw: str, tz):
    k = kind_of(f)
    if k in ("bool", "nullbool"):
        return 1 if str(raw).lower() in ("1", "true", "yes", "on") else 0
    if k == "datetime":
        try:
            return _to_utc_naive(datetime.datetime.fromisoformat(str(raw).replace(" ", "T").replace("Z", "+00:00")), tz)
        except ValueError:
            d = datetime.date.fromisoformat(str(raw)[:10])
            return _to_utc_naive(datetime.datetime(d.year, d.month, d.day), tz)
    if k == "date":
        return datetime.date.fromisoformat(str(raw)[:10])
    if f["type"] in INT_TYPES or (k == "choice" and f["type"] in INT_TYPES):
        return int(raw)
    if k == "float":
        return float(raw)
    if k == "decimal":
        return decimal.Decimal(str(raw))
    if k == "uuid":
        return uuid.UUID(str(raw)).hex
    return str(raw)


def lookup_condition(label: str, key: str, raw: str, tz):
    parts = key.split("__")
    lookup = "exact"
    if len(parts) > 1 and parts[-1] in LOOKUPS:
        lookup = parts.pop()
    _, fspec = field_at_path(label, parts)

    def make(col, f):
        if lookup == "isnull":
            want = str(raw).lower() in ("true", "1")
            if kind_of(f) in ("file", "image") or f["type"] in TEXTISH:
                empty = or_(col.is_(None), col == "")
                return empty if want else not_(empty)
            return col.is_(None) if want else col.isnot(None)
        if lookup == "in":
            return col.in_([coerce_lookup_value(f, v, tz) for v in str(raw).split(",") if v != ""])
        if lookup in ("year", "month", "day"):
            return None  # handled by date hierarchy
        v = coerce_lookup_value(f, raw, tz)
        if lookup == "exact":
            return col == v
        if lookup == "iexact":
            return func.lower(col) == str(v).lower()
        if lookup in ("gte", "gt", "lte", "lt"):
            return {"gte": col.__ge__, "gt": col.__gt__, "lte": col.__le__, "lt": col.__lt__}[lookup](v)
        if lookup == "istartswith":
            return func.lower(col).like(_like_escape(str(v).lower()) + "%", escape="\\")
        if lookup == "contains":
            return col.like("%" + _like_escape(str(v)) + "%", escape="\\")
        return func.lower(col).like("%" + _like_escape(str(v).lower()) + "%", escape="\\")
    return path_condition(label, parts, make), fspec


# =============================================================================== list filters
def _local_today(tz) -> datetime.date:
    return datetime.datetime.now(tz).date()


def _local_midnight(d: datetime.date, tz) -> datetime.datetime:
    return tz.localize(datetime.datetime(d.year, d.month, d.day))


def _fmt_local(dt: datetime.datetime) -> str:
    return dt.isoformat(sep=" ")


def build_filter_specs(c: Ctx, label: str, params: dict[str, str], tz) -> list[dict]:
    """Django's list_filter specs: title, the GET keys each filter owns, and its choices."""
    specs = []
    for path in admin(label).get("list_filter") or []:
        parts = path.split("__")
        tlabel, f = field_at_path(label, parts)
        k = kind_of(f)
        title = f["verbose_name"]
        opts: list[dict] = []
        if k in ("bool", "nullbool"):
            ek, nk = f"{path}__exact", f"{path}__isnull"
            keys = [ek, nk]
            cur = params.get(ek)
            opts.append({"label": "All", "params": {}, "selected": cur is None and nk not in params})
            opts.append({"label": "Yes", "params": {ek: "1"}, "selected": cur == "1"})
            opts.append({"label": "No", "params": {ek: "0"}, "selected": cur == "0"})
            if f.get("null"):
                opts.append({"label": "Unknown", "params": {nk: "True"}, "selected": params.get(nk) == "True"})
        elif f["type"] in FK_TYPES:
            ek, nk = f"{path}__id__exact", f"{path}__isnull"
            keys = [ek, nk]
            cur = params.get(ek)
            opts.append({"label": "All", "params": {}, "selected": cur is None and nk not in params})
            for o in related_options(c, f["rel"]):
                opts.append({"label": o["label"], "params": {ek: str(o["value"])}, "selected": cur == str(o["value"])})
            if f.get("null"):
                opts.append({"label": EMPTY, "params": {nk: "True"}, "selected": params.get(nk) == "True"})
        elif k == "choice":
            ek, nk = f"{path}__exact", f"{path}__isnull"
            keys = [ek, nk]
            cur = params.get(ek)
            opts.append({"label": "All", "params": {}, "selected": cur is None and nk not in params})
            for val, lab in f["choices"]:
                if val is None:
                    opts.append({"label": lab, "params": {nk: "True"}, "selected": params.get(nk) == "True"})
                    continue
                opts.append({"label": lab, "params": {ek: str(val)}, "selected": cur == str(val)})
        elif k in ("date", "datetime"):
            gk, lk, nk = f"{path}__gte", f"{path}__lt", f"{path}__isnull"
            keys = [gk, lk, nk]
            today = _local_today(tz)
            tomorrow = today + datetime.timedelta(days=1)
            first_month = today.replace(day=1)
            next_month = (first_month + datetime.timedelta(days=32)).replace(day=1)
            first_year = today.replace(month=1, day=1)
            next_year = first_year.replace(year=first_year.year + 1)

            def rng(a: datetime.date, b: datetime.date):
                if k == "date":
                    return {gk: a.isoformat(), lk: b.isoformat()}
                return {gk: _fmt_local(_local_midnight(a, tz)), lk: _fmt_local(_local_midnight(b, tz))}
            choices = [("Any date", {}), ("Today", rng(today, tomorrow)),
                       ("Past 7 days", rng(today - datetime.timedelta(days=7), tomorrow)),
                       ("This month", rng(first_month, next_month)), ("This year", rng(first_year, next_year))]
            if f.get("null"):
                choices += [("No date", {nk: "True"}), ("Has date", {nk: "False"})]
            mine = {kk: params[kk] for kk in keys if kk in params}
            for lab, p in choices:
                opts.append({"label": lab, "params": p, "selected": mine == p})
        else:
            ek, nk = f"{path}__exact", f"{path}__isnull"
            keys = [ek, nk]
            cur = params.get(ek)
            opts.append({"label": "All", "params": {}, "selected": cur is None and nk not in params})
            t = table(label)
            if len(parts) == 1:
                col = t.c[f["column"]]
                vals = [r[0] for r in c.db.execute(select(col).distinct().where(col.isnot(None)).order_by(col)).all()]
            else:
                tt = table(tlabel)
                col = tt.c[f["column"]]
                vals = [r[0] for r in c.db.execute(select(col).distinct().where(col.isnot(None)).order_by(col)).all()]
            has_null = f.get("null")
            for v in vals:
                sv = json_value(f, v)
                opts.append({"label": str(sv), "params": {ek: str(sv)}, "selected": cur == str(sv)})
            if has_null:
                opts.append({"label": EMPTY, "params": {nk: "True"}, "selected": params.get(nk) == "True"})
        specs.append({"title": title, "path": path, "keys": keys, "choices": opts})
    return specs


# =============================================================================== date hierarchy
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def _tz_offset_minutes(tz) -> int:
    off = datetime.datetime.now(tz).utcoffset()
    return int(off.total_seconds() // 60) if off else 0


def date_hierarchy(c: Ctx, label: str, stmt_where, params: dict[str, str], tz) -> dict | None:
    field = admin(label).get("date_hierarchy")
    if not field:
        return None
    f = MODELS[label]["fields"][field]
    t = table(label)
    col = t.c[f["column"]]
    local = func.timestampadd(literal_column("MINUTE"), _tz_offset_minutes(tz), col) if f["type"] == "DateTimeField" else col
    y, m, d = params.get(f"{field}__year"), params.get(f"{field}__month"), params.get(f"{field}__day")
    base = select(t).where(*stmt_where).subquery() if stmt_where else select(t).subquery()
    bcol = base.c[f["column"]]
    blocal = func.timestampadd(literal_column("MINUTE"), _tz_offset_minutes(tz), bcol) if f["type"] == "DateTimeField" else bcol
    out: dict[str, Any] = {"field": field, "title": f["verbose_name"], "choices": [], "back": None}
    if y and m and d:
        out["back"] = {"label": f"{MONTHS[int(m) - 1]} {y}", "params": {f"{field}__year": y, f"{field}__month": m}}
        out["choices"] = [{"label": f"{MONTHS[int(m) - 1]} {int(d)}", "params": {}, "selected": True}]
    elif y and m:
        out["back"] = {"label": str(y), "params": {f"{field}__year": y}}
        days = [r[0] for r in c.db.execute(
            select(func.day(blocal)).where(func.year(blocal) == int(y), func.month(blocal) == int(m))
            .distinct().order_by(func.day(blocal))).all()]
        out["choices"] = [{"label": f"{MONTHS[int(m) - 1]} {dd}",
                           "params": {f"{field}__year": y, f"{field}__month": m, f"{field}__day": str(dd)}} for dd in days]
    elif y:
        out["back"] = {"label": "All dates", "params": {}}
        months = [r[0] for r in c.db.execute(
            select(func.month(blocal)).where(func.year(blocal) == int(y)).distinct().order_by(func.month(blocal))).all()]
        out["choices"] = [{"label": f"{MONTHS[mm - 1]} {y}",
                           "params": {f"{field}__year": y, f"{field}__month": str(mm)}} for mm in months]
    else:
        years = [r[0] for r in c.db.execute(select(func.year(blocal)).where(bcol.isnot(None)).distinct()
                                            .order_by(func.year(blocal))).all()]
        out["choices"] = [{"label": str(yy), "params": {f"{field}__year": str(yy)}} for yy in years]
    out["keys"] = [f"{field}__year", f"{field}__month", f"{field}__day"]
    _ = local
    return out


def date_hierarchy_condition(label: str, params: dict[str, str], tz):
    field = admin(label).get("date_hierarchy")
    if not field:
        return None
    y, m, d = params.get(f"{field}__year"), params.get(f"{field}__month"), params.get(f"{field}__day")
    if not y:
        return None
    f = MODELS[label]["fields"][field]
    col = table(label).c[f["column"]]
    try:
        y = int(y)
        if m and d:
            start = datetime.date(y, int(m), int(d))
            end = start + datetime.timedelta(days=1)
        elif m:
            start = datetime.date(y, int(m), 1)
            end = (start + datetime.timedelta(days=32)).replace(day=1)
        else:
            start, end = datetime.date(y, 1, 1), datetime.date(y + 1, 1, 1)
    except ValueError:
        raise HTTPException(400, "Invalid date hierarchy parameters")
    if f["type"] == "DateTimeField":
        return and_(col >= _to_utc_naive(datetime.datetime(start.year, start.month, start.day), tz),
                    col < _to_utc_naive(datetime.datetime(end.year, end.month, end.day), tz))
    return and_(col >= start, col < end)


# =============================================================================== changelist
RESERVED = {"q", "o", "p", "all", "e", "_to_field"}


def queryset_conditions(c: Ctx, label: str, params: dict[str, str], tz) -> list:
    """WHERE conditions for search + list_filter params + date hierarchy (the ChangeList queryset)."""
    a = admin(label)
    allowed: set[str] = set()
    for path in a.get("list_filter") or []:
        allowed |= {f"{path}__exact", f"{path}__id__exact", f"{path}__isnull", f"{path}__gte", f"{path}__lt"}
    conds = []
    for key, raw in params.items():
        if key in RESERVED or key not in allowed:
            continue
        try:
            cond, _ = lookup_condition(label, key, raw, tz)
        except (KeyError, ValueError, decimal.InvalidOperation):
            raise HTTPException(400, f"Invalid filter value for {key}")
        if cond is not None:
            conds.append(cond)
    conds.extend(c.scope(label))
    dh = date_hierarchy_condition(label, params, tz)
    if dh is not None:
        conds.append(dh)
    q = (params.get("q") or "").strip()
    if q and a.get("search_fields"):
        sc = search_condition(label, a["search_fields"], q)
        if sc is not None:
            conds.append(sc)
    return conds


def ordering_for(label: str, o: str | None) -> tuple[list, list[dict]]:
    """Return (ORDER BY columns, [{index, desc}]) from Django's `o` param (e.g. "2.-1")."""
    a = admin(label)
    t = table(label)
    ld = a["list_display"]
    cols, used = [], []
    if o:
        for part in o.split("."):
            try:
                idx = int(part.lstrip("-"))
                name = ld[idx]
            except (ValueError, IndexError):
                continue
            f = MODELS[label]["fields"].get(name)
            if not f or "column" not in f:
                continue
            col = t.c[f["column"]]
            desc = part.startswith("-")
            cols.append(col.desc() if desc else col.asc())
            used.append({"index": idx, "desc": desc})
    if not cols:
        cols = _order_cols(label, default_ordering(label))
    # Django makes the ordering deterministic by appending -pk
    cols.append(pkcol(label).desc())
    return cols, used


def columns_for(label: str) -> list[dict]:
    a = admin(label)
    out = []
    for i, name in enumerate(a["list_display"]):
        f = MODELS[label]["fields"].get(name)
        sortable = bool(f and "column" in f)
        out.append({"index": i, "name": name, "label": field_label(label, name), "sortable": sortable,
                    "editable": name in (a.get("list_editable") or [])})
    return out


def changelist(c: Ctx, label: str, params: dict[str, str]) -> dict:
    a = admin(label)
    tz = user_tz(c.user)
    t = table(label)
    conds = queryset_conditions(c, label, params, tz)
    full_count = c.db.execute(select(func.count()).select_from(t).where(*c.scope(label))).scalar_one()
    count = c.db.execute(select(func.count()).select_from(t).where(*conds)).scalar_one() if conds else full_count
    order_cols, used = ordering_for(label, params.get("o"))
    show_all = "all" in params and count <= LIST_MAX_SHOW_ALL
    try:
        page = max(1, int(params.get("p") or 1))
    except ValueError:
        page = 1
    per = count if show_all else LIST_PER_PAGE
    pages = max(1, math.ceil(count / per)) if per else 1
    page = min(page, pages)
    stmt = select(t).where(*conds).order_by(*order_cols)
    if not show_all:
        stmt = stmt.limit(LIST_PER_PAGE).offset((page - 1) * LIST_PER_PAGE)
    rows = [dict(r) for r in c.db.execute(stmt).mappings().all()]
    pcol = MODELS[label]["pk_column"]
    for r in rows:
        c.remember(label, r)
    # batch-load FK targets shown in the list
    for name in a["list_display"]:
        f = MODELS[label]["fields"].get(name)
        if f and f["type"] in FK_TYPES:
            c.prefetch(f["rel"], [r.get(f["column"]) for r in rows])
    editable = a.get("list_editable") or []
    out_rows = []
    for r in rows:
        out_rows.append({
            "pk": pk_to_str(label, r[pcol]),
            "str": c.str(label, r),
            "cells": [cell(c, label, name, r) for name in a["list_display"]],
            "values": {name: json_value(MODELS[label]["fields"][name], r[MODELS[label]["fields"][name]["column"]])
                       for name in editable},
        })
    return {
        "label": label,
        "verbose_name": MODELS[label]["verbose_name"],
        "verbose_name_plural": MODELS[label]["verbose_name_plural"],
        "columns": columns_for(label),
        "ordering": used,
        "rows": out_rows,
        "count": count,
        "full_count": full_count,
        "page": page,
        "pages": pages,
        "per_page": LIST_PER_PAGE,
        "can_show_all": count <= LIST_MAX_SHOW_ALL and count > LIST_PER_PAGE,
        "show_all": show_all,
        "filters": build_filter_specs(c, label, params, tz),
        "date_hierarchy": date_hierarchy(c, label, conds, params, tz),
        "search_enabled": bool(a.get("search_fields")),
        "q": params.get("q") or "",
        "actions": [{"name": n, "description": desc.replace("%(verbose_name_plural)s", MODELS[label]["verbose_name_plural"])}
                    for n, desc in a["actions"]],
    }


def selected_pks(c: Ctx, label: str, ids: list[str], select_across: bool, params: dict[str, str]) -> list:
    if select_across:
        conds = queryset_conditions(c, label, params, user_tz(c.user))
        return [r[0] for r in c.db.execute(select(pkcol(label)).where(*conds)).all()]
    pks = [pk_to_db(label, i) for i in ids]
    found = {r[0] for r in c.db.execute(select(pkcol(label)).where(pkcol(label).in_(pks), *c.scope(label))).all()} if pks else set()
    return [p for p in pks if p in found]


# =============================================================================== model config
def field_meta(c: Ctx, label: str, name: str, readonly: bool) -> dict:
    comp = custom.COMPUTED.get((label, name))
    if comp:
        return {"name": name, "label": comp["label"], "kind": "computed", "readonly": True, "required": False}
    f = MODELS[label]["fields"][name]
    k = kind_of(f)
    a = admin(label) if label in REG_SET else {}
    m: dict[str, Any] = {
        "name": name, "label": capfirst(f["verbose_name"]), "kind": k, "readonly": readonly,
        "required": not f.get("blank") and k not in ("bool", "nullbool"),
        "help_text": f.get("help_text", ""), "max_length": f.get("max_length"),
    }
    if f.get("choices"):
        m["choices"] = [[json_value({"type": f["type"]}, v), lab] for v, lab in f["choices"]]
    if k in ("fk", "m2m"):
        target = f["rel"]
        m["rel"] = {"label": target, "verbose_name": MODELS[target]["verbose_name"], "registered": target in REG_SET,
                    **({"app": MODELS[target]["app_label"], "model": MODELS[target]["model_name"]} if target in REG_SET else {})}
        m["widget"] = ("autocomplete" if name in (a.get("autocomplete_fields") or []) else
                       "filter_horizontal" if name in (a.get("filter_horizontal") or []) else "select")
    if k in ("file", "image") and f.get("allowed_extensions"):
        m["allowed_extensions"] = f["allowed_extensions"]
    if k == "decimal":
        m["max_digits"], m["decimal_places"] = f.get("max_digits"), f.get("decimal_places")
    return m


def is_view_only(label: str) -> bool:
    return not admin(label)["perms"]["change"]


def form_layout(c: Ctx, label: str, mode: str) -> dict:
    """Fieldsets + per-field metadata for the add or change form."""
    a = admin(label)
    fieldsets = a["fieldsets_add" if mode == "add" else "fieldsets_change"]
    ro = set(a.get("readonly_fields") or [])
    view_only = mode == "change" and is_view_only(label)
    sets, fields = [], {}
    for name, opts in fieldsets:
        sets.append({"name": name, "fields": opts["fields"], "classes": opts.get("classes", []),
                     "description": opts.get("description")})
        for fname in opts["fields"]:
            if label == "authentication.User" and fname in ("password", "usable_password", "password1", "password2"):
                fields[fname] = user_special_field(fname, mode)
                continue
            fields[fname] = field_meta(c, label, fname, readonly=view_only or fname in ro or
                                       (fname in MODELS[label]["fields"] and not MODELS[label]["fields"][fname]["editable"]))
    inlines = []
    for inl in a.get("inlines") or []:
        il = inl["model"]
        iro = set(inl["readonly_fields"])
        inlines.append({
            "label": il, "verbose_name": inl["verbose_name"], "verbose_name_plural": inl["verbose_name_plural"],
            "style": inl["style"], "fk": inl["fk"], "extra": inl["extra"],
            "fields": [field_meta(c, il, fn, readonly=view_only or fn in iro) for fn in inl["fields"] if fn != inl["fk"]],
        })
    return {"fieldsets": sets, "fields": fields, "inlines": inlines, "view_only": view_only}


def user_special_field(name: str, mode: str) -> dict:
    if name == "password":
        return {"name": "password", "label": "Password", "kind": "password_hash", "readonly": True, "required": False,
                "help_text": "Raw passwords are not stored, so there is no way to see the user’s password, "
                             "but you can change or unset the password using this form."}
    if name == "usable_password":
        return {"name": name, "label": "Password-based authentication", "kind": "usable_password", "readonly": False,
                "required": False,
                "help_text": "Whether the user will be able to authenticate using a password or not. If disabled, they "
                             "may still be able to authenticate using other backends, such as Single Sign-On or LDAP.",
                "choices": [["true", "Enabled"], ["false", "Disabled"]]}
    if name == "password1":
        return {"name": name, "label": "Password", "kind": "password", "readonly": False, "required": True,
                "help_text": "\n".join(PASSWORD_HELP)}
    return {"name": name, "label": "Password confirmation", "kind": "password", "readonly": False, "required": True,
            "help_text": "Enter the same password as before, for verification."}


PASSWORD_HELP = [
    "Your password can’t be too similar to your other personal information.",
    "Your password must contain at least 8 characters.",
    "Your password can’t be a commonly used password.",
    "Your password can’t be entirely numeric.",
]


def model_config(c: Ctx, label: str) -> dict:
    s, a = MODELS[label], admin(label)
    return {
        "label": label, "app": s["app_label"], "app_name": APPS.get(s["app_label"], s["app_label"]),
        "model": s["model_name"], "object_name": s["object_name"],
        "verbose_name": s["verbose_name"], "verbose_name_plural": s["verbose_name_plural"],
        "perms": a["perms"],
        "list_display": columns_for(label),
        "list_filter": a.get("list_filter") or [],
        "list_editable": a.get("list_editable") or [],
        "editable_fields": {n: field_meta(c, label, n, False) for n in a.get("list_editable") or []},
        "search_fields": a.get("search_fields") or [],
        "date_hierarchy": a.get("date_hierarchy"),
        "ordering": default_ordering(label),
        "readonly_fields": a.get("readonly_fields") or [],
        "autocomplete_fields": a.get("autocomplete_fields") or [],
        "actions": [{"name": n, "description": d.replace("%(verbose_name_plural)s", s["verbose_name_plural"])}
                    for n, d in a["actions"]],
        "add_form": form_layout(c, label, "add"),
        "change_form": form_layout(c, label, "change"),
        "extra_links": extra_links(label),
        "list_per_page": LIST_PER_PAGE,
    }


def extra_links(label: str) -> list[dict]:
    if label == "documents.DocumentVersion":
        return [{"route": "change_file", "label": "Change Document File"}]
    if label == "authentication.User":
        return [{"route": "password", "label": "Change password"}]
    return []


# =============================================================================== object (change form data)
def get_row(c: Ctx, label: str, pk_raw: Any) -> dict:
    pk = pk_to_db(label, pk_raw)
    row = c.fetch(label, pk)
    if row is not None and c.scope(label) and not c.db.execute(
            select(pkcol(label)).where(pkcol(label) == pk, *c.scope(label))).first():
        row = None  # belongs to another workspace than the one chosen in the top bar
    if row is None:
        raise HTTPException(404, f"{capfirst(MODELS[label]['verbose_name'])} with ID “{pk_raw}” doesn’t exist. "
                                 "Perhaps it was deleted?")
    return row


def password_summary(encoded: str | None) -> dict:
    """ReadOnlyPasswordHashWidget — never exposes the hash itself."""
    from app.core.security import has_usable_password
    if not encoded or not has_usable_password(encoded):
        return {"usable": False, "text": "No password set."}
    parts = encoded.split("$")
    if parts[0] == "pbkdf2_sha256" and len(parts) == 4:
        return {"usable": True, "items": [["algorithm", parts[0]], ["iterations", parts[1]],
                                          ["salt", parts[2][:6] + "*" * max(0, len(parts[2]) - 6)],
                                          ["hash", "*" * 10]]}
    return {"usable": True, "items": [["algorithm", parts[0]], ["hash", "*" * 10]]}


def field_value(c: Ctx, label: str, name: str, row: dict) -> Any:
    f = MODELS[label]["fields"][name]
    k = kind_of(f)
    if k == "m2m":
        return m2m_current(c, label, name, row)
    v = row.get(f["column"])
    if k == "fk":
        if v is None:
            return None
        rel = c.fetch(f["rel"], v)
        return {"value": json_value(MODELS[f["rel"]]["fields"][MODELS[f["rel"]]["pk"]], v),
                "label": c.str(f["rel"], rel) if rel else str(v)}
    if k in ("file", "image"):
        return {"name": v, "url": files_core.media_url(v)} if v else None
    return json_value(f, v)


def object_data(c: Ctx, label: str, row: dict) -> dict:
    layout = form_layout(c, label, "change")
    values, display = {}, {}
    for name, meta in layout["fields"].items():
        if meta["kind"] == "password_hash":
            display[name] = password_summary(row.get("password"))
            continue
        if meta["kind"] == "computed":
            display[name] = cell(c, label, name, row)
            continue
        values[name] = field_value(c, label, name, row)
        if meta["readonly"]:
            display[name] = cell(c, label, name, row)
    inlines = []
    pk = row[MODELS[label]["pk_column"]]
    for inl in admin(label).get("inlines") or []:
        il = inl["model"]
        it = table(il)
        fkcol = MODELS[il]["fields"][inl["fk"]]["column"]
        rows = [dict(r) for r in c.db.execute(select(it).where(it.c[fkcol] == pk).order_by(pkcol(il))).mappings().all()]
        out = []
        for r in rows:
            c.remember(il, r)
            item = {"pk": pk_to_str(il, r[MODELS[il]["pk_column"]]), "str": c.str(il, r), "values": {}, "display": {}}
            for fn in inl["fields"]:
                if fn == inl["fk"]:
                    continue
                item["values"][fn] = field_value(c, il, fn, r)
                if fn in inl["readonly_fields"]:
                    item["display"][fn] = cell(c, il, fn, r)
            out.append(item)
        inlines.append({"label": il, "rows": out})
    return {"pk": pk_to_str(label, pk), "str": c.str(label, row), "values": values, "display": display,
            "inlines": inlines}


def initial_data(c: Ctx, label: str) -> dict:
    """Initial values for the add form (model field defaults)."""
    layout = form_layout(c, label, "add")
    values = {}
    for name, meta in layout["fields"].items():
        if meta["kind"] in ("computed", "password", "password_hash"):
            continue
        if meta["kind"] == "usable_password":
            values[name] = "true"
            continue
        f = MODELS[label]["fields"][name]
        if "default" in f:
            d = f["default"]
            if isinstance(d, dict) and "callable" in d:
                fn = d["callable"]
                values[name] = (iso(utcnow()) if fn == "now" else "{}" if fn == "dict" else "[]" if fn == "list" else
                                str(uuid.uuid4()) if fn == "uuid4" else None)
            else:
                values[name] = json_value(f, d) if kind_of(f) != "json" else json.dumps(d)
        elif kind_of(f) == "m2m":
            values[name] = []
        elif kind_of(f) == "bool":
            values[name] = False
        else:
            values[name] = None
    return {"values": values}


# =============================================================================== cleaning / validation
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_RE = re.compile(r"^(?:http|ftp)s?://[^\s/$.?#].[^\s]*$", re.I)


class FormErrors(Exception):
    def __init__(self, errors: dict[str, list[str]], non_field: list[str] | None = None,
                 inline_errors: dict | None = None):
        super().__init__("invalid")
        self.errors, self.non_field, self.inline_errors = errors, non_field or [], inline_errors or {}


def raise_form_errors(e: FormErrors):
    n = sum(len(v) for v in e.errors.values()) + len(e.non_field) + sum(
        len(v) for rows in e.inline_errors.values() for r in rows.values() for v in r.values())
    raise HTTPException(400, {"message": "Please correct the error below." if n == 1 else "Please correct the errors below.",
                              "errors": e.errors, "non_field_errors": e.non_field, "inline_errors": e.inline_errors})


def clean_field(c: Ctx, label: str, name: str, raw: Any, tz) -> Any:
    """Return the DB column value (or raise ValueError(message))."""
    f = MODELS[label]["fields"][name]
    k = kind_of(f)
    required = not f.get("blank")
    if isinstance(raw, dict) and "value" in raw and k in ("fk", "choice"):
        raw = raw["value"]
    if k == "bool":
        return 1 if raw in (True, 1, "1", "true", "True", "on") else 0
    if k == "nullbool":
        if raw in (None, "", "unknown"):
            return None
        return 1 if raw in (True, 1, "1", "true", "True", "on") else 0
    if k == "m2m":
        ids = [x["value"] if isinstance(x, dict) else x for x in (raw or [])]
        if not ids and required:
            raise ValueError("This field is required.")
        target = f["rel"]
        pks = [pk_to_db(target, i) for i in ids]
        found = {r[0] for r in c.db.execute(select(pkcol(target)).where(pkcol(target).in_(pks))).all()} if pks else set()
        for p in pks:
            if p not in found:
                raise ValueError(f"Select a valid choice. {p} is not one of the available choices.")
        return pks
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if required and k not in ("json",):
            raise ValueError("This field is required.")
        if k == "json":
            if required:
                raise ValueError("This field is required.")
            return None
        if f["type"] in TEXTISH and not f.get("null"):
            return ""
        return None
    s = raw.strip() if isinstance(raw, str) else raw
    if k in ("char", "email", "url", "ip", "text", "choice") and f["type"] in TEXTISH:
        s = str(s)
        if k == "url" and "://" not in s:
            s = "http://" + s
        ml = f.get("max_length")
        if ml and len(s) > ml:
            raise ValueError(f"Ensure this value has at most {ml} characters (it has {len(s)}).")
        if k == "email" and not EMAIL_RE.match(s):
            raise ValueError("Enter a valid email address.")
        if k == "url" and not URL_RE.match(s):
            raise ValueError("Enter a valid URL.")
        if k == "ip":
            try:
                ipaddress.ip_address(s)
            except ValueError:
                raise ValueError("Enter a valid IPv4 or IPv6 address.")
        if f.get("choices") and s not in [str(v) for v, _ in f["choices"]]:
            raise ValueError(f"Select a valid choice. {s} is not one of the available choices.")
        return s
    if f["type"] in INT_TYPES:
        try:
            v = int(str(s))
        except ValueError:
            raise ValueError("Enter a whole number.")
        if f["type"].startswith("Positive") and v < 0:
            raise ValueError("Ensure this value is greater than or equal to 0.")
        if f.get("choices") and v not in [cv for cv, _ in f["choices"]]:
            raise ValueError(f"Select a valid choice. {v} is not one of the available choices.")
        return v
    if k == "float":
        try:
            return float(str(s))
        except ValueError:
            raise ValueError("Enter a number.")
    if k == "decimal":
        try:
            v = decimal.Decimal(str(s))
            if not v.is_finite():
                raise decimal.InvalidOperation
        except decimal.InvalidOperation:
            raise ValueError("Enter a number.")
        sign, digits, exp = v.as_tuple()
        dec = -exp if exp < 0 else 0
        whole = len(digits) - dec if len(digits) > dec else 0
        md, dp = f.get("max_digits"), f.get("decimal_places")
        if md is not None and len(digits) > md and whole + dec > md:
            raise ValueError(f"Ensure that there are no more than {md} digits in total.")
        if dp is not None and dec > dp:
            raise ValueError(f"Ensure that there are no more than {dp} decimal places.")
        if md is not None and dp is not None and whole > md - dp:
            raise ValueError(f"Ensure that there are no more than {md - dp} digits before the decimal point.")
        return v
    if k == "date":
        try:
            return datetime.date.fromisoformat(str(s)[:10])
        except ValueError:
            raise ValueError("Enter a valid date.")
    if k == "datetime":
        try:
            dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Enter a valid date/time.")
        return _to_utc_naive(dt, tz)
    if k == "json":
        if isinstance(s, (dict, list, int, float, bool)):
            return s
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            raise ValueError("Enter a valid JSON.")
    if k == "uuid":
        try:
            return uuid.UUID(str(s)).hex
        except ValueError:
            raise ValueError("Enter a valid UUID.")
    if k == "fk":
        target = f["rel"]
        try:
            pk = pk_to_db(target, s)
        except HTTPException:
            raise ValueError("Select a valid choice. That choice is not one of the available choices.")
        if c.fetch(target, pk) is None:
            raise ValueError("Select a valid choice. That choice is not one of the available choices.")
        return pk
    return s


def db_initial(label: str, name: str, row: dict | None, c: Ctx) -> Any:
    """Current DB value in the same shape clean_field returns (for has_changed)."""
    if row is None:
        return None
    f = MODELS[label]["fields"][name]
    k = kind_of(f)
    if k == "m2m":
        return [o["value"] for o in m2m_current(c, label, name, row)]
    v = row.get(f["column"])
    if k in ("bool", "nullbool"):
        return None if v is None else int(bool(v))
    if k == "float" and v is not None:
        return float(v)
    return v


def has_changed(label: str, name: str, old: Any, new: Any) -> bool:
    f = MODELS[label]["fields"][name]
    k = kind_of(f)
    if k == "m2m":
        return sorted(map(str, old or [])) != sorted(map(str, new or []))
    if k == "datetime":
        if old is None or new is None:
            return old != new
        return old.replace(microsecond=0) != new.replace(microsecond=0)
    if k == "decimal" and old is not None and new is not None:
        return decimal.Decimal(old) != decimal.Decimal(new)
    if k == "json":
        return old != new
    if old in (None, "") and new in (None, ""):
        return False
    if isinstance(old, str) and isinstance(new, str):
        return old.replace("\r\n", "\n") != new.replace("\r\n", "\n")
    return str(old) != str(new)


def check_unique(c: Ctx, label: str, merged: dict, form_fields: list[str], pk: Any, errors: dict, non_field: list):
    s = MODELS[label]
    t = table(label)
    for name in form_fields:
        f = s["fields"].get(name)
        if not f or not f.get("unique") or name in errors:
            continue
        v = merged.get(f["column"])
        if v in (None, ""):
            continue
        stmt = select(pkcol(label)).where(t.c[f["column"]] == v)
        if pk is not None:
            stmt = stmt.where(pkcol(label) != pk)
        if c.db.execute(stmt.limit(1)).first():
            errors.setdefault(name, []).append(
                f"{capfirst(s['verbose_name'])} with this {capfirst(f['verbose_name'])} already exists.")
    for group in s.get("unique_together") or []:
        if any(g not in form_fields or g in errors for g in group):
            continue
        conds = []
        for g in group:
            col = t.c[s["fields"][g]["column"]]
            v = merged.get(s["fields"][g]["column"])
            conds.append(col.is_(None) if v is None else col == v)
        stmt = select(pkcol(label)).where(*conds)
        if pk is not None:
            stmt = stmt.where(pkcol(label) != pk)
        if c.db.execute(stmt.limit(1)).first():
            labels = [capfirst(s["fields"][g]["verbose_name"]) for g in group]
            non_field.append(f"{capfirst(s['verbose_name'])} with this {text_list(labels)} already exists.")


def model_defaults(label: str) -> dict:
    """Column values a fresh model instance has (Field.get_default())."""
    out = {}
    for name, f in MODELS[label]["fields"].items():
        if "column" not in f or f.get("primary_key") and f["type"] in INT_TYPES:
            continue
        if f.get("auto_now") or f.get("auto_now_add"):
            out[f["column"]] = utcnow()
            continue
        if "default" in f:
            d = f["default"]
            if isinstance(d, dict) and "callable" in d:
                fn = d["callable"]
                out[f["column"]] = (utcnow() if fn == "now" else {} if fn == "dict" else [] if fn == "list" else
                                    uuid.uuid4().hex if fn == "uuid4" else None)
            else:
                out[f["column"]] = (1 if d else 0) if isinstance(d, bool) else d
        elif f["type"] in TEXTISH or f["type"] in FILE_TYPES:
            out[f["column"]] = None if f.get("null") else ""
        else:
            out[f["column"]] = None
    return out


def upload_dir(label: str, name: str, merged: dict, pk: Any) -> str:
    up = MODELS[label]["fields"][name].get("upload_to") or ""
    if up == "callable:document_upload_path":
        return files_core.document_upload_dir(pk)
    if up == "callable:reference_upload_path":
        return files_core.reference_upload_dir(pk)
    if up == "callable:reference_zip_upload_path":
        return files_core.reference_zip_upload_dir(merged.get("user_id"))
    return datetime.datetime.now().strftime(up)


def _image_ok(upload: UploadFile) -> bool:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return upload.filename.rsplit(".", 1)[-1].lower() in {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff", "ico"}
    try:
        upload.file.seek(0)
        Image.open(upload.file).verify()
        upload.file.seek(0)
        return True
    except Exception:  # noqa: BLE001
        return False


def clean_form(c: Ctx, label: str, field_names: list[str], data: dict, uploads: dict[str, UploadFile],
               clear: set[str], existing: dict | None, tz) -> tuple[dict, dict, dict, list[str], dict]:
    """Validate a model form. Returns (column_values, m2m_values, file_uploads, changed_labels, errors)."""
    s = MODELS[label]
    errors: dict[str, list[str]] = {}
    cols: dict[str, Any] = {}
    m2m: dict[str, list] = {}
    file_ups: dict[str, UploadFile | None] = {}
    changed: list[str] = []
    for name in field_names:
        f = s["fields"][name]
        k = kind_of(f)
        if k in ("file", "image"):
            up = uploads.get(name)
            current = existing.get(f["column"]) if existing else None
            if up is not None and name in clear:
                errors[name] = ["Please either submit a file or check the clear checkbox, not both."]
                continue
            if up is None:
                if name in clear:
                    if not f.get("blank"):
                        errors[name] = ["This field is required."]
                        continue
                    if current:
                        file_ups[name] = None
                        changed.append(capfirst(f["verbose_name"]))
                elif not current and not f.get("blank"):
                    errors[name] = ["This field is required."]
                continue
            ext = (up.filename or "").rsplit(".", 1)[-1].lower() if "." in (up.filename or "") else ""
            allowed = f.get("allowed_extensions")
            if allowed and ext not in allowed:
                errors[name] = [f"File extension “{ext}” is not allowed. Allowed extensions are: {', '.join(allowed)}."]
                continue
            if k == "image" and not _image_ok(up):
                errors[name] = ["Upload a valid image. The file you uploaded was either not an image or a corrupted image."]
                continue
            if len(up.filename or "") > (f.get("max_length") or 100) and False:
                pass
            file_ups[name] = up
            changed.append(capfirst(f["verbose_name"]))
            continue
        raw = data.get(name)
        try:
            v = clean_field(c, label, name, raw, tz)
        except ValueError as e:
            errors[name] = [str(e)]
            continue
        old = db_initial(label, name, existing, c) if existing is not None else None
        if existing is None:
            # Django's add form compares against the field's initial (model default)
            dflt = model_defaults(label).get(f.get("column", ""), None) if k != "m2m" else []
            if k in ("bool", "nullbool") and isinstance(dflt, bool):
                dflt = int(dflt)
            changed_now = has_changed(label, name, dflt, v)
        else:
            changed_now = has_changed(label, name, old, v)
        if k == "m2m":
            m2m[name] = v
        elif existing is None or changed_now:
            cols[f["column"]] = v
        if changed_now:
            changed.append(capfirst(f["verbose_name"]))
    return cols, m2m, file_ups, changed, errors


def json_col_value(label: str, colname: str, v: Any) -> Any:
    """Nullable JSON columns store SQL NULL for None (Django null=True semantics)."""
    t = table(label)
    col = t.c[colname]
    if v is None and col.type.__class__.__name__ == "JSON" and col.nullable:
        return null()
    return v


def write_row(c: Ctx, label: str, values: dict, pk: Any | None) -> Any:
    t = table(label)
    s = MODELS[label]
    values = {k: json_col_value(label, k, v) for k, v in values.items()}
    if pk is None:
        res = c.db.execute(insert(t).values(**values))
        if s["pk_column"] in values and values[s["pk_column"]] is not None:
            new_pk = values[s["pk_column"]]
        else:
            new_pk = res.inserted_primary_key[0]
        return new_pk
    if values:
        c.db.execute(update(t).where(pkcol(label) == pk).values(**values))
    return pk


def set_m2m(c: Ctx, label: str, name: str, pk: Any, ids: list) -> None:
    f = MODELS[label]["fields"][name]
    m = f["m2m"]
    through = Base.metadata.tables[m["through"]]
    cur = {r[0] for r in c.db.execute(select(through.c[m["dst"]]).where(through.c[m["src"]] == pk)).all()}
    new = set(ids)
    if cur - new:
        c.db.execute(delete(through).where(through.c[m["src"]] == pk, through.c[m["dst"]].in_(list(cur - new))))
    for i in new - cur:
        c.db.execute(insert(through).values(**{m["src"]: pk, m["dst"]: i}))


def touch_auto_now(label: str, values: dict) -> None:
    for f in MODELS[label]["fields"].values():
        if f.get("auto_now") and "column" in f:
            values[f["column"]] = utcnow()


def save_object(c: Ctx, label: str, pk_raw: Any | None, data: dict, uploads: dict[str, UploadFile],
                clear: set[str], inline_data: dict | None) -> dict:
    """ModelAdmin._changeform_view POST: validate form + inlines, save, write LogEntry."""
    s, a = MODELS[label], admin(label)
    is_add = pk_raw is None
    if is_add and not a["perms"]["add"]:
        raise HTTPException(403, "You do not have permission to add this object.")
    if not is_add and not a["perms"]["change"]:
        raise HTTPException(403, "You do not have permission to change this object.")
    tz = user_tz(c.user)
    existing = None if is_add else dict(get_row(c, label, pk_raw))
    pk = None if is_add else existing[s["pk_column"]]
    layout = form_layout(c, label, "add" if is_add else "change")
    names = [n for n, m in layout["fields"].items()
             if not m["readonly"] and m["kind"] not in ("computed", "password_hash", "password", "usable_password")]
    cols, m2m, file_ups, changed, errors = clean_form(c, label, names, data, uploads, clear, existing, tz)
    non_field: list[str] = []
    merged = {**model_defaults(label), **(existing or {}), **cols}
    if not errors:
        check_unique(c, label, merged, names, pk, errors, non_field)

    # ---- inline formsets
    inline_plan, inline_errors = [], {}
    for inl in a.get("inlines") or []:
        il = inl["model"]
        rows = (inline_data or {}).get(il) or []
        inames = [fn for fn in inl["fields"] if fn != inl["fk"] and fn not in inl["readonly_fields"]]
        errs_for = {}
        for idx, r in enumerate(rows):
            vals = r.get("values") or {}
            ipk = r.get("pk")
            iexisting = None
            if ipk not in (None, ""):
                iexisting = c.fetch(il, pk_to_db(il, ipk))
                fkc = MODELS[il]["fields"][inl["fk"]]["column"]
                if iexisting is None or (pk is not None and iexisting[fkc] != pk):
                    errs_for[str(idx)] = {"__all__": ["Select a valid choice. That choice is not one of the available choices."]}
                    continue
            if r.get("DELETE"):
                if iexisting is not None:
                    inline_plan.append(("delete", il, inl, iexisting, {}, []))
                continue
            if iexisting is None and not any(v not in (None, "", [], False) for v in vals.values()):
                continue  # empty extra form
            icols, _, _, ichanged, ierrs = clean_form(c, il, inames, vals, {}, set(), iexisting, tz)
            if not ierrs:
                imerged = {**model_defaults(il), **(iexisting or {}), **icols,
                           MODELS[il]["fields"][inl["fk"]]["column"]: pk if pk is not None else -1}
                infe: list[str] = []
                if pk is not None:
                    check_unique(c, il, imerged, inames + [inl["fk"]],
                                 iexisting[MODELS[il]["pk_column"]] if iexisting else None, ierrs, infe)
                if infe:
                    ierrs["__all__"] = infe
            if ierrs:
                errs_for[str(idx)] = ierrs
                continue
            inline_plan.append(("change" if iexisting is not None else "add", il, inl, iexisting, icols, ichanged))
        # duplicate rows within the formset (unique_together on the fk + another field)
        seen = set()
        for op, il2, inl2, iex, icols, _ in inline_plan:
            if il2 != il or op == "delete":
                continue
            key = tuple(sorted((k, str(v)) for k, v in {**(iex or {}), **icols}.items()
                               if k in {MODELS[il]["fields"][g]["column"] for grp in MODELS[il].get("unique_together") or []
                                        for g in grp if g != inl["fk"]}))
            if key and key in seen:
                errs_for.setdefault("__formset__", {}).setdefault("__all__", []).append(
                    "Please correct the duplicate data for "
                    + text_list([g for grp in MODELS[il].get("unique_together") or [] for g in grp]) + ", which must be unique.")
            seen.add(key)
        if errs_for:
            inline_errors[il] = errs_for

    if errors or non_field or inline_errors:
        raise_form_errors(FormErrors(errors, non_field, inline_errors))

    # ---- save
    values = dict(cols)
    if is_add:
        values = {**model_defaults(label), **cols}
    else:
        touch_auto_now(label, values)
    custom.before_save(c, label, values, is_add, existing)
    new_pk = write_row(c, label, values, pk)
    stored_files: dict[str, str] = {}
    for name, up in file_ups.items():
        col = s["fields"][name]["column"]
        if up is None:
            stored_files[col] = ""
        else:
            merged_now = {**merged, **values}
            stored_files[col] = files_core.save_upload(up, upload_dir(label, name, merged_now, None if is_add else new_pk))
    if stored_files:
        c.db.execute(update(table(label)).where(pkcol(label) == new_pk).values(**stored_files))
    for name, ids in m2m.items():
        set_m2m(c, label, name, new_pk, ids)

    messages_json: list[dict] = []
    if is_add:
        messages_json.append({"added": {}})
    elif changed:
        messages_json.append({"changed": {"fields": changed}})
    for op, il, inl, iex, icols, ichanged in inline_plan:
        fkc = MODELS[il]["fields"][inl["fk"]]["column"]
        if op == "delete":
            irepr = c.str(il, iex)
            ipk = iex[MODELS[il]["pk_column"]]
            run_delete(c, il, [ipk])
            messages_json.append({"deleted": {"name": MODELS[il]["verbose_name"], "object": irepr}})
            continue
        if op == "add":
            ivals = {**model_defaults(il), **icols, fkc: new_pk}
            custom.before_save(c, il, ivals, True, None)
            ipk = write_row(c, il, ivals, None)
            c._cache.pop((il, ipk), None)
            messages_json.append({"added": {"name": MODELS[il]["verbose_name"], "object": c.str(il, c.fetch(il, ipk))}})
        else:
            if not ichanged:
                continue
            ivals = dict(icols)
            touch_auto_now(il, ivals)
            ipk = iex[MODELS[il]["pk_column"]]
            write_row(c, il, ivals, ipk)
            c._cache.pop((il, ipk), None)
            messages_json.append({"changed": {"name": MODELS[il]["verbose_name"], "object": c.str(il, c.fetch(il, ipk)),
                                              "fields": ichanged}})
    c._cache.pop((label, new_pk), None)
    row = c.fetch(label, new_pk)
    obj_str = c.str(label, row)
    log_action(c, label, new_pk, obj_str, ADDITION if is_add else CHANGE, json.dumps(messages_json))
    c.db.commit()
    return {"pk": pk_to_str(label, new_pk), "str": obj_str, "changed": changed}


def save_message(label: str, obj_str: str, is_add: bool, then: str | None) -> str:
    name = MODELS[label]["verbose_name"]
    msg = f"The {name} “{obj_str}” was {'added' if is_add else 'changed'} successfully."
    if then == "continue":
        msg += " You may edit it again below."
    elif then == "addanother":
        msg += f" You may add another {name} below."
    return msg


# =============================================================================== list_editable
def list_edit(c: Ctx, label: str, rows: list[dict]) -> dict:
    a = admin(label)
    editable = a.get("list_editable") or []
    if not editable:
        raise HTTPException(400, "This model has no editable list columns.")
    tz = user_tz(c.user)
    plan, errors = [], {}
    for r in rows:
        pk = pk_to_db(label, r.get("pk"))
        existing = c.fetch(label, pk)
        if existing is None:
            continue
        cols, _, _, changed, errs = clean_form(c, label, editable, r.get("values") or {}, {}, set(), existing, tz)
        if errs:
            errors[pk_to_str(label, pk)] = errs
            continue
        if changed:
            plan.append((pk, cols, changed))
    if errors:
        raise HTTPException(400, {"message": "Please correct the errors below.", "row_errors": errors})
    for pk, cols, changed in plan:
        values = dict(cols)
        touch_auto_now(label, values)
        existing = c.fetch(label, pk)
        custom.before_save(c, label, values, False, existing)
        write_row(c, label, values, pk)
        c._cache.pop((label, pk), None)
        log_action(c, label, pk, c.str(label, c.fetch(label, pk)), CHANGE, json.dumps([{"changed": {"fields": changed}}]))
    c.db.commit()
    n = len(plan)
    s = MODELS[label]
    msg = (f"{n} {s['verbose_name']} was changed successfully." if n == 1 else
           f"{n} {s['verbose_name_plural']} were changed successfully.")
    return {"changed": n, "message": msg if n else None}


# =============================================================================== deletion
_CHILDREN: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
for _child, _col, _target, _tcol, _on in RELS:
    _CHILDREN[_target].append((_child, _col, _tcol, _on))


def _table_label(tname: str) -> str:
    return TABLES[tname]["label"]


class Collector:
    """django.db.models.deletion.Collector + admin NestedObjects for the delete confirmation page."""

    def __init__(self, c: Ctx, node_limit: int = 2000):
        self.c = c
        self.delete: dict[str, dict[Any, dict]] = defaultdict(dict)  # table -> pk -> row
        self.set_null: list[tuple[str, str, list]] = []
        self.protected: list[dict] = []
        self.node_limit = node_limit
        self.nodes = 0
        self.truncated = False

    def _node(self, tname: str, row: dict) -> dict:
        lab = _table_label(tname)
        pk = row[TABLES[tname]["pk_column"]]
        node: dict[str, Any] = {"model": capfirst(TABLES[tname]["verbose_name"]), "children": []}
        if lab in MODELS:
            self.c.remember(lab, row)
            node["str"] = self.c.str(lab, row)
            if lab in REG_SET:
                node["link"] = url_info(lab, pk)
        else:
            node["str"] = f"{TABLES[tname]['object_name']} object ({pk})"
        return node

    def collect(self, tname: str, rows: list[dict], parent_nodes: list[dict] | None) -> list[dict]:
        pkc = TABLES[tname]["pk_column"]
        new_rows, nodes = [], []
        for r in rows:
            pk = r[pkc]
            if pk in self.delete[tname]:
                continue
            self.delete[tname][pk] = r
            new_rows.append(r)
            if self.nodes < self.node_limit:
                n = self._node(tname, r)
                self.nodes += 1
                nodes.append((pk, n))
            else:
                self.truncated = True
                nodes.append((pk, None))
        node_by_pk = {pk: n for pk, n in nodes}
        if not new_rows:
            return []
        pks = [r[pkc] for r in new_rows]
        for child, col, tcol, on in _CHILDREN.get(tname, []):
            ct = Base.metadata.tables.get(child)
            if ct is None:
                continue
            keyvals = [r[tcol] for r in new_rows] if tcol != pkc else pks
            for i in range(0, len(keyvals), 500):
                chunk = keyvals[i:i + 500]
                crows = [dict(x) for x in self.c.db.execute(select(ct).where(ct.c[col].in_(chunk))).mappings().all()]
                if not crows:
                    continue
                if on == "CASCADE":
                    grouped: dict[Any, list[dict]] = defaultdict(list)
                    for cr in crows:
                        grouped[cr[col]].append(cr)
                    for parent_pk, group in grouped.items():
                        child_nodes = self.collect(child, group, None)
                        pn = node_by_pk.get(parent_pk)
                        if pn is not None:
                            pn["children"].extend(child_nodes)
                elif on == "SET_NULL":
                    self.set_null.append((child, col, chunk))
                elif on == "PROTECT":
                    for cr in crows:
                        lab = _table_label(child)
                        pkv = cr[TABLES[child]["pk_column"]]
                        self.protected.append({
                            "model": capfirst(TABLES[child]["verbose_name"]),
                            "str": self.c.str(lab, cr) if lab in MODELS else f"{TABLES[child]['object_name']} object ({pkv})",
                            **({"link": url_info(lab, pkv)} if lab in REG_SET else {}),
                        })
                # DO_NOTHING: ignored, exactly like Django
        return [n for _, n in nodes if n is not None]

    def counts(self) -> list[dict]:
        out = []
        for tname, rows in self.delete.items():
            if rows:
                out.append({"model": capfirst(TABLES[tname]["verbose_name_plural"]), "count": len(rows)})
        return out

    def ordered_tables(self) -> list[str]:
        """Children before parents (Kahn on the CASCADE edges among collected tables)."""
        tabs = [t for t, r in self.delete.items() if r]
        deps = {t: set() for t in tabs}  # t must be deleted before deps[t]
        for child, col, target, tcol, on in RELS:
            if child in deps and target in deps and child != target:
                deps[child].add(target)
        order, remaining = [], set(tabs)
        while remaining:
            ready = [t for t in remaining if not any(t in deps[o] for o in remaining if o != t)]
            if not ready:
                ready = list(remaining)
            for t in sorted(ready):
                order.append(t)
                remaining.discard(t)
        return order

    def execute(self) -> None:
        db = self.c.db
        for tname, col, keys in self.set_null:
            t = Base.metadata.tables[tname]
            db.execute(update(t).where(t.c[col].in_(keys)).values(**{col: None}))
        for tname in self.ordered_tables():
            t = Base.metadata.tables[tname]
            pkc = TABLES[tname]["pk_column"]
            pks = list(self.delete[tname].keys())
            for i in range(0, len(pks), 500):
                db.execute(delete(t).where(t.c[pkc].in_(pks[i:i + 500])))


def collect_for(c: Ctx, label: str, pks: list) -> Collector:
    col = Collector(c)
    tname = MODELS[label]["table"]
    rows = [dict(r) for r in c.db.execute(select(table(label)).where(pkcol(label).in_(pks))).mappings().all()]
    col.collect(tname, rows, None)
    return col


def delete_summary(c: Ctx, label: str, pks: list) -> dict:
    col = Collector(c)
    rows = [dict(r) for r in c.db.execute(select(table(label)).where(pkcol(label).in_(pks))).mappings().all()]
    roots = col.collect(MODELS[label]["table"], rows, None)
    return {
        "objects": roots,
        "counts": col.counts(),
        "protected": col.protected,
        "truncated": col.truncated,
        "verbose_name": MODELS[label]["verbose_name"],
        "verbose_name_plural": MODELS[label]["verbose_name_plural"],
    }


def run_delete(c: Ctx, label: str, pks: list) -> Collector:
    col = collect_for(c, label, pks)
    if col.protected:
        raise HTTPException(400, {"message": "Cannot delete because deleting would require deleting the following "
                                             "protected related objects.", "protected": col.protected})
    col.execute()
    return col


def delete_objects(c: Ctx, label: str, pks: list) -> list[str]:
    """Delete with LogEntry per selected object (ModelAdmin.delete_view / delete_selected)."""
    if not admin(label)["perms"]["delete"]:
        raise HTTPException(403, "You do not have permission to delete this object.")
    rows = [dict(r) for r in c.db.execute(select(table(label)).where(pkcol(label).in_(pks))).mappings().all()]
    reprs = []
    for r in rows:
        c.remember(label, r)
        reprs.append((r[MODELS[label]["pk_column"]], c.str(label, r)))
    run_delete(c, label, [p for p, _ in reprs])
    for pk, rep in reprs:
        log_action(c, label, pk, rep, DELETION, "")
    c.db.commit()
    return [rep for _, rep in reprs]


# =============================================================================== admin log
def content_type_id(c: Ctx, label: str) -> int:
    ct = Base.metadata.tables["django_content_type"]
    app, model = label.split(".")
    row = c.db.execute(select(ct.c.id).where(ct.c.app_label == app, ct.c.model == model.lower())).first()
    if row:
        return row[0]
    res = c.db.execute(insert(ct).values(app_label=app, model=model.lower()))  # ContentType.get_for_model creates
    return res.inserted_primary_key[0]


def log_action(c: Ctx, label: str, pk: Any, obj_repr: str, flag: int, message: str) -> None:
    t = Base.metadata.tables["django_admin_log"]
    c.db.execute(insert(t).values(
        action_time=utcnow(), user_id=c.user.id, content_type_id=content_type_id(c, label),
        object_id=pk_to_str(label, pk), object_repr=str(obj_repr)[:200], action_flag=flag, change_message=message))


def change_message_text(raw: str) -> str:
    """LogEntry.get_change_message()"""
    if raw and raw[0] == "[":
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        messages = []
        for sub in parsed:
            if "added" in sub:
                if sub["added"]:
                    messages.append(f"Added {sub['added']['name']} “{sub['added']['object']}”.")
                else:
                    messages.append("Added.")
            elif "changed" in sub:
                fields = text_list(sub["changed"].get("fields", []), "and")
                if "name" in sub["changed"]:
                    messages.append(f"Changed {fields} for {sub['changed']['name']} “{sub['changed']['object']}”.")
                else:
                    messages.append(f"Changed {fields}.")
            elif "deleted" in sub:
                messages.append(f"Deleted {sub['deleted']['name']} “{sub['deleted']['object']}”.")
        out = " ".join(m[0].upper() + m[1:] for m in messages)
        return out or "No fields changed."
    return raw


def _ct_label(c: Ctx, ct_id: int | None) -> tuple[str | None, str]:
    if ct_id is None:
        return None, ""
    ct = Base.metadata.tables["django_content_type"]
    row = c.db.execute(select(ct).where(ct.c.id == ct_id)).mappings().first()
    if not row:
        return None, ""
    for t in TABLES.values():
        app, obj = t["label"].split(".")
        if app == row["app_label"] and obj.lower() == row["model"]:
            return t["label"], t["verbose_name"]
    return None, row["model"]


def log_entry_json(c: Ctx, e: dict, users: dict[int, dict]) -> dict:
    lab, vname = _ct_label(c, e["content_type_id"])
    u = users.get(e["user_id"]) or {}
    full = f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip()
    link = None
    if e["action_flag"] != DELETION and lab in REG_SET and e["object_id"]:
        link = url_info(lab)
        link["pk"] = e["object_id"]
    return {
        "id": e["id"], "action_time": iso(e["action_time"]), "action_flag": e["action_flag"],
        "is_addition": e["action_flag"] == ADDITION, "is_change": e["action_flag"] == CHANGE,
        "is_deletion": e["action_flag"] == DELETION,
        "object_id": e["object_id"], "object_repr": e["object_repr"], "content_type": capfirst(vname) if vname else None,
        "change_message": change_message_text(e["change_message"]), "link": link,
        "user": {"id": e["user_id"], "username": u.get("username"), "full_name": full},
    }


def _users_map(c: Ctx, ids) -> dict[int, dict]:
    ut = Base.metadata.tables["authentication_user"]
    ids = list(set(ids))
    if not ids:
        return {}
    return {r["id"]: dict(r) for r in c.db.execute(
        select(ut.c.id, ut.c.username, ut.c.first_name, ut.c.last_name).where(ut.c.id.in_(ids))).mappings().all()}


def history(c: Ctx, label: str, pk_raw: Any) -> dict:
    row = get_row(c, label, pk_raw)
    t = Base.metadata.tables["django_admin_log"]
    pk_str = pk_to_str(label, row[MODELS[label]["pk_column"]])
    entries = [dict(e) for e in c.db.execute(
        select(t).where(t.c.object_id == pk_str, t.c.content_type_id == content_type_id(c, label))
        .order_by(t.c.action_time.asc())).mappings().all()]
    users = _users_map(c, [e["user_id"] for e in entries])
    return {"pk": pk_str, "str": c.str(label, row), "entries": [log_entry_json(c, e, users) for e in entries]}


def recent_actions(c: Ctx, limit: int = 10) -> list[dict]:
    t = Base.metadata.tables["django_admin_log"]
    entries = [dict(e) for e in c.db.execute(
        select(t).where(t.c.user_id == c.user.id).order_by(t.c.action_time.desc()).limit(limit)).mappings().all()]
    users = _users_map(c, [e["user_id"] for e in entries])
    return [log_entry_json(c, e, users) for e in entries]


# =============================================================================== index
def index(c: Ctx, with_counts: bool = True) -> dict:
    apps: dict[str, dict] = {}
    for label in REGISTERED:
        s = MODELS[label]
        a = s["admin"]
        app = apps.setdefault(s["app_label"], {"app_label": s["app_label"], "name": APPS.get(s["app_label"], s["app_label"]),
                                               "models": []})
        count = None
        if with_counts:
            count = c.db.execute(select(func.count()).select_from(table(label)).where(*c.scope(label))).scalar_one()
        app["models"].append({"label": label, "name": capfirst(s["verbose_name_plural"]), "object_name": s["object_name"],
                              "app": s["app_label"], "model": s["model_name"], "perms": a["perms"], "count": count,
                              "scope": "workspace" if ws_scope.is_workspace_table(s["table"]) else "platform"})
    out = sorted(apps.values(), key=lambda x: x["name"].lower())
    for app in out:
        app["models"].sort(key=lambda m: m["name"])
    return {"apps": out, "recent_actions": recent_actions(c)}


# =============================================================================== autocomplete
def autocomplete(c: Ctx, label: str, field: str, q: str, page: int, all_: bool) -> dict:
    f = MODELS[label]["fields"].get(field)
    if not f or kind_of(f) not in ("fk", "m2m"):
        # inline fields
        for inl in admin(label).get("inlines") or []:
            if field.startswith(inl["model"] + ":"):
                return autocomplete(c, inl["model"], field.split(":", 1)[1], q, page, all_) if inl["model"] in MODELS else {}
        raise HTTPException(404, "Not found")
    target = f["rel"]
    if all_:
        return {"results": related_options(c, target), "more": False}
    per = 20
    t = table(target)
    stmt = select(t).where(*c.scope(target))
    searchable = target in REG_SET and admin(target).get("search_fields")
    if target == "auth.Permission":
        ct = Base.metadata.tables["django_content_type"]
        stmt = stmt.join(ct, ct.c.id == t.c.content_type_id).order_by(ct.c.app_label, ct.c.model, t.c.codename)
        if q:
            stmt = stmt.where(or_(func.lower(t.c.name).like(f"%{_like_escape(q.lower())}%", escape="\\"),
                                  func.lower(t.c.codename).like(f"%{_like_escape(q.lower())}%", escape="\\")))
    else:
        stmt = stmt.order_by(*(_order_cols(target, default_ordering(target)) or [pkcol(target).asc()]))
        if q and searchable:
            stmt = stmt.where(search_condition(target, admin(target)["search_fields"], q))
    if q and not searchable and target != "auth.Permission":
        # No search_fields on the target admin → filter on __str__ (small lookup tables only)
        rows = [dict(r) for r in c.db.execute(stmt.limit(2000)).mappings().all()]
        res = []
        for r in rows:
            c.remember(target, r)
            s = c.str(target, r)
            if q.lower() in s.lower():
                res.append({"value": json_value(MODELS[target]["fields"][MODELS[target]["pk"]], r[MODELS[target]["pk_column"]]),
                            "label": s})
        start = (page - 1) * per
        return {"results": res[start:start + per], "more": len(res) > start + per}
    rows = [dict(r) for r in c.db.execute(stmt.limit(per + 1).offset((page - 1) * per)).mappings().all()]
    res = []
    for r in rows[:per]:
        c.remember(target, r)
        res.append({"value": json_value(MODELS[target]["fields"][MODELS[target]["pk"]], r[MODELS[target]["pk_column"]]),
                    "label": c.str(target, r)})
    return {"results": res, "more": len(rows) > per}
