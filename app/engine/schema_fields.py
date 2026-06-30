"""OpenAPI 응답 스키마 → 리턴 필드(JSONPath) 평탄화 + 예시 생성.

- 스펙 원문(raw dict)을 root 로 받아 `$ref`(#/components/schemas/.., #/definitions/..)를 해소.
- allOf 병합, 중첩 object/array 재귀(깊이/사이클 가드).
- fields: [{path, type, required}], example: 타입 기반 샘플 객체.
"""
from __future__ import annotations

import json
from typing import Any, Optional

try:
    import yaml  # 선택적(YAML 스펙 대비)
except Exception:  # pragma: no cover
    yaml = None

_MAX_DEPTH = 6


def load_spec(raw: str) -> dict:
    """raw 문자열(JSON 또는 YAML)을 dict 로."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        if yaml is not None:
            try:
                return yaml.safe_load(raw) or {}
            except Exception:
                return {}
        return {}


def resolve_ref(ref: str, root: dict) -> dict:
    """'#/components/schemas/Foo' 형태를 root 에서 따라가 dict 반환(실패 시 {})."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return {}
    cur: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return {}
    return cur if isinstance(cur, dict) else {}


def _deref(schema: Any, root: dict, seen: frozenset) -> tuple[dict, frozenset]:
    """$ref 를 해소하고 allOf 를 병합한 스키마 dict 반환."""
    if not isinstance(schema, dict):
        return {}, seen
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            return {}, seen
        seen = seen | {ref}
        schema = resolve_ref(ref, root)
        if not isinstance(schema, dict):
            return {}, seen
    if "allOf" in schema and isinstance(schema["allOf"], list):
        merged: dict = {"type": "object", "properties": {}, "required": []}
        for sub in schema["allOf"]:
            d, seen = _deref(sub, root, seen)
            if d.get("properties"):
                merged["properties"].update(d["properties"])
            if d.get("required"):
                merged["required"].extend(d["required"])
            if d.get("type"):
                merged["type"] = d["type"]
        # allOf 외 자체 properties 도 병합
        if schema.get("properties"):
            merged["properties"].update(schema["properties"])
        if schema.get("required"):
            merged["required"].extend(schema["required"])
        return merged, seen
    return schema, seen


def type_of(schema: Any, root: dict, seen: frozenset = frozenset()) -> str:
    d, _ = _deref(schema, root, seen)
    t = d.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if t:
        return t
    if d.get("properties"):
        return "object"
    if d.get("items"):
        return "array"
    return "any"


def flatten(schema: Any, root: dict, base: str = "$",
            seen: frozenset = frozenset(), depth: int = 0,
            out: Optional[list] = None) -> list:
    """리턴 필드 평탄화. [{path, type, required}]."""
    if out is None:
        out = []
    if depth > _MAX_DEPTH:
        return out
    d, seen = _deref(schema, root, seen)
    if not isinstance(d, dict):
        return out
    props = d.get("properties")
    if props:
        required = set(d.get("required") or [])
        for name, sub in props.items():
            path = base + "." + name
            out.append({"path": path, "type": type_of(sub, root, seen), "required": name in required})
            st = type_of(sub, root, seen)
            if st in ("object", "array"):
                flatten(sub, root, path, seen, depth + 1, out)
        return out
    if type_of(d, root, seen) == "array" and d.get("items"):
        flatten(d["items"], root, base + "[0]", seen, depth + 1, out)
    return out


def example_of(schema: Any, root: dict, seen: frozenset = frozenset(), depth: int = 0) -> Any:
    """타입 기반 예시 값 생성(깊이 제한)."""
    if depth > _MAX_DEPTH:
        return None
    d, seen = _deref(schema, root, seen)
    if not isinstance(d, dict):
        return None
    if "example" in d:
        return d["example"]
    if d.get("enum"):
        return d["enum"][0]
    t = type_of(d, root, seen)
    if t == "object" or d.get("properties"):
        return {k: example_of(v, root, seen, depth + 1) for k, v in (d.get("properties") or {}).items()}
    if t == "array":
        return [example_of(d.get("items") or {}, root, seen, depth + 1)]
    return {"string": "string", "integer": 0, "number": 0, "boolean": True}.get(t, None)


def response_fields(response_schema: Any, raw_spec: str) -> dict:
    """엔드포인트용: response_schema + 스펙 원문 → {fields, example, ref}."""
    root = load_spec(raw_spec)
    if not isinstance(response_schema, dict) or not response_schema:
        return {"fields": [], "example": None, "ref": None, "note": "응답 스키마가 정의되어 있지 않습니다."}
    ref = response_schema.get("$ref") if isinstance(response_schema, dict) else None
    fields = flatten(response_schema, root)
    example = example_of(response_schema, root)
    note = None
    if not fields:
        note = "구조화된 필드가 없습니다(원시 타입/미정의). 샘플 호출로 실제 값을 확인하세요."
    return {"fields": fields, "example": example, "ref": ref, "note": note}
