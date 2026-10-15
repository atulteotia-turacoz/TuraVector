from typing import Optional
import datetime
import decimal

from sqlalchemy import BigInteger, Column, DECIMAL, Date, DateTime, Double, ForeignKeyConstraint, Index, Integer, JSON, String, Table, text
from sqlalchemy.dialects.mysql import CHAR, DATETIME, INTEGER, LONGTEXT, SMALLINT, TEXT, TINYINT, VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = 'admin'

    adminID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    user_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    password: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))


class AssignedReviewer(Base):
    __tablename__ = 'assigned_reviewer'

    reviewID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    versionID: Mapped[Optional[int]] = mapped_column(Integer)
    review_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    remark: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    created_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    modified_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


class AuthGroup(Base):
    __tablename__ = 'auth_group'
    __table_args__ = (
        Index('name', 'name', unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)

    auth_group_permissions: Mapped[list['AuthGroupPermissions']] = relationship('AuthGroupPermissions', back_populates='group')
    authentication_user_groups: Mapped[list['AuthenticationUserGroups']] = relationship('AuthenticationUserGroups', back_populates='group')


class AuthenticationContactquery(Base):
    __tablename__ = 'authentication_contactquery'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_resolved: Mapped[int] = mapped_column(TINYINT(1), nullable=False)


class AuthenticationOtpverification(Base):
    __tablename__ = 'authentication_otpverification'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    otp_code: Mapped[str] = mapped_column(String(6), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_used: Mapped[int] = mapped_column(TINYINT(1), nullable=False)


class AuthenticationPermission(Base):
    __tablename__ = 'authentication_permission'
    __table_args__ = (
        Index('authentication_permission_dashboard_module_action_c62fcf8a_uniq', 'dashboard', 'module', 'action', unique=True),
        Index('name', 'name', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dashboard: Mapped[str] = mapped_column(String(50), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    authentication_rolepermission: Mapped[list['AuthenticationRolepermission']] = relationship('AuthenticationRolepermission', back_populates='permission')
    authentication_userpermission: Mapped[list['AuthenticationUserpermission']] = relationship('AuthenticationUserpermission', back_populates='permission')


class AuthenticationRole(Base):
    __tablename__ = 'authentication_role'
    __table_args__ = (
        Index('name', 'name', unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    is_system_role: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    authentication_rolepermission: Mapped[list['AuthenticationRolepermission']] = relationship('AuthenticationRolepermission', back_populates='role')
    authentication_userrole: Mapped[list['AuthenticationUserrole']] = relationship('AuthenticationUserrole', back_populates='role')
    documents_documentsharing: Mapped[list['DocumentsDocumentsharing']] = relationship('DocumentsDocumentsharing', back_populates='role_required')


class AuthenticationSmtpconfig(Base):
    __tablename__ = 'authentication_smtpconfig'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    encryption: Mapped[str] = mapped_column(String(10), nullable=False)
    from_email: Mapped[str] = mapped_column(String(254), nullable=False)
    from_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class AuthenticationUsertype(Base):
    __tablename__ = 'authentication_usertype'
    __table_args__ = (
        Index('code', 'code', unique=True),
        Index('name', 'name', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    is_system: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    authentication_user: Mapped[list['AuthenticationUser']] = relationship('AuthenticationUser', back_populates='user_type_new')


class Brand(Base):
    __tablename__ = 'brand'
    __table_args__ = (
        Index('brand_name', 'brand_name', unique=True),
    )

    brandID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_name: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    code_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class Country(Base):
    __tablename__ = 'country'
    __table_args__ = (
        Index('country_name', 'country_name', unique=True),
    )

    country_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    country_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    code_name: Mapped[Optional[str]] = mapped_column(VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))


class CourseCategory(Base):
    __tablename__ = 'course_category'
    __table_args__ = (
        Index('category_name', 'category_name', unique=True),
    )

    categoryID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_name: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    code_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))


class CourseDuration(Base):
    __tablename__ = 'course_duration'

    durationID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    duration: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'), server_default=text("'UINQUE'"))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))


class DjangoContentType(Base):
    __tablename__ = 'django_content_type'
    __table_args__ = (
        Index('django_content_type_app_label_model_76bd3d3b_uniq', 'app_label', 'model', unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_label: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    auth_permission: Mapped[list['AuthPermission']] = relationship('AuthPermission', back_populates='content_type')
    django_admin_log: Mapped[list['DjangoAdminLog']] = relationship('DjangoAdminLog', back_populates='content_type')


class DjangoMigrations(Base):
    __tablename__ = 'django_migrations'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    applied: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DjangoSession(Base):
    __tablename__ = 'django_session'
    __table_args__ = (
        Index('django_session_expire_date_a5c62663', 'expire_date'),
    )

    session_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_data: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    expire_date: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DocumentType(Base):
    __tablename__ = 'document_type'
    __table_args__ = (
        Index('document_name', 'document_name', unique=True),
    )

    docID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    document_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class DocumentsBrand(Base):
    __tablename__ = 'documents_brand'
    __table_args__ = (
        Index('code_name', 'code_name', unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code_name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    documents_document: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='brand')


class DocumentsCountry(Base):
    __tablename__ = 'documents_country'
    __table_args__ = (
        Index('documents_country_name_d4c37f43_uniq', 'name', unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code_name: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    documents_document: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='country')
    library_referencedocument: Mapped[list['LibraryReferencedocument']] = relationship('LibraryReferencedocument', back_populates='country')


class DocumentsCoursecategory(Base):
    __tablename__ = 'documents_coursecategory'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    documents_document: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='course')
    documents_enrolluser: Mapped[list['DocumentsEnrolluser']] = relationship('DocumentsEnrolluser', back_populates='course')


class DocumentsDocumenttype(Base):
    __tablename__ = 'documents_documenttype'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    documents_document: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='document_type')


class DocumentsProject(Base):
    __tablename__ = 'documents_project'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    documents_document: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='project')
    documents_enrolluser: Mapped[list['DocumentsEnrolluser']] = relationship('DocumentsEnrolluser', back_populates='project')
    documents_feedback: Mapped[list['DocumentsFeedback']] = relationship('DocumentsFeedback', back_populates='project')


class DocumentsTherapeuticarea(Base):
    __tablename__ = 'documents_therapeuticarea'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    documents_document: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='therapeutic_area')
    library_referencedocument: Mapped[list['LibraryReferencedocument']] = relationship('LibraryReferencedocument', back_populates='therapeutic_area')


class EnrollUsers(Base):
    __tablename__ = 'enroll_users'

    enrolmentID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    course_start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    course_end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    user: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    assign_role: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'1'"))
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    enrolment_duration: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    projectID: Mapped[Optional[int]] = mapped_column(Integer)
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class Feedback(Base):
    __tablename__ = 'feedback'

    feedbackID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    projectID: Mapped[Optional[int]] = mapped_column(Integer)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    feedback_rating: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    created_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    modified_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


class Notification(Base):
    __tablename__ = 'notification'

    noti_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    noti_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'0'"))
    receiver: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_for: Mapped[str] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    doctype: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    docid: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(TEXT(charset='utf8mb3', collation='utf8mb3_general_ci'))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    created_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    modified_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


t_otp_verification = Table(
    'otp_verification', Base.metadata,
    Column('otp_id', Integer, nullable=False),
    Column('userid', Integer),
    Column('email', VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci')),
    Column('otp', VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci')),
    Column('validate_status', Integer, server_default=text("'0'")),
    Column('creation', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Column('modified', DateTime, server_default=text('CURRENT_TIMESTAMP'))
)


class Projects(Base):
    __tablename__ = 'projects'

    projectID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    project_status: Mapped[str] = mapped_column(VARCHAR(200, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False, server_default=text("'Draft'"))
    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'1'"))
    course_category: Mapped[Optional[int]] = mapped_column(Integer)
    file_name: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))


class Queries(Base):
    __tablename__ = 'queries'

    queryID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    subject: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    message: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class SmtpConfig(Base):
    __tablename__ = 'smtp_config'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_email: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    display_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    protocol: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    smtp_host: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    smtp_user: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    smtp_pass: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    smtp_crypto: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    smtp_port: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    mailtype: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    charset: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    encoding: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    crlf: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    newline: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    wordwrap: Mapped[Optional[str]] = mapped_column(VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci'), server_default=text("'TRUE'"))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))


class Support(Base):
    __tablename__ = 'support'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    email_id: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    message: Mapped[Optional[str]] = mapped_column(LONGTEXT(charset='utf8mb3', collation='utf8mb3_general_ci'))
    seen_status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"))


class TherapeuticArea(Base):
    __tablename__ = 'therapeutic_area'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    therapeutic_area: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    created_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    modified_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


class Upload(Base):
    __tablename__ = 'upload'

    docID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_number: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    course: Mapped[int] = mapped_column(Integer, nullable=False)
    projectID: Mapped[int] = mapped_column(Integer, nullable=False)
    document_type: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    country: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    brand: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'1'"), comment='1-Draft\r\n2-Ongoing\r\n3-Completed')
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    userid: Mapped[int] = mapped_column(Integer, nullable=False)
    document_name: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    therapeutic_area: Mapped[Optional[int]] = mapped_column(Integer)
    file_name: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    ext: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    file_title_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


class UploadReference(Base):
    __tablename__ = 'upload_reference'

    reference_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    name_of_document: Mapped[str] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    userid: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'1'"))
    reference_number: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    subtype: Mapped[Optional[int]] = mapped_column(Integer)
    country: Mapped[Optional[int]] = mapped_column(Integer)
    brand: Mapped[Optional[int]] = mapped_column(Integer)
    therapeutic_area: Mapped[Optional[int]] = mapped_column(Integer)
    ref_number: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    ref_year: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    file_name: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    ext: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    file_title_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


class UploadReferencesZip(Base):
    __tablename__ = 'upload_references_zip'

    ref_zip_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    userid: Mapped[Optional[int]] = mapped_column(Integer)
    ref_zip_no: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    versionID: Mapped[Optional[int]] = mapped_column(Integer)
    version_no: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    file_name: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    ext: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    created_by: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    modified_by: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))
    file_title_name: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb3', collation='utf8mb3_general_ci'))


class UploadVersion(Base):
    __tablename__ = 'upload_version'
    __table_args__ = (
        Index('version_number', 'version_number', unique=True),
    )

    versionID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_number: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    version_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'1'"))
    docID: Mapped[int] = mapped_column(Integer, nullable=False)
    document_number: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    stage_status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'0'"))
    new_stage_status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'1'"), comment='1-Draft\r\n2-Draft Under Construction\r\n3-Draft Under Review\r\n4-Addressing Review Comments\r\n5-Finalised')
    created_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    modified_by: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False)
    userid: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    ext: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    file_title_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


class Users(Base):
    __tablename__ = 'users'

    userID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False, server_default=text("'UNIQUE'"))
    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    modified: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    admin: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'0'"))
    user_type: Mapped[str] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'), nullable=False, server_default=text("'Normal'"))
    is_manager: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("'0'"))
    user_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    password: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    first_name: Mapped[Optional[str]] = mapped_column(VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci'))
    last_name: Mapped[Optional[str]] = mapped_column(VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci'))
    phone: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    email_display: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    city: Mapped[Optional[str]] = mapped_column(VARCHAR(250, charset='utf8mb3', collation='utf8mb3_general_ci'))
    country: Mapped[Optional[str]] = mapped_column(VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci'))
    address: Mapped[Optional[str]] = mapped_column(TEXT(charset='utf8mb3', collation='utf8mb3_general_ci'))
    preferred_language: Mapped[Optional[str]] = mapped_column(VARCHAR(150, charset='utf8mb3', collation='utf8mb3_general_ci'))
    description: Mapped[Optional[str]] = mapped_column(TEXT(charset='utf8mb3', collation='utf8mb3_general_ci'))
    status: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'1'"))
    created_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))
    modified_by: Mapped[Optional[str]] = mapped_column(VARCHAR(300, charset='utf8mb3', collation='utf8mb3_general_ci'))


class AuthPermission(Base):
    __tablename__ = 'auth_permission'
    __table_args__ = (
        ForeignKeyConstraint(['content_type_id'], ['django_content_type.id'], name='auth_permission_content_type_id_2f476e4b_fk_django_co'),
        Index('auth_permission_content_type_id_codename_01ab375a_uniq', 'content_type_id', 'codename', unique=True)
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type_id: Mapped[int] = mapped_column(Integer, nullable=False)
    codename: Mapped[str] = mapped_column(String(100), nullable=False)

    content_type: Mapped['DjangoContentType'] = relationship('DjangoContentType', back_populates='auth_permission')
    auth_group_permissions: Mapped[list['AuthGroupPermissions']] = relationship('AuthGroupPermissions', back_populates='permission')
    authentication_user_user_permissions: Mapped[list['AuthenticationUserUserPermissions']] = relationship('AuthenticationUserUserPermissions', back_populates='permission')


class AuthenticationUser(Base):
    __tablename__ = 'authentication_user'
    __table_args__ = (
        ForeignKeyConstraint(['user_type_new_id'], ['authentication_usertype.id'], name='authentication_user_user_type_new_id_dd9d82c4_fk_authentic'),
        Index('authentication_user_user_type_new_id_dd9d82c4_fk_authentic', 'user_type_new_id'),
        Index('email', 'email', unique=True),
        Index('username', 'username', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_superuser: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    is_staff: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    date_joined: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    user_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_manager: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    last_login: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    address: Mapped[Optional[str]] = mapped_column(LONGTEXT)
    user_type_new_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    user_type_new: Mapped[Optional['AuthenticationUsertype']] = relationship('AuthenticationUsertype', back_populates='authentication_user')
    authentication_loginlog: Mapped[list['AuthenticationLoginlog']] = relationship('AuthenticationLoginlog', back_populates='user')
    authentication_rolepermission: Mapped[list['AuthenticationRolepermission']] = relationship('AuthenticationRolepermission', back_populates='granted_by')
    authentication_user_groups: Mapped[list['AuthenticationUserGroups']] = relationship('AuthenticationUserGroups', back_populates='user')
    authentication_user_user_permissions: Mapped[list['AuthenticationUserUserPermissions']] = relationship('AuthenticationUserUserPermissions', back_populates='user')
    authentication_userconsent: Mapped[list['AuthenticationUserconsent']] = relationship('AuthenticationUserconsent', back_populates='user')
    authentication_userpermission_granted_by: Mapped[list['AuthenticationUserpermission']] = relationship('AuthenticationUserpermission', foreign_keys='[AuthenticationUserpermission.granted_by_id]', back_populates='granted_by')
    authentication_userpermission_user: Mapped[list['AuthenticationUserpermission']] = relationship('AuthenticationUserpermission', foreign_keys='[AuthenticationUserpermission.user_id]', back_populates='user')
    authentication_userrole_assigned_by: Mapped[list['AuthenticationUserrole']] = relationship('AuthenticationUserrole', foreign_keys='[AuthenticationUserrole.assigned_by_id]', back_populates='assigned_by')
    authentication_userrole_user: Mapped[list['AuthenticationUserrole']] = relationship('AuthenticationUserrole', foreign_keys='[AuthenticationUserrole.user_id]', back_populates='user')
    django_admin_log: Mapped[list['DjangoAdminLog']] = relationship('DjangoAdminLog', back_populates='user')
    documents_aiconversation: Mapped[list['DocumentsAiconversation']] = relationship('DocumentsAiconversation', back_populates='user')
    documents_document_created_by: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', foreign_keys='[DocumentsDocument.created_by_id]', back_populates='created_by')
    documents_document_modified_by: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', foreign_keys='[DocumentsDocument.modified_by_id]', back_populates='modified_by')
    documents_document_user: Mapped[list['DocumentsDocument']] = relationship('DocumentsDocument', foreign_keys='[DocumentsDocument.user_id]', back_populates='user')
    documents_enrolluser: Mapped[list['DocumentsEnrolluser']] = relationship('DocumentsEnrolluser', back_populates='user')
    documents_feedback: Mapped[list['DocumentsFeedback']] = relationship('DocumentsFeedback', back_populates='user')
    documents_journal: Mapped[list['DocumentsJournal']] = relationship('DocumentsJournal', back_populates='created_by')
    documents_notification_receiver: Mapped[list['DocumentsNotification']] = relationship('DocumentsNotification', foreign_keys='[DocumentsNotification.receiver_id]', back_populates='receiver')
    documents_notification_sender: Mapped[list['DocumentsNotification']] = relationship('DocumentsNotification', foreign_keys='[DocumentsNotification.sender_id]', back_populates='sender')
    documents_researchproject: Mapped[list['DocumentsResearchproject']] = relationship('DocumentsResearchproject', back_populates='owner')
    documents_smtpsettings_created_by: Mapped[list['DocumentsSmtpsettings']] = relationship('DocumentsSmtpsettings', foreign_keys='[DocumentsSmtpsettings.created_by_id]', back_populates='created_by')
    documents_smtpsettings_updated_by: Mapped[list['DocumentsSmtpsettings']] = relationship('DocumentsSmtpsettings', foreign_keys='[DocumentsSmtpsettings.updated_by_id]', back_populates='updated_by')
    documents_support: Mapped[list['DocumentsSupport']] = relationship('DocumentsSupport', back_populates='user')
    library_referencedocument_created_by: Mapped[list['LibraryReferencedocument']] = relationship('LibraryReferencedocument', foreign_keys='[LibraryReferencedocument.created_by_id]', back_populates='created_by')
    library_referencedocument_modified_by: Mapped[list['LibraryReferencedocument']] = relationship('LibraryReferencedocument', foreign_keys='[LibraryReferencedocument.modified_by_id]', back_populates='modified_by')
    library_referencedocument_user: Mapped[list['LibraryReferencedocument']] = relationship('LibraryReferencedocument', foreign_keys='[LibraryReferencedocument.user_id]', back_populates='user')
    library_temporarypassword: Mapped[list['LibraryTemporarypassword']] = relationship('LibraryTemporarypassword', back_populates='user')
    plagiarism_plagiarismcheck: Mapped[list['PlagiarismPlagiarismcheck']] = relationship('PlagiarismPlagiarismcheck', back_populates='user')
    documents_documentreference: Mapped[list['DocumentsDocumentreference']] = relationship('DocumentsDocumentreference', back_populates='linked_by')
    documents_documentversion_created_by: Mapped[list['DocumentsDocumentversion']] = relationship('DocumentsDocumentversion', foreign_keys='[DocumentsDocumentversion.created_by_id]', back_populates='created_by')
    documents_documentversion_modified_by: Mapped[list['DocumentsDocumentversion']] = relationship('DocumentsDocumentversion', foreign_keys='[DocumentsDocumentversion.modified_by_id]', back_populates='modified_by')
    documents_documentversion_user: Mapped[list['DocumentsDocumentversion']] = relationship('DocumentsDocumentversion', foreign_keys='[DocumentsDocumentversion.user_id]', back_populates='user')
    documents_projectmilestone: Mapped[list['DocumentsProjectmilestone']] = relationship('DocumentsProjectmilestone', back_populates='created_by')
    documents_researchprojectcollaborator: Mapped[list['DocumentsResearchprojectcollaborator']] = relationship('DocumentsResearchprojectcollaborator', back_populates='user')
    documents_researchprojectdocument: Mapped[list['DocumentsResearchprojectdocument']] = relationship('DocumentsResearchprojectdocument', back_populates='uploaded_by')
    documents_researchprojecttask: Mapped[list['DocumentsResearchprojecttask']] = relationship('DocumentsResearchprojecttask', back_populates='assigned_to')
    documents_userjournalselection: Mapped[list['DocumentsUserjournalselection']] = relationship('DocumentsUserjournalselection', back_populates='user')
    documents_annotationactivity: Mapped[list['DocumentsAnnotationactivity']] = relationship('DocumentsAnnotationactivity', back_populates='user')
    documents_documentannotation: Mapped[list['DocumentsDocumentannotation']] = relationship('DocumentsDocumentannotation', back_populates='user')
    documents_documentsharing_shared_by: Mapped[list['DocumentsDocumentsharing']] = relationship('DocumentsDocumentsharing', foreign_keys='[DocumentsDocumentsharing.shared_by_id]', back_populates='shared_by')
    documents_documentsharing_user: Mapped[list['DocumentsDocumentsharing']] = relationship('DocumentsDocumentsharing', foreign_keys='[DocumentsDocumentsharing.user_id]', back_populates='user')
    documents_documentversionreference: Mapped[list['DocumentsDocumentversionreference']] = relationship('DocumentsDocumentversionreference', back_populates='linked_by')
    documents_documentversionsharing_shared_by: Mapped[list['DocumentsDocumentversionsharing']] = relationship('DocumentsDocumentversionsharing', foreign_keys='[DocumentsDocumentversionsharing.shared_by_id]', back_populates='shared_by')
    documents_documentversionsharing_user: Mapped[list['DocumentsDocumentversionsharing']] = relationship('DocumentsDocumentversionsharing', foreign_keys='[DocumentsDocumentversionsharing.user_id]', back_populates='user')
    documents_emaillog_recipient_user: Mapped[list['DocumentsEmaillog']] = relationship('DocumentsEmaillog', foreign_keys='[DocumentsEmaillog.recipient_user_id]', back_populates='recipient_user')
    documents_emaillog_sender_user: Mapped[list['DocumentsEmaillog']] = relationship('DocumentsEmaillog', foreign_keys='[DocumentsEmaillog.sender_user_id]', back_populates='sender_user')
    library_assignedreviewer_created_by: Mapped[list['LibraryAssignedreviewer']] = relationship('LibraryAssignedreviewer', foreign_keys='[LibraryAssignedreviewer.created_by_id]', back_populates='created_by')
    library_assignedreviewer_modified_by: Mapped[list['LibraryAssignedreviewer']] = relationship('LibraryAssignedreviewer', foreign_keys='[LibraryAssignedreviewer.modified_by_id]', back_populates='modified_by')
    library_assignedreviewer_user: Mapped[list['LibraryAssignedreviewer']] = relationship('LibraryAssignedreviewer', foreign_keys='[LibraryAssignedreviewer.user_id]', back_populates='user')
    library_documenthistory: Mapped[list['LibraryDocumenthistory']] = relationship('LibraryDocumenthistory', back_populates='user')
    library_referencezip_created_by: Mapped[list['LibraryReferencezip']] = relationship('LibraryReferencezip', foreign_keys='[LibraryReferencezip.created_by_id]', back_populates='created_by')
    library_referencezip_modified_by: Mapped[list['LibraryReferencezip']] = relationship('LibraryReferencezip', foreign_keys='[LibraryReferencezip.modified_by_id]', back_populates='modified_by')
    library_referencezip_user: Mapped[list['LibraryReferencezip']] = relationship('LibraryReferencezip', foreign_keys='[LibraryReferencezip.user_id]', back_populates='user')


class AuthGroupPermissions(Base):
    __tablename__ = 'auth_group_permissions'
    __table_args__ = (
        ForeignKeyConstraint(['group_id'], ['auth_group.id'], name='auth_group_permissions_group_id_b120cbf9_fk_auth_group_id'),
        ForeignKeyConstraint(['permission_id'], ['auth_permission.id'], name='auth_group_permissio_permission_id_84c5c92e_fk_auth_perm'),
        Index('auth_group_permissio_permission_id_84c5c92e_fk_auth_perm', 'permission_id'),
        Index('auth_group_permissions_group_id_permission_id_0cd325b0_uniq', 'group_id', 'permission_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    permission_id: Mapped[int] = mapped_column(Integer, nullable=False)

    group: Mapped['AuthGroup'] = relationship('AuthGroup', back_populates='auth_group_permissions')
    permission: Mapped['AuthPermission'] = relationship('AuthPermission', back_populates='auth_group_permissions')


class AuthenticationLoginlog(Base):
    __tablename__ = 'authentication_loginlog'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='authentication_login_user_id_b3bba532_fk_authentic'),
        Index('authenticat_ip_addr_bc4875_idx', 'ip_address', 'login_time'),
        Index('authenticat_status_d84005_idx', 'status', 'login_time'),
        Index('authenticat_user_id_d0e797_idx', 'user_id', 'login_time')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username_attempted: Mapped[str] = mapped_column(VARCHAR(150, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    ip_address: Mapped[str] = mapped_column(CHAR(39, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    user_agent: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    failure_reason: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    login_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    location_info: Mapped[object] = mapped_column(JSON, nullable=False)
    device_info: Mapped[object] = mapped_column(JSON, nullable=False)
    email_attempted: Mapped[Optional[str]] = mapped_column(VARCHAR(254, charset='utf8mb4', collation='utf8mb4_general_ci'))
    session_key: Mapped[Optional[str]] = mapped_column(VARCHAR(40, charset='utf8mb4', collation='utf8mb4_general_ci'))
    logout_time: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    user: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', back_populates='authentication_loginlog')


class AuthenticationRolepermission(Base):
    __tablename__ = 'authentication_rolepermission'
    __table_args__ = (
        ForeignKeyConstraint(['granted_by_id'], ['authentication_user.id'], name='authentication_rolep_granted_by_id_99033264_fk_authentic'),
        ForeignKeyConstraint(['permission_id'], ['authentication_permission.id'], name='authentication_rolep_permission_id_b453cbda_fk_authentic'),
        ForeignKeyConstraint(['role_id'], ['authentication_role.id'], name='authentication_rolep_role_id_93bf005a_fk_authentic'),
        Index('authentication_rolep_granted_by_id_99033264_fk_authentic', 'granted_by_id'),
        Index('authentication_rolep_permission_id_b453cbda_fk_authentic', 'permission_id'),
        Index('authentication_rolepermi_role_id_permission_id_54443e60_uniq', 'role_id', 'permission_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    granted_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    permission_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    granted_by_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    granted_by: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', back_populates='authentication_rolepermission')
    permission: Mapped['AuthenticationPermission'] = relationship('AuthenticationPermission', back_populates='authentication_rolepermission')
    role: Mapped['AuthenticationRole'] = relationship('AuthenticationRole', back_populates='authentication_rolepermission')


class AuthenticationUserGroups(Base):
    __tablename__ = 'authentication_user_groups'
    __table_args__ = (
        ForeignKeyConstraint(['group_id'], ['auth_group.id'], name='authentication_user_groups_group_id_6b5c44b7_fk_auth_group_id'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='authentication_user__user_id_30868577_fk_authentic'),
        Index('authentication_user_groups_group_id_6b5c44b7_fk_auth_group_id', 'group_id'),
        Index('authentication_user_groups_user_id_group_id_8af031ac_uniq', 'user_id', 'group_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False)

    group: Mapped['AuthGroup'] = relationship('AuthGroup', back_populates='authentication_user_groups')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='authentication_user_groups')


class AuthenticationUserUserPermissions(Base):
    __tablename__ = 'authentication_user_user_permissions'
    __table_args__ = (
        ForeignKeyConstraint(['permission_id'], ['auth_permission.id'], name='authentication_user__permission_id_ea6be19a_fk_auth_perm'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='authentication_user__user_id_736ebf7e_fk_authentic'),
        Index('authentication_user__permission_id_ea6be19a_fk_auth_perm', 'permission_id'),
        Index('authentication_user_user_user_id_permission_id_ec51b09f_uniq', 'user_id', 'permission_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    permission_id: Mapped[int] = mapped_column(Integer, nullable=False)

    permission: Mapped['AuthPermission'] = relationship('AuthPermission', back_populates='authentication_user_user_permissions')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='authentication_user_user_permissions')


class AuthenticationUserconsent(Base):
    __tablename__ = 'authentication_userconsent'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='authentication_userc_user_id_41aee026_fk_authentic'),
        Index('authenticat_consent_750c3b_idx', 'consent_timestamp'),
        Index('authenticat_user_id_ffe2b6_idx', 'user_id', 'consent_type', 'is_active'),
        Index('authentication_userconse_user_id_consent_type_con_48a598fc_uniq', 'user_id', 'consent_type', 'consent_version', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    consent_type: Mapped[str] = mapped_column(VARCHAR(50, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    consent_given: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    consent_text: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    consent_version: Mapped[str] = mapped_column(VARCHAR(50, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    ip_address: Mapped[str] = mapped_column(CHAR(39, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    user_agent: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    consent_timestamp: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    withdrawn_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))

    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='authentication_userconsent')


class AuthenticationUserpermission(Base):
    __tablename__ = 'authentication_userpermission'
    __table_args__ = (
        ForeignKeyConstraint(['granted_by_id'], ['authentication_user.id'], name='authentication_userp_granted_by_id_6dc06a49_fk_authentic'),
        ForeignKeyConstraint(['permission_id'], ['authentication_permission.id'], name='authentication_userp_permission_id_db8a8edb_fk_authentic'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='authentication_userp_user_id_2f092576_fk_authentic'),
        Index('authentication_userp_granted_by_id_6dc06a49_fk_authentic', 'granted_by_id'),
        Index('authentication_userp_permission_id_db8a8edb_fk_authentic', 'permission_id'),
        Index('authentication_userpermi_user_id_permission_id_ee8d1150_uniq', 'user_id', 'permission_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    is_granted: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    reason: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    granted_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    permission_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    granted_by_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    granted_by: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', foreign_keys=[granted_by_id], back_populates='authentication_userpermission_granted_by')
    permission: Mapped['AuthenticationPermission'] = relationship('AuthenticationPermission', back_populates='authentication_userpermission')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='authentication_userpermission_user')


class AuthenticationUserrole(Base):
    __tablename__ = 'authentication_userrole'
    __table_args__ = (
        ForeignKeyConstraint(['assigned_by_id'], ['authentication_user.id'], name='authentication_userr_assigned_by_id_9c018c80_fk_authentic'),
        ForeignKeyConstraint(['role_id'], ['authentication_role.id'], name='authentication_userr_role_id_f9a93670_fk_authentic'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='authentication_userr_user_id_981863a5_fk_authentic'),
        Index('authentication_userr_assigned_by_id_9c018c80_fk_authentic', 'assigned_by_id'),
        Index('authentication_userr_role_id_f9a93670_fk_authentic', 'role_id'),
        Index('authentication_userrole_user_id_role_id_2e4aff32_uniq', 'user_id', 'role_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    assigned_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    assigned_by_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    assigned_by: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', foreign_keys=[assigned_by_id], back_populates='authentication_userrole_assigned_by')
    role: Mapped['AuthenticationRole'] = relationship('AuthenticationRole', back_populates='authentication_userrole')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='authentication_userrole_user')


class DjangoAdminLog(Base):
    __tablename__ = 'django_admin_log'
    __table_args__ = (
        ForeignKeyConstraint(['content_type_id'], ['django_content_type.id'], name='django_admin_log_content_type_id_c4bce8eb_fk_django_co'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='django_admin_log_user_id_c564eba6_fk_authentication_user_id'),
        Index('django_admin_log_content_type_id_c4bce8eb_fk_django_co', 'content_type_id'),
        Index('django_admin_log_user_id_c564eba6_fk_authentication_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    object_repr: Mapped[str] = mapped_column(VARCHAR(200, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    action_flag: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False)
    change_message: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_id: Mapped[Optional[str]] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'))
    content_type_id: Mapped[Optional[int]] = mapped_column(Integer)

    content_type: Mapped[Optional['DjangoContentType']] = relationship('DjangoContentType', back_populates='django_admin_log')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='django_admin_log')


class DocumentsAiconversation(Base):
    __tablename__ = 'documents_aiconversation'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_aiconversa_user_id_fbc9389f_fk_authentic'),
        Index('documents_aiconversa_user_id_fbc9389f_fk_authentic', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_file_name: Mapped[Optional[str]] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'))
    uploaded_file_path: Mapped[Optional[str]] = mapped_column(VARCHAR(500, charset='utf8mb4', collation='utf8mb4_general_ci'))
    uploaded_file_size: Mapped[Optional[int]] = mapped_column(Integer)
    uploaded_file_type: Mapped[Optional[str]] = mapped_column(VARCHAR(50, charset='utf8mb4', collation='utf8mb4_general_ci'))

    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_aiconversation')
    documents_aidataset: Mapped[list['DocumentsAidataset']] = relationship('DocumentsAidataset', back_populates='conversation')
    documents_aimessage: Mapped[list['DocumentsAimessage']] = relationship('DocumentsAimessage', back_populates='conversation')


class DocumentsDocument(Base):
    __tablename__ = 'documents_document'
    __table_args__ = (
        ForeignKeyConstraint(['brand_id'], ['documents_brand.id'], name='documents_document_brand_id_e97b95c6_fk_documents_brand_id'),
        ForeignKeyConstraint(['country_id'], ['documents_country.id'], name='documents_document_country_id_faff1925_fk_documents_country_id'),
        ForeignKeyConstraint(['course_id'], ['documents_coursecategory.id'], name='documents_document_course_id_7f33fedc_fk_documents'),
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='documents_document_created_by_id_7d00c649_fk_authentic'),
        ForeignKeyConstraint(['document_type_id'], ['documents_documenttype.id'], name='documents_document_document_type_id_1f88b50c_fk_documents'),
        ForeignKeyConstraint(['modified_by_id'], ['authentication_user.id'], name='documents_document_modified_by_id_2f944095_fk_authentic'),
        ForeignKeyConstraint(['project_id'], ['documents_project.id'], name='documents_document_project_id_4c5c366d_fk_documents_project_id'),
        ForeignKeyConstraint(['therapeutic_area_id'], ['documents_therapeuticarea.id'], name='documents_document_therapeutic_area_id_77c71cf4_fk_documents'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_document_user_id_e543d099_fk_authentication_user_id'),
        Index('document_number', 'document_number', unique=True),
        Index('documents_document_brand_id_e97b95c6_fk_documents_brand_id', 'brand_id'),
        Index('documents_document_country_id_faff1925_fk_documents_country_id', 'country_id'),
        Index('documents_document_course_id_7f33fedc_fk_documents', 'course_id'),
        Index('documents_document_created_by_id_7d00c649_fk_authentic', 'created_by_id'),
        Index('documents_document_document_type_id_1f88b50c_fk_documents', 'document_type_id'),
        Index('documents_document_modified_by_id_2f944095_fk_authentic', 'modified_by_id'),
        Index('documents_document_project_id_4c5c366d_fk_documents_project_id', 'project_id'),
        Index('documents_document_therapeutic_area_id_77c71cf4_fk_documents', 'therapeutic_area_id'),
        Index('documents_document_user_id_e543d099_fk_authentication_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    document_number: Mapped[str] = mapped_column(String(100), nullable=False)
    stage_status: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    country_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_type_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    brand_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    course_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    therapeutic_area_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    brand: Mapped[Optional['DocumentsBrand']] = relationship('DocumentsBrand', back_populates='documents_document')
    country: Mapped['DocumentsCountry'] = relationship('DocumentsCountry', back_populates='documents_document')
    course: Mapped[Optional['DocumentsCoursecategory']] = relationship('DocumentsCoursecategory', back_populates='documents_document')
    created_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[created_by_id], back_populates='documents_document_created_by')
    document_type: Mapped['DocumentsDocumenttype'] = relationship('DocumentsDocumenttype', back_populates='documents_document')
    modified_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[modified_by_id], back_populates='documents_document_modified_by')
    project: Mapped[Optional['DocumentsProject']] = relationship('DocumentsProject', back_populates='documents_document')
    therapeutic_area: Mapped[Optional['DocumentsTherapeuticarea']] = relationship('DocumentsTherapeuticarea', back_populates='documents_document')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='documents_document_user')
    documents_documentreference: Mapped[list['DocumentsDocumentreference']] = relationship('DocumentsDocumentreference', back_populates='document')
    documents_documentversion: Mapped[list['DocumentsDocumentversion']] = relationship('DocumentsDocumentversion', back_populates='document')
    documents_documentsharing: Mapped[list['DocumentsDocumentsharing']] = relationship('DocumentsDocumentsharing', back_populates='document')
    documents_emaillog: Mapped[list['DocumentsEmaillog']] = relationship('DocumentsEmaillog', back_populates='document')
    library_documenthistory: Mapped[list['LibraryDocumenthistory']] = relationship('LibraryDocumenthistory', back_populates='document')


class DocumentsEnrolluser(Base):
    __tablename__ = 'documents_enrolluser'
    __table_args__ = (
        ForeignKeyConstraint(['course_id'], ['documents_coursecategory.id'], name='documents_enrolluser_course_id_40ba04d5_fk_documents'),
        ForeignKeyConstraint(['project_id'], ['documents_project.id'], name='documents_enrolluser_project_id_8d8281bb_fk_documents_project_id'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_enrolluser_user_id_7bd7101a_fk_authentication_user_id'),
        Index('documents_enrolluser_course_id_40ba04d5_fk_documents', 'course_id'),
        Index('documents_enrolluser_project_id_8d8281bb_fk_documents_project_id', 'project_id'),
        Index('documents_enrolluser_user_id_7bd7101a_fk_authentication_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    course_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    course_end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    course: Mapped['DocumentsCoursecategory'] = relationship('DocumentsCoursecategory', back_populates='documents_enrolluser')
    project: Mapped['DocumentsProject'] = relationship('DocumentsProject', back_populates='documents_enrolluser')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_enrolluser')


class DocumentsFeedback(Base):
    __tablename__ = 'documents_feedback'
    __table_args__ = (
        ForeignKeyConstraint(['project_id'], ['documents_project.id'], name='documents_feedback_project_id_c7a37b91_fk_documents_project_id'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_feedback_user_id_1a650d3b_fk_authentication_user_id'),
        Index('documents_feedback_project_id_c7a37b91_fk_documents_project_id', 'project_id'),
        Index('documents_feedback_user_id_1a650d3b_fk_authentication_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_text: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    project: Mapped['DocumentsProject'] = relationship('DocumentsProject', back_populates='documents_feedback')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_feedback')


class DocumentsJournal(Base):
    __tablename__ = 'documents_journal'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='documents_journal_created_by_id_6c55f3e7_fk_authentic'),
        Index('documents_j_name_22f2c4_idx', 'name'),
        Index('documents_j_primary_8b2e23_idx', 'primary_subject'),
        Index('documents_journal_created_by_id_6c55f3e7_fk_authentic', 'created_by_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(VARCHAR(500, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    publishing_model: Mapped[str] = mapped_column(VARCHAR(50, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    downloads: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    primary_subject: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    secondary_subjects: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    scope_and_aims: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    keywords: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    publisher: Mapped[Optional[str]] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'))
    issn: Mapped[Optional[str]] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'))
    eissn: Mapped[Optional[str]] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'))
    journal_impact_factor: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(5, 3))
    impact_factor_year: Mapped[Optional[int]] = mapped_column(INTEGER(unsigned=True))
    submission_to_decision_days: Mapped[Optional[int]] = mapped_column(INTEGER(unsigned=True))
    website_url: Mapped[Optional[str]] = mapped_column(VARCHAR(200, charset='utf8mb4', collation='utf8mb4_general_ci'))
    submission_url: Mapped[Optional[str]] = mapped_column(VARCHAR(200, charset='utf8mb4', collation='utf8mb4_general_ci'))
    cover_image: Mapped[Optional[str]] = mapped_column(VARCHAR(100, charset='utf8mb4', collation='utf8mb4_general_ci'))
    created_by_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    created_by: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', back_populates='documents_journal')
    documents_userjournalselection: Mapped[list['DocumentsUserjournalselection']] = relationship('DocumentsUserjournalselection', back_populates='journal')


class DocumentsNotification(Base):
    __tablename__ = 'documents_notification'
    __table_args__ = (
        ForeignKeyConstraint(['receiver_id'], ['authentication_user.id'], name='documents_notificati_receiver_id_ad531399_fk_authentic'),
        ForeignKeyConstraint(['sender_id'], ['authentication_user.id'], name='documents_notificati_sender_id_5147665e_fk_authentic'),
        Index('documents_notificati_receiver_id_ad531399_fk_authentic', 'receiver_id'),
        Index('documents_notificati_sender_id_5147665e_fk_authentic', 'sender_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    sent_for: Mapped[str] = mapped_column(String(100), nullable=False)
    is_seen: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    receiver_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    receiver: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[receiver_id], back_populates='documents_notification_receiver')
    sender: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[sender_id], back_populates='documents_notification_sender')


class DocumentsResearchproject(Base):
    __tablename__ = 'documents_researchproject'
    __table_args__ = (
        ForeignKeyConstraint(['owner_id'], ['authentication_user.id'], name='documents_researchpr_owner_id_d31bea2f_fk_authentic'),
        Index('documents_researchpr_owner_id_d31bea2f_fk_authentic', 'owner_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    research_field: Mapped[str] = mapped_column(String(255), nullable=False)
    keywords: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_type: Mapped[str] = mapped_column(String(20), nullable=False)
    has_authors: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    project_type: Mapped[str] = mapped_column(String(50), nullable=False)
    therapeutic_area: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    deadline: Mapped[Optional[datetime.date]] = mapped_column(Date)
    budget: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2))
    actual_end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    client_other: Mapped[Optional[str]] = mapped_column(String(255))
    client_poc_email: Mapped[Optional[str]] = mapped_column(String(254))
    client_poc_name: Mapped[Optional[str]] = mapped_column(String(255))
    estimated_end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    journal_name: Mapped[Optional[str]] = mapped_column(String(255))
    project_type_other: Mapped[Optional[str]] = mapped_column(String(255))
    sub_therapy_area: Mapped[Optional[str]] = mapped_column(String(255))
    therapeutic_area_other: Mapped[Optional[str]] = mapped_column(String(255))

    owner: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_researchproject')
    documents_projectauthor: Mapped[list['DocumentsProjectauthor']] = relationship('DocumentsProjectauthor', back_populates='project')
    documents_projectmilestone: Mapped[list['DocumentsProjectmilestone']] = relationship('DocumentsProjectmilestone', back_populates='project')
    documents_researchprojectcollaborator: Mapped[list['DocumentsResearchprojectcollaborator']] = relationship('DocumentsResearchprojectcollaborator', back_populates='project')
    documents_researchprojectdocument: Mapped[list['DocumentsResearchprojectdocument']] = relationship('DocumentsResearchprojectdocument', back_populates='project')
    documents_researchprojecttask: Mapped[list['DocumentsResearchprojecttask']] = relationship('DocumentsResearchprojecttask', back_populates='project')


class DocumentsSmtpsettings(Base):
    __tablename__ = 'documents_smtpsettings'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='documents_smtpsettin_created_by_id_9cfc87ab_fk_authentic'),
        ForeignKeyConstraint(['updated_by_id'], ['authentication_user.id'], name='documents_smtpsettin_updated_by_id_b2a2d065_fk_authentic'),
        Index('documents_smtpsettin_created_by_id_9cfc87ab_fk_authentic', 'created_by_id'),
        Index('documents_smtpsettin_updated_by_id_b2a2d065_fk_authentic', 'updated_by_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    use_tls: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    use_ssl: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    from_email: Mapped[str] = mapped_column(String(254), nullable=False)
    from_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    is_tested: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    charset: Mapped[str] = mapped_column(String(20), nullable=False)
    crlf: Mapped[str] = mapped_column(String(10), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    encoding: Mapped[str] = mapped_column(String(20), nullable=False)
    mailtype: Mapped[str] = mapped_column(String(10), nullable=False)
    newline: Mapped[str] = mapped_column(String(10), nullable=False)
    protocol: Mapped[str] = mapped_column(String(10), nullable=False)
    smtp_crypto: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    wordwrap: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    test_email: Mapped[Optional[str]] = mapped_column(String(254))
    last_tested: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    test_result: Mapped[Optional[str]] = mapped_column(LONGTEXT)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(255))
    smtp_pass: Mapped[Optional[str]] = mapped_column(String(255))
    smtp_port: Mapped[Optional[int]] = mapped_column(Integer)
    smtp_user: Mapped[Optional[str]] = mapped_column(String(255))

    created_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[created_by_id], back_populates='documents_smtpsettings_created_by')
    updated_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[updated_by_id], back_populates='documents_smtpsettings_updated_by')


class DocumentsSupport(Base):
    __tablename__ = 'documents_support'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_support_user_id_520e5288_fk_authentication_user_id'),
        Index('documents_support_user_id_520e5288_fk_authentication_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    is_resolved: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_support')


class LibraryReferencedocument(Base):
    __tablename__ = 'library_referencedocument'
    __table_args__ = (
        ForeignKeyConstraint(['country_id'], ['documents_country.id'], name='library_referencedoc_country_id_6d2bce9b_fk_documents'),
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='library_referencedoc_created_by_id_c9342bc4_fk_authentic'),
        ForeignKeyConstraint(['modified_by_id'], ['authentication_user.id'], name='library_referencedoc_modified_by_id_debc7eff_fk_authentic'),
        ForeignKeyConstraint(['therapeutic_area_id'], ['documents_therapeuticarea.id'], name='library_referencedoc_therapeutic_area_id_ed80fbd6_fk_documents'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='library_referencedoc_user_id_0a54f13a_fk_authentic'),
        Index('library_referencedoc_country_id_6d2bce9b_fk_documents', 'country_id'),
        Index('library_referencedoc_created_by_id_c9342bc4_fk_authentic', 'created_by_id'),
        Index('library_referencedoc_modified_by_id_debc7eff_fk_authentic', 'modified_by_id'),
        Index('library_referencedoc_therapeutic_area_id_ed80fbd6_fk_documents', 'therapeutic_area_id'),
        Index('library_referencedoc_user_id_0a54f13a_fk_authentic', 'user_id'),
        Index('reference_number', 'reference_number', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reference_number: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    subtype: Mapped[str] = mapped_column(String(20), nullable=False)
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)
    file_title_name: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_file: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    country_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ref_number: Mapped[Optional[str]] = mapped_column(String(100))
    ref_year: Mapped[Optional[int]] = mapped_column(Integer)
    therapeutic_area_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    country: Mapped['DocumentsCountry'] = relationship('DocumentsCountry', back_populates='library_referencedocument')
    created_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[created_by_id], back_populates='library_referencedocument_created_by')
    modified_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[modified_by_id], back_populates='library_referencedocument_modified_by')
    therapeutic_area: Mapped[Optional['DocumentsTherapeuticarea']] = relationship('DocumentsTherapeuticarea', back_populates='library_referencedocument')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='library_referencedocument_user')
    documents_documentreference: Mapped[list['DocumentsDocumentreference']] = relationship('DocumentsDocumentreference', back_populates='reference')
    documents_documentversionreference: Mapped[list['DocumentsDocumentversionreference']] = relationship('DocumentsDocumentversionreference', back_populates='reference')


class LibraryTemporarypassword(Base):
    __tablename__ = 'library_temporarypassword'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='library_temporarypas_user_id_e0722acd_fk_authentic'),
        Index('user_id', 'user_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    password: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='library_temporarypassword')


class PlagiarismPlagiarismcheck(Base):
    __tablename__ = 'plagiarism_plagiarismcheck'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='plagiarism_plagiaris_user_id_6d368379_fk_authentic'),
        Index('plagiarism_plagiaris_user_id_6d368379_fk_authentic', 'user_id')
    )

    id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), primary_key=True)
    title: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    error_message: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    result_file: Mapped[Optional[str]] = mapped_column(VARCHAR(100, charset='utf8mb4', collation='utf8mb4_general_ci'))
    similarity_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Double(asdecimal=True))
    semantic_similarity_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Double(asdecimal=True))

    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='plagiarism_plagiarismcheck')
    plagiarism_plagiarismfile: Mapped[list['PlagiarismPlagiarismfile']] = relationship('PlagiarismPlagiarismfile', back_populates='plagiarism_check')
    plagiarism_plagiarismresult: Mapped[list['PlagiarismPlagiarismresult']] = relationship('PlagiarismPlagiarismresult', back_populates='plagiarism_check')


class DocumentsAidataset(Base):
    __tablename__ = 'documents_aidataset'
    __table_args__ = (
        ForeignKeyConstraint(['conversation_id'], ['documents_aiconversation.id'], name='documents_aidataset_conversation_id_159db32b_fk_documents'),
        Index('documents_aidataset_conversation_id_159db32b_fk_documents', 'conversation_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file: Mapped[str] = mapped_column(VARCHAR(100, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    original_filename: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    file_type: Mapped[str] = mapped_column(VARCHAR(50, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    processing_status: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processed_data: Mapped[Optional[object]] = mapped_column(JSON)
    processing_error: Mapped[Optional[str]] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'))
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    column_count: Mapped[Optional[int]] = mapped_column(Integer)
    column_names: Mapped[Optional[object]] = mapped_column(JSON)
    data_types: Mapped[Optional[object]] = mapped_column(JSON)

    conversation: Mapped['DocumentsAiconversation'] = relationship('DocumentsAiconversation', back_populates='documents_aidataset')


class DocumentsAimessage(Base):
    __tablename__ = 'documents_aimessage'
    __table_args__ = (
        ForeignKeyConstraint(['conversation_id'], ['documents_aiconversation.id'], name='documents_aimessage_conversation_id_c19f7822_fk_documents'),
        Index('documents_aimessage_conversation_id_c19f7822_fk_documents', 'conversation_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    content: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    model_used: Mapped[Optional[str]] = mapped_column(VARCHAR(100, charset='utf8mb4', collation='utf8mb4_general_ci'))
    processing_time: Mapped[Optional[decimal.Decimal]] = mapped_column(Double(asdecimal=True))
    response_data: Mapped[Optional[object]] = mapped_column(JSON)

    conversation: Mapped['DocumentsAiconversation'] = relationship('DocumentsAiconversation', back_populates='documents_aimessage')


class DocumentsDocumentreference(Base):
    __tablename__ = 'documents_documentreference'
    __table_args__ = (
        ForeignKeyConstraint(['document_id'], ['documents_document.id'], name='documents_documentre_document_id_b46868fb_fk_documents'),
        ForeignKeyConstraint(['linked_by_id'], ['authentication_user.id'], name='documents_documentre_linked_by_id_a8e924e0_fk_authentic'),
        ForeignKeyConstraint(['reference_id'], ['library_referencedocument.id'], name='documents_documentre_reference_id_7bf2ea7b_fk_library_r'),
        Index('documents_documentre_linked_by_id_a8e924e0_fk_authentic', 'linked_by_id'),
        Index('documents_documentre_reference_id_7bf2ea7b_fk_library_r', 'reference_id'),
        Index('documents_documentrefere_document_id_reference_id_2955f611_uniq', 'document_id', 'reference_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    linked_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(LONGTEXT)

    document: Mapped['DocumentsDocument'] = relationship('DocumentsDocument', back_populates='documents_documentreference')
    linked_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_documentreference')
    reference: Mapped['LibraryReferencedocument'] = relationship('LibraryReferencedocument', back_populates='documents_documentreference')


class DocumentsDocumentversion(Base):
    __tablename__ = 'documents_documentversion'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='documents_documentve_created_by_id_aaa305f1_fk_authentic'),
        ForeignKeyConstraint(['document_id'], ['documents_document.id'], name='documents_documentve_document_id_42757b7a_fk_documents'),
        ForeignKeyConstraint(['modified_by_id'], ['authentication_user.id'], name='documents_documentve_modified_by_id_d8865e40_fk_authentic'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_documentve_user_id_c865d04c_fk_authentic'),
        Index('documents_documentve_created_by_id_aaa305f1_fk_authentic', 'created_by_id'),
        Index('documents_documentve_document_id_42757b7a_fk_documents', 'document_id'),
        Index('documents_documentve_modified_by_id_d8865e40_fk_authentic', 'modified_by_id'),
        Index('documents_documentve_user_id_c865d04c_fk_authentic', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_number: Mapped[str] = mapped_column(String(50), nullable=False)
    version_count: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)
    file_title_name: Mapped[str] = mapped_column(String(500), nullable=False)
    document_file: Mapped[str] = mapped_column(String(100), nullable=False)
    stage_status: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    new_stage_status: Mapped[Optional[int]] = mapped_column(Integer)

    created_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[created_by_id], back_populates='documents_documentversion_created_by')
    document: Mapped['DocumentsDocument'] = relationship('DocumentsDocument', back_populates='documents_documentversion')
    modified_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[modified_by_id], back_populates='documents_documentversion_modified_by')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='documents_documentversion_user')
    documents_annotationactivity: Mapped[list['DocumentsAnnotationactivity']] = relationship('DocumentsAnnotationactivity', back_populates='document_version')
    documents_documentannotation: Mapped[list['DocumentsDocumentannotation']] = relationship('DocumentsDocumentannotation', back_populates='document_version')
    documents_documentsharing: Mapped[list['DocumentsDocumentsharing']] = relationship('DocumentsDocumentsharing', back_populates='document_version')
    documents_documentversionreference: Mapped[list['DocumentsDocumentversionreference']] = relationship('DocumentsDocumentversionreference', back_populates='document_version')
    documents_documentversionsharing: Mapped[list['DocumentsDocumentversionsharing']] = relationship('DocumentsDocumentversionsharing', back_populates='document_version')
    documents_emaillog: Mapped[list['DocumentsEmaillog']] = relationship('DocumentsEmaillog', back_populates='document_version')
    library_assignedreviewer: Mapped[list['LibraryAssignedreviewer']] = relationship('LibraryAssignedreviewer', back_populates='document_version')
    library_documenthistory: Mapped[list['LibraryDocumenthistory']] = relationship('LibraryDocumenthistory', back_populates='document_version')
    library_referencezip: Mapped[list['LibraryReferencezip']] = relationship('LibraryReferencezip', back_populates='document_version')


class DocumentsProjectauthor(Base):
    __tablename__ = 'documents_projectauthor'
    __table_args__ = (
        ForeignKeyConstraint(['project_id'], ['documents_researchproject.id'], name='documents_projectaut_project_id_09850a1c_fk_documents'),
        Index('documents_projectauthor_project_id_email_f0010338_uniq', 'project_id', 'email', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(500), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    author_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    project: Mapped['DocumentsResearchproject'] = relationship('DocumentsResearchproject', back_populates='documents_projectauthor')


class DocumentsProjectmilestone(Base):
    __tablename__ = 'documents_projectmilestone'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='documents_projectmil_created_by_id_9366ba42_fk_authentic'),
        ForeignKeyConstraint(['project_id'], ['documents_researchproject.id'], name='documents_projectmil_project_id_fe202829_fk_documents'),
        Index('documents_projectmil_created_by_id_9366ba42_fk_authentic', 'created_by_id'),
        Index('documents_projectmilestone_project_id_order_0fa8f9b7_uniq', 'project_id', 'order', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    milestone_name: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    order: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'))
    responsible_person_name: Mapped[Optional[str]] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'))
    responsible_person_contact: Mapped[Optional[str]] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'))
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    tat_days: Mapped[Optional[int]] = mapped_column(Integer)
    attachment: Mapped[Optional[str]] = mapped_column(VARCHAR(100, charset='utf8mb4', collation='utf8mb4_general_ci'))

    created_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_projectmilestone')
    project: Mapped['DocumentsResearchproject'] = relationship('DocumentsResearchproject', back_populates='documents_projectmilestone')


class DocumentsResearchprojectcollaborator(Base):
    __tablename__ = 'documents_researchprojectcollaborator'
    __table_args__ = (
        ForeignKeyConstraint(['project_id'], ['documents_researchproject.id'], name='documents_researchpr_project_id_aceedc8b_fk_documents'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_researchpr_user_id_768d18db_fk_authentic'),
        Index('documents_researchpr_user_id_768d18db_fk_authentic', 'user_id'),
        Index('documents_researchprojec_project_id_user_id_73b16c96_uniq', 'project_id', 'user_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    project: Mapped['DocumentsResearchproject'] = relationship('DocumentsResearchproject', back_populates='documents_researchprojectcollaborator')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_researchprojectcollaborator')


class DocumentsResearchprojectdocument(Base):
    __tablename__ = 'documents_researchprojectdocument'
    __table_args__ = (
        ForeignKeyConstraint(['project_id'], ['documents_researchproject.id'], name='documents_researchpr_project_id_01cb4c0d_fk_documents'),
        ForeignKeyConstraint(['uploaded_by_id'], ['authentication_user.id'], name='documents_researchpr_uploaded_by_id_291af9d4_fk_authentic'),
        Index('documents_researchpr_project_id_01cb4c0d_fk_documents', 'project_id'),
        Index('documents_researchpr_uploaded_by_id_291af9d4_fk_authentic', 'uploaded_by_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    project: Mapped['DocumentsResearchproject'] = relationship('DocumentsResearchproject', back_populates='documents_researchprojectdocument')
    uploaded_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_researchprojectdocument')


class DocumentsResearchprojecttask(Base):
    __tablename__ = 'documents_researchprojecttask'
    __table_args__ = (
        ForeignKeyConstraint(['assigned_to_id'], ['authentication_user.id'], name='documents_researchpr_assigned_to_id_67b48fb7_fk_authentic'),
        ForeignKeyConstraint(['project_id'], ['documents_researchproject.id'], name='documents_researchpr_project_id_89041b1e_fk_documents'),
        Index('documents_researchpr_assigned_to_id_67b48fb7_fk_authentic', 'assigned_to_id'),
        Index('documents_researchpr_project_id_89041b1e_fk_documents', 'project_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    assigned_to_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    assigned_to: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', back_populates='documents_researchprojecttask')
    project: Mapped['DocumentsResearchproject'] = relationship('DocumentsResearchproject', back_populates='documents_researchprojecttask')


class DocumentsUserjournalselection(Base):
    __tablename__ = 'documents_userjournalselection'
    __table_args__ = (
        ForeignKeyConstraint(['journal_id'], ['documents_journal.id'], name='documents_userjourna_journal_id_33c7cc58_fk_documents'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_userjourna_user_id_93117764_fk_authentic'),
        Index('documents_userjourna_journal_id_33c7cc58_fk_documents', 'journal_id'),
        Index('documents_userjournalselection_user_id_journal_id_988680dd_uniq', 'user_id', 'journal_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notes: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    is_favorite: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    manuscript_title: Mapped[str] = mapped_column(String(500), nullable=False)
    manuscript_abstract: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    selected_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    journal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    journal: Mapped['DocumentsJournal'] = relationship('DocumentsJournal', back_populates='documents_userjournalselection')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_userjournalselection')


class PlagiarismPlagiarismfile(Base):
    __tablename__ = 'plagiarism_plagiarismfile'
    __table_args__ = (
        ForeignKeyConstraint(['plagiarism_check_id'], ['plagiarism_plagiarismcheck.id'], name='plagiarism_plagiaris_plagiarism_check_id_f375efd4_fk_plagiaris'),
        Index('plagiarism_plagiaris_plagiarism_check_id_f375efd4_fk_plagiaris', 'plagiarism_check_id')
    )

    id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), primary_key=True)
    file: Mapped[str] = mapped_column(VARCHAR(100, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    original_filename: Mapped[str] = mapped_column(VARCHAR(255, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    file_type: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    plagiarism_check_id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)

    plagiarism_check: Mapped['PlagiarismPlagiarismcheck'] = relationship('PlagiarismPlagiarismcheck', back_populates='plagiarism_plagiarismfile')


class PlagiarismPlagiarismresult(Base):
    __tablename__ = 'plagiarism_plagiarismresult'
    __table_args__ = (
        ForeignKeyConstraint(['plagiarism_check_id'], ['plagiarism_plagiarismcheck.id'], name='plagiarism_plagiaris_plagiarism_check_id_674b8b66_fk_plagiaris'),
        Index('plagiarism_check_id', 'plagiarism_check_id', unique=True)
    )

    id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), primary_key=True)
    similarity_pairs: Mapped[object] = mapped_column(JSON, nullable=False)
    metadata_: Mapped[object] = mapped_column('metadata', JSON, nullable=False)
    generated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    plagiarism_check_id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    citation_matches: Mapped[object] = mapped_column(JSON, nullable=False, server_default=text("(_utf8mb4'[]')"))
    medical_terms_matched: Mapped[object] = mapped_column(JSON, nullable=False, server_default=text("(_utf8mb4'[]')"))
    semantic_matches: Mapped[object] = mapped_column(JSON, nullable=False, server_default=text("(_utf8mb4'[]')"))
    page_matches: Mapped[object] = mapped_column(JSON, nullable=False, server_default=text("(_utf8mb4'[]')"))
    detailed_sources: Mapped[object] = mapped_column(JSON, nullable=False, server_default=text("(_utf8mb4'[]')"))
    internet_sources_percent: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    match_groups: Mapped[object] = mapped_column(JSON, nullable=False, server_default=text("(_utf8mb4'{}')"))
    overall_similarity: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    publications_percent: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    source_breakdown: Mapped[object] = mapped_column(JSON, nullable=False, server_default=text("(_utf8mb4'{}')"))
    student_papers_percent: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)

    plagiarism_check: Mapped['PlagiarismPlagiarismcheck'] = relationship('PlagiarismPlagiarismcheck', back_populates='plagiarism_plagiarismresult')
    plagiarism_plagiarismpagematch: Mapped[list['PlagiarismPlagiarismpagematch']] = relationship('PlagiarismPlagiarismpagematch', back_populates='plagiarism_result')
    plagiarism_plagiarismsource: Mapped[list['PlagiarismPlagiarismsource']] = relationship('PlagiarismPlagiarismsource', back_populates='plagiarism_result')


class DocumentsAnnotationactivity(Base):
    __tablename__ = 'documents_annotationactivity'
    __table_args__ = (
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='documents_annotation_document_version_id_0d839c36_fk_documents'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_annotation_user_id_8ab98e25_fk_authentic'),
        Index('documents_a_documen_a1f37a_idx', 'document_version_id', 'user_id', 'action', 'created_at'),
        Index('documents_annotation_document_version_id_0d839c36_fk_documents', 'document_version_id'),
        Index('documents_annotation_user_id_8ab98e25_fk_authentic', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    annotation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    document_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    document_version: Mapped['DocumentsDocumentversion'] = relationship('DocumentsDocumentversion', back_populates='documents_annotationactivity')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_annotationactivity')


class DocumentsDocumentannotation(Base):
    __tablename__ = 'documents_documentannotation'
    __table_args__ = (
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='documents_documentan_document_version_id_7a9e0251_fk_documents'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_documentan_user_id_a3c35d70_fk_authentic'),
        Index('documents_documentan_document_version_id_7a9e0251_fk_documents', 'document_version_id'),
        Index('documents_documentan_user_id_a3c35d70_fk_authentic', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    annotation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    x_position: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    y_position: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    width: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    height: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    document_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    document_version: Mapped['DocumentsDocumentversion'] = relationship('DocumentsDocumentversion', back_populates='documents_documentannotation')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_documentannotation')


class DocumentsDocumentsharing(Base):
    __tablename__ = 'documents_documentsharing'
    __table_args__ = (
        ForeignKeyConstraint(['document_id'], ['documents_document.id'], name='documents_documentsh_document_id_bf0a124c_fk_documents'),
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], ondelete='CASCADE', name='fk_documentsharing_documentversion'),
        ForeignKeyConstraint(['role_required_id'], ['authentication_role.id'], name='documents_documentsh_role_required_id_350a8eb7_fk_authentic'),
        ForeignKeyConstraint(['shared_by_id'], ['authentication_user.id'], name='documents_documentsh_shared_by_id_e9f8b689_fk_authentic'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_documentsh_user_id_87c4428a_fk_authentic'),
        Index('documents_d_documen_a862eb_idx', 'document_id', 'user_id', 'is_active'),
        Index('documents_d_user_id_3de4e4_idx', 'user_id', 'is_active'),
        Index('documents_documentsh_role_required_id_350a8eb7_fk_authentic', 'role_required_id'),
        Index('documents_documentsh_shared_by_id_e9f8b689_fk_authentic', 'shared_by_id'),
        Index('documents_documentsharing_document_id_bf0a124c', 'document_id'),
        Index('fk_documentsharing_documentversion', 'document_version_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    permission_level: Mapped[str] = mapped_column(String(20), nullable=False)
    shared_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    can_share: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    can_download: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    can_annotate: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    can_delete_versions: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    notify_on_update: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    shared_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    notes: Mapped[Optional[str]] = mapped_column(LONGTEXT)
    last_accessed: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    document_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    role_required_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    document_version_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    document: Mapped[Optional['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='documents_documentsharing')
    document_version: Mapped[Optional['DocumentsDocumentversion']] = relationship('DocumentsDocumentversion', back_populates='documents_documentsharing')
    role_required: Mapped[Optional['AuthenticationRole']] = relationship('AuthenticationRole', back_populates='documents_documentsharing')
    shared_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[shared_by_id], back_populates='documents_documentsharing_shared_by')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='documents_documentsharing_user')


class DocumentsDocumentversionreference(Base):
    __tablename__ = 'documents_documentversionreference'
    __table_args__ = (
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='documents_documentve_document_version_id_f10eaf8d_fk_documents'),
        ForeignKeyConstraint(['linked_by_id'], ['authentication_user.id'], name='documents_documentve_linked_by_id_3dd45f59_fk_authentic'),
        ForeignKeyConstraint(['reference_id'], ['library_referencedocument.id'], name='documents_documentve_reference_id_09e77289_fk_library_r'),
        Index('documents_documentve_linked_by_id_3dd45f59_fk_authentic', 'linked_by_id'),
        Index('documents_documentve_reference_id_09e77289_fk_library_r', 'reference_id'),
        Index('documents_documentversio_document_version_id_refe_a912a400_uniq', 'document_version_id', 'reference_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    document_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    linked_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(LONGTEXT)

    document_version: Mapped['DocumentsDocumentversion'] = relationship('DocumentsDocumentversion', back_populates='documents_documentversionreference')
    linked_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='documents_documentversionreference')
    reference: Mapped['LibraryReferencedocument'] = relationship('LibraryReferencedocument', back_populates='documents_documentversionreference')


class DocumentsDocumentversionsharing(Base):
    __tablename__ = 'documents_documentversionsharing'
    __table_args__ = (
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='documents_documentve_document_version_id_4a4d8b6c_fk_documents'),
        ForeignKeyConstraint(['shared_by_id'], ['authentication_user.id'], name='documents_documentve_shared_by_id_509656e2_fk_authentic'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='documents_documentve_user_id_96ccf82e_fk_authentic'),
        Index('documents_documentve_shared_by_id_509656e2_fk_authentic', 'shared_by_id'),
        Index('documents_documentve_user_id_96ccf82e_fk_authentic', 'user_id'),
        Index('documents_documentversio_document_version_id_user_17e3b0cb_uniq', 'document_version_id', 'user_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    permission_level: Mapped[str] = mapped_column(String(20), nullable=False)
    shared_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    can_download: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    can_annotate: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    document_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shared_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    notes: Mapped[Optional[str]] = mapped_column(LONGTEXT)
    last_accessed: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))

    document_version: Mapped['DocumentsDocumentversion'] = relationship('DocumentsDocumentversion', back_populates='documents_documentversionsharing')
    shared_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[shared_by_id], back_populates='documents_documentversionsharing_shared_by')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='documents_documentversionsharing_user')


class DocumentsEmaillog(Base):
    __tablename__ = 'documents_emaillog'
    __table_args__ = (
        ForeignKeyConstraint(['document_id'], ['documents_document.id'], name='documents_emaillog_document_id_0e917f7e_fk_documents_document_id'),
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='documents_emaillog_document_version_id_77b083e3_fk_documents'),
        ForeignKeyConstraint(['recipient_user_id'], ['authentication_user.id'], name='documents_emaillog_recipient_user_id_cb07dc7f_fk_authentic'),
        ForeignKeyConstraint(['sender_user_id'], ['authentication_user.id'], name='documents_emaillog_sender_user_id_94728ff6_fk_authentic'),
        Index('documents_emaillog_document_id_0e917f7e_fk_documents_document_id', 'document_id'),
        Index('documents_emaillog_document_version_id_77b083e3_fk_documents', 'document_version_id'),
        Index('documents_emaillog_recipient_user_id_cb07dc7f_fk_authentic', 'recipient_user_id'),
        Index('documents_emaillog_sender_user_id_94728ff6_fk_authentic', 'sender_user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(254), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    message_content: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    from_email: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    error_message: Mapped[Optional[str]] = mapped_column(LONGTEXT)
    document_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    document_version_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    recipient_user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    sender_user_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    document: Mapped[Optional['DocumentsDocument']] = relationship('DocumentsDocument', back_populates='documents_emaillog')
    document_version: Mapped[Optional['DocumentsDocumentversion']] = relationship('DocumentsDocumentversion', back_populates='documents_emaillog')
    recipient_user: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', foreign_keys=[recipient_user_id], back_populates='documents_emaillog_recipient_user')
    sender_user: Mapped[Optional['AuthenticationUser']] = relationship('AuthenticationUser', foreign_keys=[sender_user_id], back_populates='documents_emaillog_sender_user')


class LibraryAssignedreviewer(Base):
    __tablename__ = 'library_assignedreviewer'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='library_assignedrevi_created_by_id_0b4fb2c4_fk_authentic'),
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='library_assignedrevi_document_version_id_33cc1f8e_fk_documents'),
        ForeignKeyConstraint(['modified_by_id'], ['authentication_user.id'], name='library_assignedrevi_modified_by_id_bed1202b_fk_authentic'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='library_assignedrevi_user_id_b8dcd296_fk_authentic'),
        Index('library_assignedrevi_created_by_id_0b4fb2c4_fk_authentic', 'created_by_id'),
        Index('library_assignedrevi_document_version_id_33cc1f8e_fk_documents', 'document_version_id'),
        Index('library_assignedrevi_modified_by_id_bed1202b_fk_authentic', 'modified_by_id'),
        Index('library_assignedrevi_user_id_b8dcd296_fk_authentic', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    review_date: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    is_completed: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    remarks: Mapped[Optional[str]] = mapped_column(LONGTEXT)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=6))

    created_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[created_by_id], back_populates='library_assignedreviewer_created_by')
    document_version: Mapped['DocumentsDocumentversion'] = relationship('DocumentsDocumentversion', back_populates='library_assignedreviewer')
    modified_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[modified_by_id], back_populates='library_assignedreviewer_modified_by')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='library_assignedreviewer_user')


class LibraryDocumenthistory(Base):
    __tablename__ = 'library_documenthistory'
    __table_args__ = (
        ForeignKeyConstraint(['document_id'], ['documents_document.id'], name='library_documenthist_document_id_c9b760a1_fk_documents'),
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='library_documenthist_document_version_id_6786634e_fk_documents'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='library_documenthist_user_id_096b2532_fk_authentic'),
        Index('library_documenthist_document_id_c9b760a1_fk_documents', 'document_id'),
        Index('library_documenthist_document_version_id_6786634e_fk_documents', 'document_version_id'),
        Index('library_documenthist_user_id_096b2532_fk_authentic', 'user_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    action_description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_version_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    document: Mapped['DocumentsDocument'] = relationship('DocumentsDocument', back_populates='library_documenthistory')
    document_version: Mapped[Optional['DocumentsDocumentversion']] = relationship('DocumentsDocumentversion', back_populates='library_documenthistory')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', back_populates='library_documenthistory')


class LibraryReferencezip(Base):
    __tablename__ = 'library_referencezip'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_id'], ['authentication_user.id'], name='library_referencezip_created_by_id_5d814996_fk_authentic'),
        ForeignKeyConstraint(['document_version_id'], ['documents_documentversion.id'], name='library_referencezip_document_version_id_408b28b4_fk_documents'),
        ForeignKeyConstraint(['modified_by_id'], ['authentication_user.id'], name='library_referencezip_modified_by_id_637874cb_fk_authentic'),
        ForeignKeyConstraint(['user_id'], ['authentication_user.id'], name='library_referencezip_user_id_92a45b43_fk_authentication_user_id'),
        Index('library_referencezip_created_by_id_5d814996_fk_authentic', 'created_by_id'),
        Index('library_referencezip_document_version_id_408b28b4_fk_documents', 'document_version_id'),
        Index('library_referencezip_modified_by_id_637874cb_fk_authentic', 'modified_by_id'),
        Index('library_referencezip_user_id_92a45b43_fk_authentication_user_id', 'user_id'),
        Index('reference_zip_number', 'reference_zip_number', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reference_zip_number: Mapped[str] = mapped_column(String(100), nullable=False)
    version_number: Mapped[str] = mapped_column(String(50), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)
    file_title_name: Mapped[str] = mapped_column(String(500), nullable=False)
    zip_file: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    created_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[created_by_id], back_populates='library_referencezip_created_by')
    document_version: Mapped['DocumentsDocumentversion'] = relationship('DocumentsDocumentversion', back_populates='library_referencezip')
    modified_by: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[modified_by_id], back_populates='library_referencezip_modified_by')
    user: Mapped['AuthenticationUser'] = relationship('AuthenticationUser', foreign_keys=[user_id], back_populates='library_referencezip_user')


class PlagiarismPlagiarismpagematch(Base):
    __tablename__ = 'plagiarism_plagiarismpagematch'
    __table_args__ = (
        ForeignKeyConstraint(['plagiarism_result_id'], ['plagiarism_plagiarismresult.id'], name='plagiarism_plagiaris_plagiarism_result_id_49b8feea_fk_plagiaris'),
        Index('plagiarism_plagiaris_plagiarism_result_id_49b8feea_fk_plagiaris', 'plagiarism_result_id')
    )

    id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), primary_key=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_percentage: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    content_preview: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    has_matches: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    highlighted_content: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    plagiarism_result_id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)

    plagiarism_result: Mapped['PlagiarismPlagiarismresult'] = relationship('PlagiarismPlagiarismresult', back_populates='plagiarism_plagiarismpagematch')
    plagiarism_pagesourcematch: Mapped[list['PlagiarismPagesourcematch']] = relationship('PlagiarismPagesourcematch', back_populates='page_match')


class PlagiarismPlagiarismsource(Base):
    __tablename__ = 'plagiarism_plagiarismsource'
    __table_args__ = (
        ForeignKeyConstraint(['plagiarism_result_id'], ['plagiarism_plagiarismresult.id'], name='plagiarism_plagiaris_plagiarism_result_id_4df74cdd_fk_plagiaris'),
        Index('plagiarism_plagiaris_plagiarism_result_id_4df74cdd_fk_plagiaris', 'plagiarism_result_id')
    )

    id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), primary_key=True)
    source_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(LONGTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    url: Mapped[str] = mapped_column(VARCHAR(200, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    source_type: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    similarity_percentage: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    match_type: Mapped[str] = mapped_column(VARCHAR(20, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    matched_words: Mapped[object] = mapped_column(JSON, nullable=False)
    match_count: Mapped[int] = mapped_column(Integer, nullable=False)
    plagiarism_result_id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)

    plagiarism_result: Mapped['PlagiarismPlagiarismresult'] = relationship('PlagiarismPlagiarismresult', back_populates='plagiarism_plagiarismsource')
    plagiarism_pagesourcematch: Mapped[list['PlagiarismPagesourcematch']] = relationship('PlagiarismPagesourcematch', back_populates='source')


class PlagiarismPagesourcematch(Base):
    __tablename__ = 'plagiarism_pagesourcematch'
    __table_args__ = (
        ForeignKeyConstraint(['page_match_id'], ['plagiarism_plagiarismpagematch.id'], name='plagiarism_pagesourc_page_match_id_5bdd4f0e_fk_plagiaris'),
        ForeignKeyConstraint(['source_id'], ['plagiarism_plagiarismsource.id'], name='plagiarism_pagesourc_source_id_a6feda94_fk_plagiaris'),
        Index('plagiarism_pagesourc_page_match_id_5bdd4f0e_fk_plagiaris', 'page_match_id'),
        Index('plagiarism_pagesourc_source_id_a6feda94_fk_plagiaris', 'source_id')
    )

    id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), primary_key=True)
    similarity_percentage: Mapped[decimal.Decimal] = mapped_column(Double(asdecimal=True), nullable=False)
    matched_segments: Mapped[object] = mapped_column(JSON, nullable=False)
    page_match_id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)
    source_id: Mapped[str] = mapped_column(CHAR(32, charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=False)

    page_match: Mapped['PlagiarismPlagiarismpagematch'] = relationship('PlagiarismPlagiarismpagematch', back_populates='plagiarism_pagesourcematch')
    source: Mapped['PlagiarismPlagiarismsource'] = relationship('PlagiarismPlagiarismsource', back_populates='plagiarism_pagesourcematch')
