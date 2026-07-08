"""MCP 서버 (streamable_http) — 도메인에서 HTTP로 노출.

기존 stdio 서버(`backend.mcp_server`)의 low-level `server`·툴 빌드 로직을 그대로 재사용하고,
전송 계층만 stdio → streamable HTTP 로 교체한다. 두 진입점이 동일 로직을 공유하므로
노출 워크플로우·스키마·dry_run 동작은 stdio 와 완전히 동일하다.

실행:
    PYTHONPATH=<repo> python -m backend.mcp_http_server

엔드포인트:
    - {MCP_HTTP_PATH}(기본 /mcp) : MCP streamable_http (POST/GET/DELETE)
    - /healthz                    : 상태 점검(인증 불필요)

환경변수:
    MCP_HTTP_HOST    (기본 0.0.0.0)   바인딩 호스트
    MCP_HTTP_PORT    (기본 8800)      바인딩 포트
    MCP_HTTP_PATH    (기본 /mcp)      MCP 엔드포인트 경로
    MCP_AUTH_TOKEN   (없음)           설정 시 'Authorization: Bearer <token>' 검증. 미설정 시 개방(경고).
    MCP_SSL_CERTFILE (없음)           TLS 인증서(fullchain) 경로 → HTTPS
    MCP_SSL_KEYFILE  (없음)           TLS 개인키 경로
    MCP_ALLOWED_HOSTS(없음)           콤마구분. 설정 시 DNS rebinding 보호(Host 화이트리스트)
    MCP_JSON_RESPONSE(false)          true면 SSE 대신 단일 JSON 응답
    MCP_GROUP        (없음)           특정 그룹 워크플로우만 노출(기존과 동일)
    MCP_FORWARDED_ALLOW_IPS(*)        신뢰할 프록시 IP(uvicorn forwarded_allow_ips)
    LOG_LEVEL        (INFO)           로깅 레벨
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

# 기존 stdio 서버의 로직을 그대로 재사용(import 시 핸들러가 `server`에 등록됨)
from backend import mcp_server
from backend.db import init_db, list_tables

logger = logging.getLogger("mcp_http")

MCP_PATH = os.environ.get("MCP_HTTP_PATH", "/mcp")
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN") or None
JSON_RESPONSE = os.environ.get("MCP_JSON_RESPONSE", "false").lower() in ("1", "true", "yes")
_ALLOWED = [h.strip() for h in (os.environ.get("MCP_ALLOWED_HOSTS") or "").split(",") if h.strip()]


def _security_settings() -> TransportSecuritySettings | None:
    """MCP_ALLOWED_HOSTS 설정 시 DNS rebinding 보호 활성(도메인 노출 방어)."""
    if not _ALLOWED:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_ALLOWED,
        allowed_origins=[f"https://{h}" for h in _ALLOWED] + [f"http://{h}" for h in _ALLOWED],
    )


class BearerAuthMiddleware:
    """순수 ASGI 미들웨어 — SSE 스트리밍을 버퍼링하지 않도록 BaseHTTPMiddleware 대신 사용.

    - MCP_AUTH_TOKEN 미설정: 통과(개방). 기동 시 경고 로그.
    - 설정: 'Authorization: Bearer <token>' 정확히 일치해야 통과. 불일치 시 401.
    - /healthz, OPTIONS(프리플라이트)는 인증 제외.
    """

    def __init__(self, app: ASGIApp, token: str | None, protect_prefix: str) -> None:
        self.app = app
        self.token = token
        self.protect_prefix = protect_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "")
        if method == "OPTIONS" or not path.startswith(self.protect_prefix):
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        expected = f"Bearer {self.token}"
        if auth != expected:
            await JSONResponse(
                {"error": "unauthorized", "detail": "유효한 Bearer 토큰이 필요합니다."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


# ---- MCP streamable_http 세션 매니저 (기존 low-level server 재사용) ----
session_manager = StreamableHTTPSessionManager(
    app=mcp_server.server,
    json_response=JSON_RESPONSE,
    stateless=False,
    security_settings=_security_settings(),
)


async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


async def healthz(request):
    return JSONResponse({"status": "ok", "tables": list_tables(), "mcp_path": MCP_PATH})


async def root(request):
    return PlainTextResponse(f"MCP streamable_http server. endpoint: {MCP_PATH}")


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    init_db()
    mcp_server.ensure_tools(force=True)  # 기동 시 1회 툴 빌드
    poll = float(os.environ.get("MCP_POLL_SECS", "0") or 0)  # HTTP는 재조회로 최신화 → 기본 폴러 off
    poller = None
    async with session_manager.run():  # streamable_http 세션 매니저 활성
        if poll > 0:
            async def _bg():
                while True:
                    await asyncio.sleep(poll)
                    with contextlib.suppress(Exception):
                        mcp_server.ensure_tools()
            poller = asyncio.create_task(_bg())
        try:
            yield
        finally:
            if poller is not None:
                poller.cancel()


app = Starlette(
    routes=[
        Route("/", root),
        Route("/healthz", healthz),
        Mount(MCP_PATH, app=handle_mcp),
    ],
    lifespan=lifespan,
)
app = BearerAuthMiddleware(app, token=AUTH_TOKEN, protect_prefix=MCP_PATH)


def main() -> None:
    import uvicorn

    # logging 은 대문자 레벨명(INFO)만, uvicorn 은 소문자(info)만 허용 → 분리 처리
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    host = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_HTTP_PORT", "8800"))
    certfile = os.environ.get("MCP_SSL_CERTFILE") or None
    keyfile = os.environ.get("MCP_SSL_KEYFILE") or None
    scheme = "https" if certfile and keyfile else "http"

    if not AUTH_TOKEN:
        logger.warning("MCP_AUTH_TOKEN 미설정 — 인증 없이 개방됩니다. 도메인 노출 시 반드시 설정하세요.")
    if scheme == "http" and host not in ("127.0.0.1", "localhost"):
        logger.warning("TLS 미설정 상태로 %s 바인딩. 도메인 노출은 리버스 프록시 또는 인증서 설정을 권장합니다.", host)
    logger.info("MCP streamable_http listening on %s://%s:%d%s", scheme, host, port, MCP_PATH)

    # 리버스 프록시 뒤에서 X-Forwarded-* 신뢰(스킴/클라이언트 IP 복원)
    fwd_ips = os.environ.get("MCP_FORWARDED_ALLOW_IPS", "*")
    uvicorn.run(
        app,
        host=host,
        port=port,
        ssl_certfile=certfile,
        ssl_keyfile=keyfile,
        proxy_headers=True,
        forwarded_allow_ips=fwd_ips,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
