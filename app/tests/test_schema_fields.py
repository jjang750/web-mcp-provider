import json
from engine import schema_fields as sf

SPEC = {
    "components": {
        "schemas": {
            "ImpoDetail": {
                "type": "object",
                "required": ["aptcd", "items"],
                "properties": {
                    "aptcd": {"type": "string"},
                    "yearmon": {"type": "string"},
                    "total": {"type": "integer"},
                    "items": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}},
                    "meta": {"$ref": "#/components/schemas/Meta"},
                },
            },
            "Item": {
                "type": "object",
                "properties": {"dong": {"type": "string"}, "amt": {"type": "number"}},
            },
            "Meta": {
                "allOf": [
                    {"type": "object", "properties": {"page": {"type": "integer"}}},
                    {"type": "object", "properties": {"size": {"type": "integer"}}},
                ]
            },
            "Node": {  # 사이클
                "type": "object",
                "properties": {"child": {"$ref": "#/components/schemas/Node"}, "name": {"type": "string"}},
            },
        }
    }
}
RAW = json.dumps(SPEC)


def _paths(fields):
    return [f["path"] for f in fields]


def test_resolve_ref():
    d = sf.resolve_ref("#/components/schemas/Item", SPEC)
    assert d["properties"]["dong"]["type"] == "string"


def test_flatten_nested_and_array_and_ref():
    top = {"$ref": "#/components/schemas/ImpoDetail"}
    fields = sf.flatten(top, SPEC)
    paths = _paths(fields)
    assert "$.aptcd" in paths
    assert "$.items" in paths
    assert "$.items[0].dong" in paths
    assert "$.items[0].amt" in paths
    assert "$.meta.page" in paths and "$.meta.size" in paths  # allOf 병합
    req = {f["path"]: f["required"] for f in fields}
    assert req["$.aptcd"] is True and req["$.yearmon"] is False


def test_cycle_guard():
    top = {"$ref": "#/components/schemas/Node"}
    fields = sf.flatten(top, SPEC)  # 무한루프 없이 반환
    assert "$.name" in _paths(fields)


def test_example_generation():
    ex = sf.example_of({"$ref": "#/components/schemas/ImpoDetail"}, SPEC)
    assert ex["aptcd"] == "string" and ex["total"] == 0
    assert isinstance(ex["items"], list) and ex["items"][0]["dong"] == "string"


def test_response_fields_empty():
    out = sf.response_fields(None, RAW)
    assert out["fields"] == [] and out["note"]


def test_response_fields_full():
    out = sf.response_fields({"$ref": "#/components/schemas/ImpoDetail"}, RAW)
    assert "$.items[0].dong" in _paths(out["fields"])
    assert out["example"]["aptcd"] == "string"
