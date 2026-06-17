"""OpenAPI v2(Swagger) / v3 → 오퍼레이션 추출 (FastAPI 비의존).

계약(사양서 §4):
  parse_openapi(raw, source_hint) -> ParseResult
  base_url:
    - v3: servers[0].url (변수 기본값 치환)
    - v2: scheme://host + basePath
    - 없으면 None + warning
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")


@dataclass
class Operation:
    operation_id: Optional[str]
    method: str
    path: str
    base_url: Optional[str]
    summary: Optional[str]
    params_schema: Any = None
    request_schema: Any = None
    response_schema: Any = None
    auth: Any = None


@dataclass
class ParseResult:
    spec_version: str
    base_url: Optional[str]
    operations: list[Operation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _load(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        raise ValueError("빈 스펙입니다.")
    # JSON 우선 시도, 실패 시 YAML
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if yaml is None:
            raise ValueError("JSON 파싱 실패. YAML 지원을 위해 PyYAML 설치가 필요합니다.")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise ValueError("스펙 루트가 객체가 아닙니다.")
        return data


def _substitute_server_vars(url: str, variables: dict) -> str:
    """v3 servers[].variables 의 기본값으로 {var} 치환."""
    def repl(m: re.Match) -> str:
        name = m.group(1)
        var = variables.get(name) if isinstance(variables, dict) else None
        if isinstance(var, dict) and "default" in var:
            return str(var["default"])
        return m.group(0)

    return re.sub(r"\{([^}]+)\}", repl, url)


def _base_url_v3(spec: dict, warnings: list[str]) -> Optional[str]:
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        url = first.get("url") if isinstance(first, dict) else None
        if url:
            return _substitute_server_vars(url, (first or {}).get("variables", {})).rstrip("/")
    warnings.append("v3 스펙에 servers[0].url 이 없어 base_url 을 결정할 수 없습니다.")
    return None


def _base_url_v2(spec: dict, warnings: list[str]) -> Optional[str]:
    host = spec.get("host")
    base_path = spec.get("basePath", "") or ""
    schemes = spec.get("schemes") or []
    scheme = "https" if "https" in schemes else (schemes[0] if schemes else "https")
    if host:
        return f"{scheme}://{host}{base_path}".rstrip("/")
    warnings.append("v2 스펙에 host 가 없어 base_url 을 결정할 수 없습니다.")
    return None


def _extract_params(op: dict, path_item: dict) -> list[dict]:
    """path-level + operation-level 파라미터 병합."""
    params: list[dict] = []
    for src in (path_item.get("parameters", []), op.get("parameters", [])):
        if isinstance(src, list):
            params.extend(p for p in src if isinstance(p, dict))
    return params


def parse_openapi(raw: str, source_hint: Optional[str] = None) -> ParseResult:
    spec = _load(raw)
    warnings: list[str] = []

    swagger = spec.get("swagger")
    openapi = spec.get("openapi")
    if openapi:
        version = str(openapi)
        is_v3 = True
    elif swagger:
        version = str(swagger)
        is_v3 = False
    else:
        # 휴리스틱
        is_v3 = "components" in spec or "servers" in spec
        version = "3.0.0" if is_v3 else "2.0"
        warnings.append("스펙 버전 필드(openapi/swagger)가 없어 추정했습니다.")

    base_url = _base_url_v3(spec, warnings) if is_v3 else _base_url_v2(spec, warnings)

    operations: list[Operation] = []
    paths = spec.get("paths", {}) or {}
    if not paths:
        warnings.append("paths 가 비어 있습니다.")

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            params = _extract_params(op, path_item)

            request_schema = None
            if is_v3:
                rb = op.get("requestBody")
                if isinstance(rb, dict):
                    content = rb.get("content", {})
                    media = content.get("application/json") or (next(iter(content.values()), None) if content else None)
                    if isinstance(media, dict):
                        request_schema = media.get("schema")
            else:
                body_params = [p for p in params if p.get("in") == "body"]
                if body_params:
                    request_schema = body_params[0].get("schema")

            responses = op.get("responses", {}) or {}
            response_schema = None
            ok = responses.get("200") or responses.get("201") or next(iter(responses.values()), None)
            if isinstance(ok, dict):
                if is_v3:
                    content = ok.get("content", {})
                    media = content.get("application/json") or (next(iter(content.values()), None) if content else None)
                    if isinstance(media, dict):
                        response_schema = media.get("schema")
                else:
                    response_schema = ok.get("schema")

            operations.append(
                Operation(
                    operation_id=op.get("operationId"),
                    method=method.upper(),
                    path=path,
                    base_url=base_url,
                    summary=op.get("summary") or op.get("description"),
                    params_schema=[p for p in params if p.get("in") != "body"],
                    request_schema=request_schema,
                    response_schema=response_schema,
                    auth=op.get("security") or spec.get("security"),
                )
            )

    return ParseResult(
        spec_version=version,
        base_url=base_url,
        operations=operations,
        warnings=warnings,
    )
