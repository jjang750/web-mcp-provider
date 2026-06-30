import pytest

from engine import http_client


def test_base_url_priority_node_first():
    assert http_client.resolve_base_url("http://a", "http://b", "http://c") == "http://a"


def test_base_url_priority_operation_second():
    assert http_client.resolve_base_url(None, "http://b", "http://c") == "http://b"


def test_base_url_priority_default_last():
    assert http_client.resolve_base_url(None, None, "http://c") == "http://c"


def test_protocol_guard_rejects_schemeless():
    with pytest.raises(http_client.ProtocolError):
        http_client.build_url("localhost:8000", "/x")


def test_build_url_joins_path():
    assert http_client.build_url("http://h/api", "/items") == "http://h/api/items"
    assert http_client.build_url("http://h/api/", "items") == "http://h/api/items"


def test_apply_auth_bearer():
    headers, params = {}, {}
    http_client._apply_auth({"type": "bearer", "token": "T"}, headers, params)
    assert headers["Authorization"] == "Bearer T"


def test_apply_auth_apikey_query():
    headers, params = {}, {}
    http_client._apply_auth(
        {"type": "apikey", "name": "api_key", "value": "K", "location": "query"}, headers, params
    )
    assert params["api_key"] == "K"
