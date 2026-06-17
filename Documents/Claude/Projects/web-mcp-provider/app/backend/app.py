from __future__ import annotations
import importlib
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from backend.db import init_db, list_tables

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MCP Provider", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

for _mod in ("specs", "operations", "workflows", "executions"):
    try:
        module = importlib.import_module(f"backend.routers.{_mod}")
    except ModuleNotFoundError:
        continue
    router = getattr(module, "router", None)
    if router is not None:
        app.include_router(router)


def render(request: Request, name: str, **context) -> HTMLResponse:
    return HTMLResponse(templates.env.get_template(name).render(request=request, **context))


@app.get("/healthz")
def healthz():
    return {"status": "ok", "tables": list_tables()}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(request, "index.html")


@app.get("/editor/{workflow_id}", response_class=HTMLResponse)
def editor(request: Request, workflow_id: int):
    return render(request, "editor.html", workflow_id=workflow_id)
