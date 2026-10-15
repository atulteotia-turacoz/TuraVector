"""Superadmin workspace scope for the generic (Core SQL) model admin.

The superadmin picks a workspace in the top bar (`X-Workspace` header). Models holding the data of
users — accounts, roles and permissions given to people, documents, references, mail… —
then show only the rows of that workspace's members. Platform models (roles, permission
definitions, user types, categories, SMTP, journals…) stay global, and so do the login logs,
privacy consents and OTP verifications, which the platform keeps as one audit trail.
"""
from sqlalchemy import and_, literal, or_, select

from app.core.tenancy import HOME_WORKSPACE_SLUG, WORKSPACE_KEY
from app.models import Base

# table -> column holding the user the row belongs to
OWNER_COLUMN: dict[str, str] = {
    "authentication_user": "id",
    "authentication_userrole": "user_id",
    "authentication_userpermission": "user_id",
    "documents_document": "user_id",
    "documents_documentversion": "user_id",
    "documents_documentannotation": "user_id",
    "documents_annotationactivity": "user_id",
    "documents_enrolluser": "user_id",
    "documents_feedback": "user_id",
    "documents_support": "user_id",
    "documents_notification": "receiver_id",
    "documents_emaillog": "recipient_user_id",
    "documents_userjournalselection": "user_id",
    "documents_documentsharing": "user_id",
    "documents_documentversionsharing": "user_id",
    "library_referencedocument": "user_id",
    "library_referencezip": "user_id",
    "library_documenthistory": "user_id",
    "library_temporarypassword": "user_id",
}
# rows owned through a parent row
VIA_PARENT = {
    # a review belongs to the workspace of the document under review (the reviewer may be Turacoz staff)
    "library_assignedreviewer": ("document_version_id", "documents_documentversion"),
    "documents_documentreference": ("document_id", "documents_document"),
    "documents_documentversionreference": ("document_version_id", "documents_documentversion"),
}



def _t(name: str):
    return Base.metadata.tables[name]


def is_workspace_table(table_name: str) -> bool:
    return table_name in OWNER_COLUMN or table_name in VIA_PARENT


def members(org_id: int):
    m = _t("org_membership")
    return select(m.c.user_id).where(m.c.organisation_id == org_id)


def people(org_id: int):
    """Members plus the Turacoz users assigned to the workspace — whose data counts as the workspace's."""
    a = _t("org_assignment")
    return members(org_id).union(select(a.c.user_id).where(a.c.organisation_id == org_id))


def _owned(column, org_id: int):
    """Owner is a member — or, in the home workspace (SMBT), a platform superuser."""
    cond = column.in_(people(org_id))
    m = _t("org_organisation")
    users = _t("authentication_user")
    home = select(m.c.id).where(m.c.slug == HOME_WORKSPACE_SLUG).scalar_subquery()
    return or_(cond, and_(literal(org_id) == home, column.in_(select(users.c.id).where(users.c.is_superuser == 1))))


def condition(table, org_id: int | None):
    """WHERE clause limiting `table` to the workspace, or None (no workspace chosen / platform table)."""
    if not org_id:
        return None
    name = table.name
    if name == "authentication_user":
        return table.c.id.in_(members(org_id))  # superusers are not members of any workspace
    if name in OWNER_COLUMN:
        return _owned(table.c[OWNER_COLUMN[name]], org_id)
    if name in VIA_PARENT:
        fk, parent_name = VIA_PARENT[name]
        parent = _t(parent_name)
        return table.c[fk].in_(select(parent.c.id).where(_owned(parent.c[OWNER_COLUMN[parent_name]], org_id)))
    return None


def workspace_of(db) -> int | None:
    """The workspace the superadmin is looking at in this request (set from the X-Workspace header)."""
    return db.info.get(WORKSPACE_KEY)
