from engine.parser import parse_openapi

V3 = """
{
  "openapi": "3.0.1",
  "info": {"title": "t", "version": "1"},
  "servers": [{"url": "https://api.example.com/v1"}],
  "paths": {
    "/users/{id}": {
      "get": {
        "operationId": "getUser",
        "summary": "사용자 조회",
        "parameters": [{"name": "id", "in": "path", "required": true, "schema": {"type": "integer"}}],
        "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"type": "object"}}}}}
      }
    }
  }
}
"""

V3_VARS = """
{
  "openapi": "3.0.0",
  "servers": [{"url": "https://{host}/v2", "variables": {"host": {"default": "svc.example.com"}}}],
  "paths": {}
}
"""

V2 = """
{
  "swagger": "2.0",
  "host": "legacy.example.com",
  "basePath": "/api",
  "schemes": ["https", "http"],
  "paths": {
    "/items": {
      "post": {
        "operationId": "createItem",
        "summary": "아이템 생성",
        "parameters": [{"name": "body", "in": "body", "schema": {"type": "object"}}],
        "responses": {"200": {"schema": {"type": "object"}}}
      }
    }
  }
}
"""


def test_v3_base_url_and_operation():
    res = parse_openapi(V3)
    assert res.spec_version.startswith("3")
    assert res.base_url == "https://api.example.com/v1"
    assert len(res.operations) == 1
    op = res.operations[0]
    assert op.method == "GET" and op.path == "/users/{id}"
    assert op.operation_id == "getUser"
    assert op.base_url == "https://api.example.com/v1"


def test_v3_server_variable_substitution():
    res = parse_openapi(V3_VARS)
    assert res.base_url == "https://svc.example.com/v2"


def test_v2_base_url_scheme_host_basepath():
    res = parse_openapi(V2)
    assert res.spec_version == "2.0"
    assert res.base_url == "https://legacy.example.com/api"
    op = res.operations[0]
    assert op.method == "POST" and op.path == "/items"
    assert op.request_schema == {"type": "object"}


def test_missing_servers_warns():
    res = parse_openapi('{"openapi":"3.0.0","paths":{}}')
    assert res.base_url is None
    assert any("servers" in w for w in res.warnings)
