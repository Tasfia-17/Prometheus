"""CLI: python -m graphrag --spec openapi.json --diff-stdin"""
import argparse
import json
import sys
from pathlib import Path
from .builder import OpenAPIGraph
from .retriever import SubgraphRetriever


def main():
    parser = argparse.ArgumentParser(description="OpenAPI GraphRAG — extract relevant schemas from a diff")
    parser.add_argument("--spec", required=True, help="Path to openapi.json")
    parser.add_argument("--diff-stdin", action="store_true", help="Read diff from stdin")
    parser.add_argument("--endpoint", action="append", default=[], help="Explicit endpoint (e.g. 'POST /api/foo')")
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text())
    graph = OpenAPIGraph.from_spec(spec)
    retriever = SubgraphRetriever(graph)

    stats = graph.stats()
    print(f"## GraphRAG Traversal\n")
    print(f"Graph: {stats['nodes']} nodes, {stats['edges']} edges")

    if args.diff_stdin:
        diff = sys.stdin.read()
        endpoints = retriever.endpoints_from_diff(diff)
    else:
        endpoints = args.endpoint

    if not endpoints:
        print("No changed endpoints detected in diff.")
        sys.exit(0)

    print(f"Matched endpoints: {len(endpoints)}\n")
    ctx = retriever.for_endpoints(endpoints)

    G = graph.graph
    for ep in ctx.endpoints:
        d = G.nodes[ep]
        print(f"  ● {d.get('method', '')} {d.get('path', '')}")
        if ctx.requires_auth:
            print(f"    ├─ AUTH → Bearer token required")
        for _, neighbor, edge_data in G.edges(ep, data=True):
            rel = edge_data.get("relation", "")
            if rel in ("ACCEPTS", "RETURNS"):
                nd = G.nodes[neighbor]
                label = "ACCEPTS" if rel == "ACCEPTS" else "RETURNS"
                print(f"    ├─ {label} → {neighbor} (schema)")
                schema_info = ctx.schemas.get(neighbor, {})
                for prop in schema_info.get("properties", []):
                    req = " *" if prop.get("required") else ""
                    print(f"    │  ├─ .{prop['name']}: {prop['type']}{req}")
            elif rel == "HAS_PARAM":
                nd = G.nodes[neighbor]
                if nd.get("name", "").lower() != "authorization":
                    print(f"    ├─ HAS_PARAM → {nd.get('name')} ({nd.get('location')})")
        print()

    schema_count = len(ctx.schemas)
    param_count = len(ctx.parameters)
    print(f"Retrieved: {schema_count} schemas, {param_count} params, auth={'yes' if ctx.requires_auth else 'no'}")


if __name__ == "__main__":
    main()
