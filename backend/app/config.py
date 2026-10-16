"""Application settings, loaded from environment / .env.

Every value mirrors a setting from the original Django project
(turadome_django/settings.py) so behaviour stays identical.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # .../TuraDomeNew/backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "TuraVector"
    DEBUG: bool = True

    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "tura_dome_new"
    DB_USER: str = "atul"
    DB_PASSWORD: str = ""

    # Auth (JWT replaces Django sessions)
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    JWT_ALGORITHM: str = "HS256"

    # URLs
    BACKEND_PUBLIC_URL: str = "http://localhost:8001"  # the site root, WITHOUT /api (code adds /api/... and /media/...)
    FRONTEND_URL: str = "http://localhost:5173"
    SUPERADMIN_URL: str = "http://localhost:5174"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"

    @field_validator("BACKEND_PUBLIC_URL")
    @classmethod
    def _no_api_suffix(cls, v: str) -> str:
        # media URLs are <this>/media/… and callbacks <this>/api/…, so a trailing /api would be doubled
        v = v.strip().rstrip("/")
        return v[:-4] if v.endswith("/api") else v

    # Media — defaults to the original Django MEDIA_ROOT so existing files keep working
    MEDIA_ROOT: str = str(BASE_DIR.parent.parent / "media")
    MEDIA_URL: str = "/media/"
    FILE_UPLOAD_MAX_SIZE: int = 104857600  # 100MB
    TIME_ZONE: str = "Asia/Kolkata"

    # Email fallback (used when no active SMTPSettings row exists)
    EMAIL_BACKEND: str = "console"  # console | smtp
    EMAIL_HOST: str = "smtp.gmail.com"
    EMAIL_PORT: int = 587
    EMAIL_USE_TLS: bool = True
    EMAIL_HOST_USER: str = ""
    EMAIL_HOST_PASSWORD: str = ""
    DEFAULT_FROM_EMAIL: str = "noreply@turadome.com"
    # Testing: deliver every email to this one address instead of the real recipient. Leave empty in production.
    EMAIL_REDIRECT_TO: str = ""
    # check for due invoice reminders every hour inside the app (scripts/send_invoice_reminders.py does the same from cron)
    INVOICE_REMINDERS_AUTORUN: bool = True

    # OnlyOffice
    ONLYOFFICE_JWT_SECRET: str = ""
    # The secret the live Django editor view actually signed with (turadome_django.utils.generate_token)
    ONLYOFFICE_EDITOR_JWT_SECRET: str = ""
    ONLYOFFICE_DOCUMENT_SERVER_URL: str = "https://officedom.turadome.com"
    ONLYOFFICE_DISABLE_JWT: bool = False
    ENABLE_ONLYOFFICE_EDITOR: bool = False
    NGROK_BASE_URL: str = ""

    # Microsoft Office 365 / OneDrive
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = ""
    MICROSOFT_ONEDRIVE_USER_ID: str = ""

    # Apryse / PDFTron WebViewer
    PDFTRON_ENABLED: bool = True
    PDFTRON_LICENSE_KEY: str = ""
    PDFTRON_VERSION: str = "8.10.0"
    PDFTRON_PATH: str = "/webviewer/lib"

    # Document security
    ALLOW_DOCUMENT_DOWNLOAD: bool = False
    DOCUMENT_WATERMARK: bool = True
    DOCUMENT_PRINT_DISABLED: bool = True

    # Other Tura applications shown as cards on the dashboard-selection page
    TURA_RESEARCH_ASSISTANT_URL: str = "https://turaresearchassistant.turacoz.com/login"
    TURA_LMS_URL: str = "https://turalms.turacoz.com/login/index.php"
    TURAGRAMMAR_URL: str = "https://turagrammar.turacoz.com/"
    # Single sign-on into those apps (app/services/external_apps_sso.py). An app whose SSO
    # settings are blank keeps opening its normal login page.
    SSO_TICKET_TTL_SECONDS: int = 60
    TURA_RESEARCH_ASSISTANT_SSO_URL: str = ""     # e.g. https://turaresearchassistant.turacoz.com/sso
    TURA_RESEARCH_ASSISTANT_SSO_SECRET: str = ""  # same value as TURADOME_SSO_SECRET in that app
    TURAGRAMMAR_SSO_URL: str = ""                 # e.g. https://turagrammar.turacoz.com/sso
    TURAGRAMMAR_SSO_SECRET: str = ""              # same value as TURADOME_SSO_SECRET in that app
    TURA_LMS_BASE_URL: str = "https://turalms.turacoz.com"
    TURA_LMS_WS_TOKEN: str = ""                   # Moodle web-service token for auth_userkey

    # Journal search providers
    SPRINGER_API_KEY: str = ""
    SPRINGER_API_BASE_URL: str = "https://api.springernature.com/meta/v2/json"
    ELSEVIER_API_KEY: str = ""
    ELSEVIER_SCOPUS_API_URL: str = "https://api.elsevier.com/content/search/scopus"
    ELSEVIER_SERIAL_API_URL: str = "https://api.elsevier.com/content/serial/title"
    PUBMED_API_KEY: str = ""
    PUBMED_ESEARCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    PUBMED_EFETCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus

        return (
            f"mysql+pymysql://{self.DB_USER}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def microsoft_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.MICROSOFT_TENANT_ID}"

    @property
    def media_root(self) -> Path:
        path = Path(self.MEDIA_ROOT)
        return (path if path.is_absolute() else (BASE_DIR / path)).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if not settings.SECRET_KEY.strip():
    # every login token is signed with it: an empty value only shows up later as a 500 on login
    raise RuntimeError("SECRET_KEY is empty in backend/.env. Set it to a long random value, e.g. the output of "
                       "`python3 -c \"import secrets; print(secrets.token_urlsafe(64))\"`, and restart the service.")
