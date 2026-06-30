from __future__ import annotations
import os
from typing import Any, Optional
from urllib.parse import urljoin
import httpx

DEFAULT_BASE_URL = os.environ.get("MCP_DEFAULT_BASE_URL", "http://localhost:8000")
TRUST_ENV = os.environ.get("MCP_HTTP_TRUST_ENV", "0") == "1"


class ProtocolError(ValueError):
    pass


def resolve_base_url(node_base_url, operation_base_url, default=DEFAULT_BASE_URL):
    return node_base_url or operation_base_url or default


def _guard_protocol(url):
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ProtocolError(f"요청 URL에 http:// 또는 https:// 스킴이 없습니다: '{url}'.")


def build_url(base_url, path):
    _guard_protocol(base_url)
    base = base_url if base_url.endswith("/") else base_url + "/"
    rel = path[1:] if path.startswith("/") else path
    return urljoin(base, rel)


def _apply_auth(auth, headers, params):
    if not auth:
        return
    t = auth.get("type")
    if t == "bearer" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif t == "basic":
        import base64
        enc = base64.b64encode(f"{auth.get('username','')}:{auth.get('password','')}".encode()).decode()
        headers["Authorization"] = f"Basic {enc}"
    elif t == "apikey":
        name = auth.get("name") or auth.get("key") or "X-API-Key"
        value = auth.get("value") or auth.get("token")
        if value:
            if auth.get("location") == "query":
                params[name] = value
            else:
                headers[name] = value


def preview(method, base_url, path, *, path_params=None, query=None, header=None, body=None, auth=None):
    """실제 전송 없이 호출 계획(method·url·query·header·body)을 해석해 반환(dry-run 미리보기용).

    보안: 인증 시크릿은 노출하지 않고 type 만 'auth_type' 으로 표기한다.
    """
    url = build_url(base_url, path)
    if path_params:
        for k, v in path_params.items():
            url = url.replace(f"{{{k}}}", str(v))
    _guard_protocol(url)
    return {
        "method": method.upper(),
        "url": url,
        "query": dict(query) if query else None,
        "header": dict(header) if header else None,
        "body": body if body not in (None, "") else None,
        "auth_type": (auth or {}).get("type"),
    }


def call(method, base_url, path, *, path_params=None, query=None, header=None, body=None, auth=None, timeout=30.0, client=None):
    url = build_url(base_url, path)
    if path_params:
        for k, v in path_params.items():
            url = url.replace(f"{{{k}}}", str(v))
    _guard_protocol(url)
    headers = dict(header or {})
    params = dict(query or {})
    _apply_auth(auth, headers, params)
    owns = client is None
    cli = client or httpx.Client(timeout=timeout, trust_env=TRUST_ENV)
    try:
        resp = cli.request(method.upper(), url, params=params or None, headers=headers or None, json=body if body not in (None, "") else None)
        try:
            parsed = resp.json()
        except Exception:
            parsed = resp.text
        return {"status_code": resp.status_code, "headers": dict(resp.headers), "body": parsed}
    finally:
        if owns:
            cli.close()
