"""ORM models.

`generated.py` is produced by sqlacodegen straight from the existing MySQL schema
(the tables Django created), so the FastAPI app reads and writes the very same
rows without any migration. Regenerate it with scripts/regenerate_models.sh if
the schema ever changes.

Friendly aliases below match the original Django model names, so code ported
from the Django views reads naturally (e.g. `Document`, `DocumentVersion`).
"""
import datetime

from sqlalchemy import event
from sqlalchemy.orm import Mapper

from app.models.generated import *  # noqa: F401,F403
from app.models.generated import (
    AuthenticationContactquery,
    AuthenticationLoginlog,
    AuthenticationOtpverification,
    AuthenticationPermission,
    AuthenticationRole,
    AuthenticationRolepermission,
    AuthenticationSmtpconfig,
    AuthenticationUser,
    AuthenticationUserconsent,
    AuthenticationUserpermission,
    AuthenticationUserrole,
    AuthenticationUsertype,
    Base,
    DocumentsAiconversation,
    DocumentsAidataset,
    DocumentsAimessage,
    DocumentsAnnotationactivity,
    DocumentsBrand,
    DocumentsCountry,
    DocumentsCoursecategory,
    DocumentsDocument,
    DocumentsDocumentannotation,
    DocumentsDocumentreference,
    DocumentsDocumentsharing,
    DocumentsDocumenttype,
    DocumentsDocumentversion,
    DocumentsDocumentversionreference,
    DocumentsDocumentversionsharing,
    DocumentsEmaillog,
    DocumentsEnrolluser,
    DocumentsFeedback,
    DocumentsJournal,
    DocumentsNotification,
    DocumentsProject,
    DocumentsProjectauthor,
    DocumentsProjectmilestone,
    DocumentsResearchproject,
    DocumentsResearchprojectcollaborator,
    DocumentsResearchprojectdocument,
    DocumentsResearchprojecttask,
    DocumentsSmtpsettings,
    DocumentsSupport,
    DocumentsTherapeuticarea,
    DocumentsUserjournalselection,
    LibraryAssignedreviewer,
    LibraryDocumenthistory,
    LibraryReferencedocument,
    LibraryReferencezip,
    LibraryTemporarypassword,
    PlagiarismPagesourcematch,
    PlagiarismPlagiarismcheck,
    PlagiarismPlagiarismfile,
    PlagiarismPlagiarismpagematch,
    PlagiarismPlagiarismresult,
    PlagiarismPlagiarismsource,
)

# ---- authentication app ----
User = AuthenticationUser
UserType = AuthenticationUsertype
Permission = AuthenticationPermission
Role = AuthenticationRole
RolePermission = AuthenticationRolepermission
UserRole = AuthenticationUserrole
UserPermission = AuthenticationUserpermission
OTPVerification = AuthenticationOtpverification
SMTPConfig = AuthenticationSmtpconfig
ContactQuery = AuthenticationContactquery
LoginLog = AuthenticationLoginlog
UserConsent = AuthenticationUserconsent

# ---- documents app ----
DocumentType = DocumentsDocumenttype
Brand = DocumentsBrand
Country = DocumentsCountry
TherapeuticArea = DocumentsTherapeuticarea
CourseCategory = DocumentsCoursecategory
Project = DocumentsProject
EnrollUser = DocumentsEnrolluser
Document = DocumentsDocument
DocumentVersion = DocumentsDocumentversion
DocumentFeedback = DocumentsFeedback
DocumentSupport = DocumentsSupport
DocumentNotification = DocumentsNotification
DocumentAnnotation = DocumentsDocumentannotation
AnnotationActivity = DocumentsAnnotationactivity
EmailLog = DocumentsEmaillog
SMTPSettings = DocumentsSmtpsettings
ResearchProject = DocumentsResearchproject
ResearchProjectCollaborator = DocumentsResearchprojectcollaborator
ResearchProjectTask = DocumentsResearchprojecttask
ResearchProjectDocument = DocumentsResearchprojectdocument
ProjectMilestone = DocumentsProjectmilestone
ProjectAuthor = DocumentsProjectauthor
Journal = DocumentsJournal
UserJournalSelection = DocumentsUserjournalselection
DocumentReference = DocumentsDocumentreference
DocumentVersionReference = DocumentsDocumentversionreference
DocumentSharing = DocumentsDocumentsharing
DocumentVersionSharing = DocumentsDocumentversionsharing
AIConversation = DocumentsAiconversation
AIMessage = DocumentsAimessage
AIDataset = DocumentsAidataset

# ---- library app ----
ReferenceDocument = LibraryReferencedocument
ReferenceZip = LibraryReferencezip
AssignedReviewer = LibraryAssignedreviewer
DocumentHistory = LibraryDocumenthistory
TemporaryPassword = LibraryTemporarypassword

# ---- plagiarism app ----
PlagiarismCheck = PlagiarismPlagiarismcheck
PlagiarismFile = PlagiarismPlagiarismfile
PlagiarismResult = PlagiarismPlagiarismresult
PlagiarismSource = PlagiarismPlagiarismsource
PlagiarismPageMatch = PlagiarismPlagiarismpagematch
PageSourceMatch = PlagiarismPagesourcematch

# Organisation workspaces (new tables, see scripts/organisations.sql)
from app.models.organisations import Organisation, OrgAssignment, OrgMembership  # noqa: E402,F401
from app.models.payments import PaymentGateway  # noqa: E402,F401
from app.models.rates import RateCardItem, RateService  # noqa: E402,F401
from app.models.billing import (  # noqa: E402,F401
    BillingApprover, BillingRequest, BillingRequestItem, BillingSettings, Invoice, InvoiceEvent, InvoiceLine,
    OrgBillingProfile,
)


def utcnow() -> datetime.datetime:
    """Naive UTC timestamp — Django (USE_TZ=True) stores UTC in MySQL DATETIME columns."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


# Django's auto_now_add / auto_now have no database default, so fill them here
# for every model, exactly like Django's pre_save did.
_AUTO_ADD_FIELDS = ("created_at", "uploaded_at", "granted_at", "assigned_at", "login_time",
                    "consent_timestamp", "date_joined", "generated_at", "joined_at", "linked_at",
                    "shared_at", "selected_at")
_AUTO_NOW_FIELDS = ("updated_at",)


@event.listens_for(Base, "before_insert", propagate=True)
def _fill_auto_add(mapper: Mapper, connection, target) -> None:
    now = utcnow()
    cols = mapper.columns.keys()
    for name in _AUTO_ADD_FIELDS + _AUTO_NOW_FIELDS:
        if name in cols and getattr(target, name, None) is None:
            setattr(target, name, now)


@event.listens_for(Base, "before_update", propagate=True)
def _touch_auto_now(mapper: Mapper, connection, target) -> None:
    cols = mapper.columns.keys()
    for name in _AUTO_NOW_FIELDS:
        if name in cols:
            setattr(target, name, utcnow())
