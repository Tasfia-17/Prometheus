"""Tests for GraphRAG builder — graph construction from OpenAPI specs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from graphrag.builder import OpenAPIGraph
from graphrag.digraph import DiGraph

SIMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test", "version": "1.0"},
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                }
            },
            "CreateItem": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}, "price": {"type": "number"}}
            },
            "ItemList": {
                "type": "object",
                "properties": {"items": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}}}
            }
        },
        "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    },
    "paths": {
        "/api/items": {
            "get": {
                "operationId": "listItems",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ItemList"}}}}}
            },
            "post": {
                "operationId": "createItem",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateItem"}}}},
                "responses": {"201": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}}}
            }
        },
        "/api/items/{id}": {
            "get": {
                "operationId": "getItem",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}},
                    "404": {"description": "Not found"}
                }
            }
        }
    }
}


def test_graph_has_endpoints():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    eps = g.endpoints()
    assert "GET /api/items" in eps
    assert "POST /api/items" in eps
    assert "GET /api/items/{id}" in eps
    assert len(eps) == 3


def test_graph_has_schemas():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    schemas = g.schemas()
    assert "Item" in schemas
    assert "CreateItem" in schemas
    assert "ItemList" in schemas


def test_returns_edge():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    edges = {(u, v, d["relation"]) for u, v, d in G.edges(data=True)}
    assert ("GET /api/items", "ItemList", "RETURNS") in edges
    assert ("POST /api/items", "Item", "RETURNS") in edges


def test_accepts_edge():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    edges = {(u, v, d["relation"]) for u, v, d in G.edges(data=True)}
    assert ("POST /api/items", "CreateItem", "ACCEPTS") in edges


def test_has_property_edges():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    prop_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "HAS_PROPERTY"]
    prop_targets = [v for _, v in prop_edges]
    assert "Item.id" in prop_targets
    assert "Item.name" in prop_targets
    assert "Item.price" in prop_targets


def test_references_edge_for_array():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    edges = {(u, v, d["relation"]) for u, v, d in G.edges(data=True)}
    assert ("ItemList", "Item", "REFERENCES") in edges


def test_requires_auth_edge():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    edges = {(u, v, d["relation"]) for u, v, d in G.edges(data=True)}
    assert ("GET /api/items", "security:bearerAuth", "REQUIRES_AUTH") in edges


def test_has_param_edge():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    param_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "HAS_PARAM"]
    param_targets = [v for _, v in param_edges]
    assert any("id" in t for t in param_targets)


def test_stats():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    s = g.stats()
    assert s["endpoints"] == 3
    assert s["schemas"] == 3
    assert s["nodes"] > 0
    assert s["edges"] > 0


def test_empty_spec():
    g = OpenAPIGraph.from_spec({"openapi": "3.0.0", "info": {}, "paths": {}})
    assert g.endpoints() == []
    assert g.schemas() == []


def test_property_types():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    id_node = G.nodes.get("Item.id", {})
    assert id_node.get("property_type") == "integer"
    name_node = G.nodes.get("Item.name", {})
    assert name_node.get("property_type") == "string"


def test_required_fields():
    g = OpenAPIGraph.from_spec(SIMPLE_SPEC)
    G = g.graph
    schema_node = G.nodes["Item"]
    assert "id" in schema_node.get("required", [])
    assert "name" in schema_node.get("required", [])


def test_midas_spec():
    spec_path = Path(__file__).parent.parent / "demos/midas-bank/openapi.json"
    if not spec_path.exists():
        return  # skip if not built yet
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    assert len(g.endpoints()) > 0
    assert len(g.schemas()) > 0


def test_calliope_spec():
    spec_path = Path(__file__).parent.parent / "demos/calliope-books/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    assert "GET /api/books" in g.endpoints()
    assert "GET /api/books/search" in g.endpoints()


def test_hestia_spec():
    spec_path = Path(__file__).parent.parent / "demos/hestia-eats/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    assert len(g.endpoints()) >= 9


def test_midas_new_endpoints():
    spec_path = Path(__file__).parent.parent / "demos/midas-bank/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    eps = g.endpoints()
    assert "POST /api/transactions/withdraw" in eps
    assert "GET /api/accounts/summary" in eps


def test_calliope_new_endpoints():
    spec_path = Path(__file__).parent.parent / "demos/calliope-books/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    eps = g.endpoints()
    assert "GET /api/books/suggestions" in eps
    assert "GET /api/books/genre/{genre}" in eps


def test_hestia_new_endpoints():
    spec_path = Path(__file__).parent.parent / "demos/hestia-eats/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    eps = g.endpoints()
    assert "GET /api/restaurants/search" in eps
    assert "DELETE /api/orders/{id}" in eps


def test_allof_schema():
    spec = {
        "openapi": "3.0.0", "info": {}, "paths": {},
        "components": {"schemas": {
            "Base": {"type": "object", "properties": {"id": {"type": "integer"}}},
            "Extended": {"allOf": [
                {"$ref": "#/components/schemas/Base"},
                {"properties": {"name": {"type": "string"}}}
            ]}
        }}
    }
    g = OpenAPIGraph.from_spec(spec)
    assert g.graph.has_edge("Extended", "Base")


def test_anyof_property_type():
    spec = {
        "openapi": "3.0.0", "info": {}, "paths": {},
        "components": {"schemas": {
            "Item": {"type": "object", "properties": {
                "value": {"anyOf": [{"type": "string"}, {"type": "integer"}]}
            }}
        }}
    }
    g = OpenAPIGraph.from_spec(spec)
    prop = g.graph.nodes.get("Item.value", {})
    assert "string" in prop.get("property_type", "") or "integer" in prop.get("property_type", "")


def test_multiple_response_schemas():
    spec = {
        "openapi": "3.0.0", "info": {}, "paths": {
            "/api/items": {"get": {
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ItemList"}}}},
                    "404": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}
                }
            }}
        },
        "components": {"schemas": {
            "ItemList": {"type": "object", "properties": {"items": {"type": "array"}}},
            "Error": {"type": "object", "properties": {"detail": {"type": "string"}}}
        }}
    }
    g = OpenAPIGraph.from_spec(spec)
    edges = {(u, v, d["relation"]) for u, v, d in g.graph.edges(data=True)}
    assert ("GET /api/items", "ItemList", "RETURNS") in edges
    assert ("GET /api/items", "Error", "RETURNS") in edges



def test_midas_new_endpoints():
    spec_path = Path(__file__).parent.parent / "demos/midas-bank/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    eps = g.endpoints()
    assert "POST /api/transactions/withdraw" in eps
    assert "GET /api/accounts/summary" in eps


def test_calliope_new_endpoints():
    spec_path = Path(__file__).parent.parent / "demos/calliope-books/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    eps = g.endpoints()
    assert "GET /api/books/suggestions" in eps
    assert "GET /api/books/genre/{genre}" in eps


def test_hestia_new_endpoints():
    spec_path = Path(__file__).parent.parent / "demos/hestia-eats/openapi.json"
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    g = OpenAPIGraph.from_spec(spec)
    eps = g.endpoints()
    assert "GET /api/restaurants/search" in eps
    assert "DELETE /api/orders/{id}" in eps
