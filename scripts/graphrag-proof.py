#!/usr/bin/env python3
"""A/B proof: GraphRAG context vs full OpenAPI spec.

Calls the IBM Bob / OpenAI-compatible API with both full spec and GraphRAG
context for the same endpoint, then compares schema field coverage and
hallucinated endpoint counts.

Usage:
    export OPENAI_API_KEY=<your-key>
    export OPENAI_BASE_URL=<optional, defaults to OpenAI>
    python3 scripts/graphrag-proof.py

Results are written to scripts/graphrag-proof-output.txt
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from graphrag.builder import OpenAPIGraph
from graphrag.retriever import SubgraphRetriever

try:
    from openai import OpenAI
except ImportError:
    print("openai package required: pip install openai", file=sys.stderr)
    sys.exit(1)

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY", ""),
    base_url=os.environ.get("OPENAI_BASE_URL", None),
)

DEMOS = Path(__file__).parent.parent / "demos"

SYSTEM_PROMPT = """You are a k6 load test generator. Given API context, list:
1. The endpoints you would test (as "METHOD /path" lines under "ENDPOINTS:")
2. The response fields you would validate for each endpoint (under "FIELDS:")
Be concise. Only list what the context tells you."""

TEST_CASES = [
    {
        "demo": "midas-bank",
        "endpoint": "POST /api/transactions/transfer",
        "diff": '+@app.post("/api/transactions/transfer")\n',
        "expected_fields": {"from_account_id", "to_account_id", "amount", "type", "id"},
    },
    {
        "demo": "calliope-books",
        "endpoint": "GET /api/books/search",
        "diff": '+app.get("/api/books/search", requireAuth, (req, res) => {\n',
        "expected_fields": {"books", "id", "title", "author"},
    },
    {
        "demo": "hestia-eats",
        "endpoint": "GET /api/orders/history",
        "diff": '+app.get("/api/orders/history", requireAuth, (c) => {\n',
        "expected_fields": {"orders", "total", "id", "status", "restaurant_id"},
    },
]


def call_llm(context: str, label: str) -> tuple[str, float]:
    t0 = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"API context:\n\n{context}\n\nList endpoints and fields."},
        ],
        max_tokens=400,
        temperature=0,
    )
    elapsed = time.time() - t0
    return resp.choices[0].message.content, elapsed


def score(response: str, expected_fields: set[str], all_endpoints: list[str], changed_endpoint: str) -> dict:
    text = response.lower()
    covered = sum(1 for f in expected_fields if f.lower() in text)
    # hallucinations: endpoints mentioned that aren't the changed one
    hallucinated = sum(
        1 for ep in all_endpoints
        if ep != changed_endpoint and ep.split(" ", 1)[-1].lower() in text
    )
    return {
        "field_coverage": f"{covered}/{len(expected_fields)}",
        "hallucinated_endpoints": hallucinated,
    }


def run():
    results = []
    for tc in TEST_CASES:
        spec = json.loads((DEMOS / tc["demo"] / "openapi.json").read_text())
        full_spec_text = json.dumps(spec, indent=2)
        full_tokens = len(full_spec_text) // 4

        g = OpenAPIGraph.from_spec(spec)
        r = SubgraphRetriever(g)
        eps = r.endpoints_from_diff(tc["diff"]) or [tc["endpoint"]]
        ctx = r.for_endpoints(eps)
        graphrag_text = ctx.to_text()
        graphrag_tokens = len(graphrag_text) // 4
        reduction = round((1 - graphrag_tokens / full_tokens) * 100, 1)

        all_endpoints = g.endpoints()

        print(f"\n{'='*60}")
        print(f"Test: {tc['demo']} — {tc['endpoint']}")
        print(f"Full spec: ~{full_tokens} tokens | GraphRAG: ~{graphrag_tokens} tokens | Reduction: {reduction}%")

        full_response, full_time = call_llm(full_spec_text, "full-spec")
        full_score = score(full_response, tc["expected_fields"], all_endpoints, tc["endpoint"])
        print(f"Full spec  → fields: {full_score['field_coverage']}, hallucinations: {full_score['hallucinated_endpoints']}, time: {full_time:.1f}s")

        graphrag_response, graphrag_time = call_llm(graphrag_text, "graphrag")
        graphrag_score = score(graphrag_response, tc["expected_fields"], all_endpoints, tc["endpoint"])
        print(f"GraphRAG   → fields: {graphrag_score['field_coverage']}, hallucinations: {graphrag_score['hallucinated_endpoints']}, time: {graphrag_time:.1f}s")

        results.append({
            "demo": tc["demo"],
            "endpoint": tc["endpoint"],
            "token_reduction_pct": reduction,
            "full_spec": {**full_score, "time_s": round(full_time, 2)},
            "graphrag": {**graphrag_score, "time_s": round(graphrag_time, 2)},
        })

    # Write output
    out = ["# GraphRAG A/B Proof Results\n",
           f"Model: {MODEL}\n",
           "| Demo | Endpoint | Token Reduction | Full Spec Fields | GraphRAG Fields | Full Hallucinations | GraphRAG Hallucinations |",
           "|---|---|---|---|---|---|---|"]
    for r in results:
        out.append(
            f"| {r['demo']} | {r['endpoint']} | {r['token_reduction_pct']}% "
            f"| {r['full_spec']['field_coverage']} | {r['graphrag']['field_coverage']} "
            f"| {r['full_spec']['hallucinated_endpoints']} | {r['graphrag']['hallucinated_endpoints']} |"
        )
    out_path = Path(__file__).parent / "graphrag-proof-output.txt"
    out_path.write_text("\n".join(out))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY (and optionally OPENAI_BASE_URL, OPENAI_MODEL)", file=sys.stderr)
        sys.exit(1)
    run()
