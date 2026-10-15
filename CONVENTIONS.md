# TuraDomeNew — porting conventions

Port of the Django app in `TuraDome/` (one level up) to **FastAPI + React**. Goal: **identical features** — every page, form, field, filter, permission check, email, notification, status transition, export and edge case in the Django code must exist in the new app. Do not add, drop or "improve" features. Only the look changes (new design system).

```
TuraDomeNew/
  backend/     FastAPI  (http://localhost:8001)   ./run.sh
  frontend/    React    (http://localhost:5173)   npm run dev   — the user app
  superadmin/  React    (http://localhost:5174)   npm run dev   — replaces Django /admin/
```

## Data — non-negotiable
- DB `tura_dome_new` is a **verified copy of production data**. Schema is unchanged (Django's tables). Never ALTER/DROP/TRUNCATE, never delete or modify existing rows outside a real user action in the app.
- **Tests**: use `backend/tests/conftest.py` fixtures (`client`, `db`, `login_as`, `sent_emails`). They wrap each test in a transaction that is rolled back, use a temp MEDIA_ROOT and stub email. **Never** call write endpoints with a raw `SessionLocal()`, curl against a running server, or the `mysql` CLI. Read-only queries are fine.
- Existing users (all have Django pbkdf2 hashes): `admin` (superuser), `reviewer1`, `reviewer2`, `teacher1`, `multi_role_test`, … — query `authentication_user` for more.
- Uploaded files live in `TuraDome/media` (MEDIA_ROOT). DB columns store paths relative to it, exactly like Django FileField. The directory may be empty locally — code must handle missing files gracefully (404, not 500).

## Backend (`backend/app/`)
- **Models**: `from app.models import Document, DocumentVersion, User, ...` — aliases named after the Django models (see `app/models/__init__.py`). Underlying classes are sqlacodegen output in `app/models/generated.py` (relationships included, e.g. `version.document`, `doc.user`, `doc.created_by`). Booleans are TINYINT → compare with `== 1`, assign `1/0`. UUID PKs (plagiarism) are `CHAR(32)` hex without dashes, as Django stores them.
- `created_at`/`updated_at` and other `auto_now(_add)` columns are filled automatically by an ORM hook. **All other NOT NULL columns have no DB default** — set every field the Django model gives a default (e.g. `is_active=1`, `stage_status=0`, `retry_count=0`, JSON fields `{}`).
- Datetimes are **naive UTC** (`app.models.utcnow()`). Serialize with `app.core.utils.iso()` (adds `Z`); the frontend localises.
- Auth/permissions (`app/core/deps.py`): `get_current_user`, `get_optional_user`, `require_superuser`, `require_staff`, `require_manager`, `require_admin_like`, `require_permission(dashboard, module, action)`, `require_capability("can_upload")`. Programmatic checks: `app.core.permissions` → `can(db, user, "can_view_all_documents")`, `has_module_permission(...)`, `is_manager_like(user)` (user_type=='manager' or is_manager), `is_admin_like(user)` (staff/superuser/manager). Mirror the exact decorator/inline checks of each Django view, including its error message text.
- Email: `app.core.email.send_email_with_logging(db, subject, message, [to], email_type, sender_user=, recipient_user=, document=, document_version=)` (writes EmailLog exactly like Django) and `send_plain_email(...)` for Django `send_mail`.
- Files: `app.core.files` → `save_upload(upload, directory)` returns the relative path to store; `media_path(rel)` → absolute Path; `media_url(rel)`; `delete_file(rel)`; `document_upload_dir(version_id)` etc. replicate Django `upload_to`. Media is also served statically at `/media/...`. For files the browser must fetch (viewer, downloads) prefer an authenticated endpoint returning `FileResponse`; the frontend appends `?token=` via `authUrl()`.
- Utilities: `app.core.utils` → `iso`, `time_ago`, `full_name`, `user_brief`, `user_type_display`, `paginate`, `get_client_ip`, `format_datetime_for_user`, `localize_datetime`.
- **Routers are auto-discovered**: create `app/routers/<module>_<topic>.py` with module-level `router = APIRouter(prefix="/api/<area>", tags=[...])`. Every top-level `APIRouter` object in a module gets included, so don't create sub-routers that you also include manually. All paths under `/api/` except OnlyOffice callbacks if the external server needs a fixed path.
- Business logic that is more than a few lines → `app/services/<module>_*.py`; Pydantic models → `app/schemas/<module>_*.py`. For multipart forms use `Form(...)`/`File(...)`.
- Settings: `from app.config import settings` (all Django settings incl. API keys are there; secrets come from `backend/.env`).
- Venv: `backend/venv/bin/python`. Run tests: `cd backend && ./venv/bin/python -m pytest -q tests/test_<module>*.py`. Add packages to `requirements.txt` if you need new ones (and `./venv/bin/pip install`).

## Frontend (`frontend/src/`)
- Stack: React 18 + TypeScript + Vite, react-router-dom v6, @tanstack/react-query, axios, lucide-react icons, chart.js + react-chartjs-2, @pdftron/webviewer 8.10.0 (the exact SDK production ran) (runtime served at `/webviewer/lib`, see `GET /api/config` → `PDFTRON_PATH`, licence key etc.).
- **Routes**: create `src/features/<module>/routes.tsx` exporting `routes: AppRoute[]` (`src/routes.ts`). Collected automatically. Use `React.lazy` for pages. **Keep the original Django URL paths** with trailing slash (`/documents/document/:documentId/`, `/library/manage-users/`). `layout`: `'main'` for templates extending `base.html`, `'other'` for `other_documents_base.html`, `'bare'` for standalone pages (auth, full-screen viewers). `public: true` for pages reachable without login.
- The sidebar/topbar already exist (`src/layouts/AppShell.tsx`) — don't duplicate navigation; in-page links/buttons are yours.
- API: `import { api, authUrl, downloadFile, toFormData, errorMessage } from '@/lib/api'`. Auth: `useAuth()` → `{ user, can('can_upload'), refresh }`; `useUser()` inside protected pages. Dates: `formatDateTime`, `formatDate`, `timeAgo`, `fileSize` from `@/lib/format`.
- UI kit: `@/components/ui` → `PageHeader, Panel, Stat, DataTable (search/sort/paging; replaces jQuery DataTables), Pagination, Modal, useConfirm, useToast (replaces Django messages), Field, SearchInput, SearchSelect (replaces select2; single/multi, remote search), Tabs, Badge, StageStatus, Loading, Empty, ErrorNotice, Spinner`.
- CSS: use the classes in `src/styles/base.css` + `app.css` (`btn btn-primary|secondary|ghost|danger btn-sm`, `act`, `input`, `field`, `panel`, `tbl`, `stat-grid`, `grid-2/3/4`, `form-grid`, `notice notice-ok|warn|danger|accent`, `badge-*`, `kv`, `dropzone`, `viewer-frame`, `row`, `between`, `stack`, `muted`, `small` …). Colours only via CSS variables (`var(--accent)`, `var(--ink-2)`, `var(--ok)`…) so light/dark and all palettes work. No Bootstrap, no hard-coded colours, no inline gradients. Square corners, hairlines, no shadows. Feature-specific CSS → `src/features/<module>/<module>.css` imported by that feature.
- Typecheck before finishing: `cd frontend && npx tsc --noEmit -p .` must pass for your files.

## Ownership (parallel work)
Each module owns ONLY: `backend/app/routers/<module>_*.py`, `backend/app/services/<module>_*.py`, `backend/app/schemas/<module>_*.py`, `backend/tests/test_<module>*.py`, `frontend/src/features/<module>/**`. **Do not edit shared files** (`app/core/*`, `app/models/*`, `app/main.py`, `app/config.py`, `src/components/*`, `src/lib/*`, `src/layouts/*`, `src/App.tsx`, styles). If you truly need a shared change, implement it locally in your module and mention it in your final report.
Already implemented (don't re-implement): `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET /api/config`, `GET /api/library/quick-stats`, `GET /api/notifications/recent`, `POST /api/notifications/{id}/read`.
