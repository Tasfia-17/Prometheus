"""Tests for SubgraphRetriever — BFS traversal and diff parsing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from graphrag.builder import OpenAPIGraph
from graphrag.retriever import SubgraphRetriever, _paths_match
from tests.test_builder import SIMPLE_SPEC


def make_retriever():
    return SubgraphRetriever(OpenAPIGraph.from_spec(SIMPLE_SPEC))


def test_for_endpoints_exact():
    r = make_retriever()
    ctx = r.for_endpoints(["GET /api/items"])
    assert "GET /api/items" in ctx.endpoints
    assert "ItemList" in ctx.schemas


def test_for_endpoints_collects_properties():
    r = make_retriever()
    ctx = r.for_endpoints(["POST /api/items"])
    assert "CreateItem" in ctx.schemas
    assert "Item" in ctx.schemas
    props = [p["name"] for p in ctx.schemas["Item"]["properties"]]
    assert "id" in props
    assert "name" in props


def test_for_endpoints_auth_detection():
    r = make_retriever()
    ctx = r.for_endpoints(["GET /api/items"])
    assert ctx.requires_auth is True


def test_for_endpoints_no_auth():
    r = make_retriever()
    ctx = r.for_endpoints(["POST /api/items"])
    assert ctx.requires_auth is False


def test_fuzzy_match():
    r = make_retriever()
    ctx = r.for_endpoints(["/api/items/{id}"])
    assert len(ctx.endpoints) == 1


def test_unknown_endpoint():
    r = make_retriever()
    ctx = r.for_endpoints(["GET /api/nonexistent"])
    assert ctx.endpoints == []


def test_endpoints_from_diff_fastapi():
    r = make_retriever()
    diff = """+@app.get("/api/items/{id}")
+def get_item(id: int):
+    pass
"""
    eps = r.endpoints_from_diff(diff)
    assert "GET /api/items/{id}" in eps


def test_endpoints_from_diff_express():
    r = make_retriever()
    diff = """+router.post('/api/items', requireAuth, (req, res) => {
+  res.json({});
+});
"""
    eps = r.endpoints_from_diff(diff)
    assert "POST /api/items" in eps


def test_endpoints_from_diff_added_lines_only():
    r = make_retriever()
    diff = """ @app.get("/api/items")  # context line (no +)
+@app.post("/api/items")
"""
    eps = r.endpoints_from_diff(diff)
    assert "POST /api/items" in eps
    # GET should not be matched (no + prefix)


def test_endpoints_from_diff_empty():
    r = make_retriever()
    eps = r.endpoints_from_diff("")
    assert eps == []


def test_paths_match_exact():
    assert _paths_match("/api/items", "/api/items") is True


def test_paths_match_param():
    assert _paths_match("/api/items/42", "/api/items/{id}") is True


def test_paths_match_express_param():
    assert _paths_match("/api/items/:id", "/api/items/{id}") is True


def test_paths_match_named_segment_no_match():
    # "search" should NOT match {id}
    assert _paths_match("/api/items/search", "/api/items/{id}") is False


def test_paths_match_different_length():
    assert _paths_match("/api/items", "/api/items/{id}") is False


def test_paths_match_uuid():
    assert _paths_match("/api/items/550e8400-e29b-41d4-a716-446655440000", "/api/items/{id}") is True


def test_to_text_output():
    r = make_retriever()
    ctx = r.for_endpoints(["POST /api/items"])
    text = ctx.to_text()
    assert "POST" in text
    assert "/api/items" in text
