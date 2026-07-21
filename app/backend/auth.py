"""관리 UI 인증/인가 — JWT(HttpOnly 쿠키) 기반.

설계 우선순위(정확성→재현성→보안→운영):
- 자격증명은 .env 에서만 주입(APP_AUTH_USER / APP_AUTH_PASSWORD), 평문 비교.
- 로그인 성공 시 JWT 발급 → HttpOnly 쿠키(cookie_name)로 내려줌. 만료 1일(기본 24h) → "1일 1회" 로그인.
- 프론트는 same-origin fetch 라 쿠키가 자동 전송되어 기존 코드 수정 불필요.
- 미들웨어에서 HTML 페이지는 /login 리다이렉트, /api 는 401 JSON 반환.

인증 미설정(APP_AUTH_USER 비어있음) 시 AUTH_ENABLED=False → 기존 동작 유지(무인증).
운영 배포에서는 반드시 .env 로 자격증명/시크릿을 설정할 것.
"""
from __future__ import annotations

import os
import hmac
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt  # PyJWT

# --- .env 자동 로드 (로컬 실행 시 env_file 없이도 동작하도록) ---------------
# 이미 설정된 실제 환경변수는 덮어쓰지 않는다(override=False).
try:
    from dotenv import load_dotenv

    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"  # app/.env
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH, override=False)
except ModuleNotFoundError:
    pass  # python-dotenv 미설치 시 OS 환경변수만 사용

# --- .env 주입 설정 -------------------------------------------------------
AUTH_USER = os.environ.get("APP_AUTH_USER", "").strip()
AUTH_PASSWORD = os.environ.get("APP_AUTH_PASSWORD", "")
JWT_SECRET = os.environ.get("APP_JWT_SECRET", "").strip()
JWT_ALG = "HS256"
# 절대 상한 — 로그인 후 최대 유효 시간("1일 1회").
JWT_EXPIRE_HOURS = int(os.environ.get("APP_JWT_EXPIRE_HOURS", "24"))
# 무활동(idle) 세션 타임아웃(분) — 마지막 요청 후 이 시간 지나면 만료. 요청마다 슬라이딩 갱신.
SESSION_IDLE_MINUTES = int(os.environ.get("APP_SESSION_IDLE_MINUTES", "30"))
COOKIE_NAME = os.environ.get("APP_AUTH_COOKIE", "mcp_auth")
# 리버스 프록시가 TLS 종단(HTTPS) 이면 true 권장. 로컬 HTTP 테스트 시 false.
COOKIE_SECURE = os.environ.get("APP_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

# 자격증명이 설정된 경우에만 인증을 활성화한다.
AUTH_ENABLED = bool(AUTH_USER and AUTH_PASSWORD)

# 인증을 켰는데 시크릿이 없으면 운영상 위험 → 명확히 실패시킨다.
if AUTH_ENABLED and not JWT_SECRET:
    raise RuntimeError(
        "APP_AUTH_USER/PASSWORD 설정 시 APP_JWT_SECRET 도 필수입니다(.env). "
        "긴 랜덤 문자열을 지정하세요."
    )

# 미들웨어에서 인증 없이 통과시킬 경로 접두사.
PUBLIC_PREFIXES = ("/login", "/logout", "/static", "/healthz", "/favicon.ico")


def verify_credentials(username: str, password: str) -> bool:
    """타이밍 안전 비교로 자격증명 검증."""
    if not AUTH_ENABLED:
        return False
    ok_user = hmac.compare_digest(username or "", AUTH_USER)
    ok_pass = hmac.compare_digest(password or "", AUTH_PASSWORD)
    return ok_user and ok_pass


def create_token(username: str, login_at: datetime | None = None) -> str:
    """토큰 발급. exp=무활동 타임아웃(30분), lat=로그인 시각(절대 상한 기준)."""
    now = datetime.now(timezone.utc)
    login_at = login_at or now
    payload = {
        "sub": username,
        "lat": int(login_at.timestamp()),  # login-at: 절대 상한 기준(고정)
        "iat": now,
        "exp": now + timedelta(minutes=SESSION_IDLE_MINUTES),  # 무활동 만료
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict | None:
    """유효하면 payload, 만료/위조면 None."""
    if not token:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


def _within_absolute_cap(payload: dict) -> bool:
    """로그인 후 절대 상한(JWT_EXPIRE_HOURS) 이내인지."""
    lat = payload.get("lat")
    if lat is None:
        return True  # 구버전 토큰 호환
    login_at = datetime.fromtimestamp(lat, tz=timezone.utc)
    return datetime.now(timezone.utc) - login_at < timedelta(hours=JWT_EXPIRE_HOURS)


def authenticate(request) -> tuple[bool, str | None]:
    """인증 검증 + 슬라이딩 갱신.

    반환: (인증 성공 여부, 갱신할 새 토큰 | None).
    - 무활동 30분 초과(exp 만료) → 실패.
    - 절대 상한 24h 초과 → 실패.
    - 유효 → 성공 + 새 토큰(exp 재연장, lat 유지)으로 슬라이딩.
    """
    if not AUTH_ENABLED:
        return True, None
    payload = decode_token(request.cookies.get(COOKIE_NAME, ""))
    if payload is None or not _within_absolute_cap(payload):
        return False, None
    login_at = datetime.fromtimestamp(payload["lat"], tz=timezone.utc) if payload.get("lat") else None
    return True, create_token(payload.get("sub", ""), login_at=login_at)


def is_authenticated(request) -> bool:
    """요청 쿠키의 JWT 가 유효한지(슬라이딩 갱신 없이 조회만)."""
    if not AUTH_ENABLED:
        return True
    payload = decode_token(request.cookies.get(COOKIE_NAME, ""))
    return payload is not None and _within_absolute_cap(payload)


def is_public_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p) for p in PUBLIC_PREFIXES)


def set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_IDLE_MINUTES * 60,  # 무활동 타임아웃과 동기화(브라우저도 idle 시 쿠키 폐기)
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")
