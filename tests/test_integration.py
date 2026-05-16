"""Integration tests — spec → graph → retrieval → text output."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from graphrag.builder import OpenAPIGraph
from graphrag.retriever import SubgraphRetriever

DEMOS = Path(__file__).parent.parent / "demos"


def load_spec(name: str) -> dict:
    return json.loads((DEMOS / name / "openapi.json").read_text())


def test_midas_graph_stats():
    spec = load_spec("midas-bank")
    g = OpenAPIGraph.from_spec(spec)
    s = g.stats()
    assert s["endpoints"] >= 5
    assert s["schemas"] >= 3
    assert s["nodes"] > 10
    assert s["edges"] > 10


def test_midas_transfer_retrieval():
    spec = load_spec("midas-bank")
    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    ctx = r.for_endpoints(["POST /api/transactions/transfer"])
    assert len(ctx.endpoints) == 1
    assert len(ctx.schemas) >= 1
    assert ctx.requires_auth is True


def test_midas_diff_parsing():
    spec = load_spec("midas-bank")
    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    diff = """+@app.post("/api/transactions/transfer", status_code=201)
+def transfer(req: TransferRequest, auth=Depends(require_auth)):
"""
    eps = r.endpoints_from_diff(diff)
    assert len(eps) >= 1
    assert any("transfer" in ep for ep in eps)


def test_midas_token_reduction():
    """GraphRAG context should be much smaller than full spec."""
    spec = load_spec("midas-bank")
    full_spec_tokens = len(json.dumps(spec)) // 4  # rough token estimate

    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    ctx = r.for_endpoints(["POST /api/transactions/transfer"])
    graphrag_tokens = len(ctx.to_text()) // 4

    reduction = 1 - (graphrag_tokens / full_spec_tokens)
    assert reduction > 0.80, f"Expected >80% reduction, got {reduction:.1%}"


def test_calliope_search_endpoint():
    spec = load_spec("calliope-books")
    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    ctx = r.for_endpoints(["GET /api/books/search"])
    assert len(ctx.endpoints) == 1


def test_calliope_diff_parsing():
    spec = load_spec("calliope-books")
    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    diff = """+app.get('/api/books/search', requireAuth, (req, res) => {
+  res.json({ books: [] });
+});
"""
    eps = r.endpoints_from_diff(diff)
    assert any("search" in ep for ep in eps)


def test_hestia_history_endpoint():
    spec = load_spec("hestia-eats")
    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    ctx = r.for_endpoints(["GET /api/orders/history"])
    assert len(ctx.endpoints) == 1
    assert "OrderHistory" in ctx.schemas


def test_hestia_order_schemas():
    spec = load_spec("hestia-eats")
    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    ctx = r.for_endpoints(["POST /api/orders"])
    assert "CreateOrder" in ctx.schemas or "Order" in ctx.schemas


def test_no_hallucinated_endpoints():
    """Retrieved endpoints must exist in the spec."""
    for demo in ["midas-bank", "calliope-books", "hestia-eats"]:
        spec = load_spec(demo)
        g = OpenAPIGraph.from_spec(spec)
        r = SubgraphRetriever(g)
        known = set(g.endpoints())
        for ep in g.endpoints():
            ctx = r.for_endpoints([ep])
            for found_ep in ctx.endpoints:
                assert found_ep in known, f"Hallucinated endpoint: {found_ep}"


def test_all_specs_parse_without_error():
    for demo in ["midas-bank", "calliope-books", "hestia-eats"]:
        spec = load_spec(demo)
        g = OpenAPIGraph.from_spec(spec)
        assert g.stats()["nodes"] > 0


def test_context_to_text_contains_schemas():
    spec = load_spec("midas-bank")
    g = OpenAPIGraph.from_spec(spec)
    r = SubgraphRetriever(g)
    ctx = r.for_endpoints(["POST /api/transactions/transfer"])
    text = ctx.to_text()
    assert "POST" in text
    assert "/api/transactions/transfer" in text
    assert "Schemas:" in text
