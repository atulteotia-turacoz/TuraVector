"""TuraVector FastAPI application.

Routers are discovered automatically: every module in app/routers/ that exposes
`router` (and optionally more APIRouter objects listed in `routers`) is included.
"""
import importlib
import logging
import pkgutil

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import routers as routers_pkg
from app.config import settings

logging.basicConfig(level=logging.INFO if settings.DEBUG else logging.WARNING)
log = logging.getLogger("turadome")

app = FastAPI(title="TuraVector API", version="2.0.0")


@app.on_event("startup")
def _start_invoice_reminders() -> None:
    if settings.INVOICE_REMINDERS_AUTORUN:
        from app.services import billing_reminders
        billing_reminders.start_runner()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def _include_routers() -> None:
    for mod_info in sorted(pkgutil.iter_modules(routers_pkg.__path__), key=lambda m: m.name):
        if mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{routers_pkg.__name__}.{mod_info.name}")
        found = [obj for obj in vars(module).values() if isinstance(obj, APIRouter)]
        for r in found:
            app.include_router(r)
        log.info("router module %s: %d router(s)", mod_info.name, len(found))


_include_routers()

settings.media_root.mkdir(parents=True, exist_ok=True)
app.mount(settings.MEDIA_URL.rstrip("/"), StaticFiles(directory=settings.media_root), name="media")


@app.get("/api/health")
def health():
    return {"status": "ok"}
