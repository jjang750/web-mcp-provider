from __future__ import annotations
import importlib
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlparse
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from backend import auth
from backend.db import init_db, list_tables
from engine.http_client import DEFAULT_BASE_URL

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


@app.middleware("http")
async def require_auth(request: Request, call_next):
    """인증 활성화 시: 미인증 요청은 페이지=/login 리다이렉트, /api=401 JSON.

    인증된 요청은 세션을 슬라이딩 갱신(무활동 30분 타임아웃, 24h 절대 상한).
    """
    if auth.AUTH_ENABLED and not auth.is_public_path(request.url.path):
        ok, new_token = auth.authenticate(request)
        if not ok:
            if request.url.path.startswith("/api"):
                return JSONResponse({"detail": "세션이 만료되었습니다. 다시 로그인하세요."}, status_code=401)
            nxt = request.url.path
            if request.url.query:
                nxt += "?" + request.url.query
            return RedirectResponse(url=f"/login?next={quote(nxt, safe='')}", status_code=302)
        response = await call_next(request)
        if new_token:
            auth.set_auth_cookie(response, new_token)  # 슬라이딩: 활동 시 타임아웃 리셋
        return response
    return await call_next(request)

for _mod in ("specs", "operations", "workflows", "executions", "connections"):
    try:
        module = importlib.import_module(f"backend.routers.{_mod}")
    except ModuleNotFoundError:
        continue
    router = getattr(module, "router", None)
    if router is not None:
        app.include_router(router)


def render(request: Request, name: str, **context) -> HTMLResponse:
    return HTMLResponse(templates.env.get_template(name).render(request=request, **context))


def _safe_next(next_url: str | None) -> str:
    """오픈 리다이렉트 방지 — 같은 사이트 내부 경로만 허용."""
    if not next_url:
        return "/"
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc or not next_url.startswith("/"):
        return "/"
    return next_url


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str | None = None):
    if auth.is_authenticated(request):
        return RedirectResponse(url=_safe_next(next), status_code=302)
    return render(request, "login.html", next=next or "")


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str | None = None,
):
    if not auth.verify_credentials(username, password):
        html = templates.env.get_template("login.html").render(
            request=request, error="아이디 또는 비밀번호가 올바르지 않습니다.", next=next or ""
        )
        return HTMLResponse(html, status_code=401)
    resp = RedirectResponse(url=_safe_next(next), status_code=302)
    auth.set_auth_cookie(resp, auth.create_token(username))
    return resp


@app.post("/logout")
@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    auth.clear_auth_cookie(resp)
    return resp


@app.get("/healthz")
def healthz():
    return {"status": "ok", "tables": list_tables()}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(request, "index.html")


@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request):
    return render(request, "logs.html")


@app.get("/editor/{workflow_id}", response_class=HTMLResponse)
def editor(request: Request, workflow_id: int):
    return render(
        request, "editor.html", workflow_id=workflow_id, default_base_url=DEFAULT_BASE_URL
    )
