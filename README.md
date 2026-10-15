# TuraDome (New)

The TuraDome Django application, rebuilt as three separate apps with the same features:

| Directory     | What                                   | Stack                          | URL                      |
|---------------|----------------------------------------|--------------------------------|--------------------------|
| `backend/`    | REST API                               | Python · FastAPI · SQLAlchemy  | http://localhost:8001    |
| `frontend/`   | The user application                   | React · TypeScript · Vite      | http://localhost:5173    |
| `superadmin/` | Admin console (replaces Django `/admin/`) | React · TypeScript · Vite   | http://localhost:5174    |

## Database

- Uses MySQL database **`tura_dome_new`** (user `atul`). It holds a full, verified copy of the original `tura_dome` data: all 84 tables, with identical row counts. The original `tura_dome` database is untouched.
- The schema is exactly what Django created, so **no migrations are needed**. The old Django app and the new API can even run against the same database side by side.
- Existing passwords keep working: the API verifies and creates Django-format `pbkdf2_sha256` hashes.
- Uploaded files are read from the original `TuraDome/media` folder (`MEDIA_ROOT` in `backend/.env`).

## Running

```bash
# 1. API
cd backend && ./run.sh                       # creates venv on first run; http://localhost:8001/docs

# 2. User app
cd frontend && npm install && npm run dev    # http://localhost:5173

# 3. Admin console (superusers only)
cd superadmin && npm install && npm run dev  # http://localhost:5174
```

The Apryse/PDFTron WebViewer **8.10.0** runtime (the server SDK build) lives in `frontend/public/webviewer/lib`. To reinstall it from a server copy: `WEBVIEWER_SDK_DIR=/path/to/static/dist/lib node scripts/copy-webviewer.mjs`.

## Theme

Both React apps share the design system: light, dark or follow-system mode, plus eight accent palettes and a custom colour. Users pick these from the palette button in the top bar, and the choice is remembered per browser.

## Configuration

All settings (DB, JWT secret, SMTP fallback, OnlyOffice, Office 365, PDFTron, Springer / Elsevier / PubMed keys) live in `backend/.env`. See `backend/.env.example`. The keys that were hard-coded in the Django `settings.py` have been moved into `.env`.

## Tests

```bash
cd backend && ./venv/bin/python -m pytest -q
```

Tests run against `tura_dome_new` inside a transaction that is always rolled back. Uploads go to a temporary folder and outgoing email is stubbed, so running the suite never changes real data.

## Developer notes

See `CONVENTIONS.md` for how the code is organised: router auto-discovery, the model aliases, permission helpers, and the feature-folder routing in the React apps.
# TuraVector
