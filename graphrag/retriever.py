"""Subgraph retrieval — extract relevant API context for changed endpoints."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from .builder import OpenAPIGraph


@dataclass
class RetrievedContext:
    endpoints: list[str] = field(default_factory=list)
    schemas: dict[str, dict] = field(default_factory=dict)
    parameters: list[dict] = field(default_factory=list)
    requires_auth: bool = False
    _graph: OpenAPIGraph | None = field(default=None, repr=False)

    def to_text(self) -> str:
        lines = []
        for ep in self.endpoints:
            G = self._graph.graph if self._graph else None
            if G and G.has_node(ep):
                d = G.nodes[ep]
                lines.append(f"## {d.get('method', '')} {d.get('path', '')}")
                if d.get("summary"):
                    lines.append(f"Summary: {d['summary']}")
            else:
                lines.append(f"## {ep}")

        if self.requires_auth:
            lines.append("\nAuthentication: Bearer token required")

        if self.parameters:
            lines.append("\nParameters:")
            for p in self.parameters:
                req = " (required)" if p.get("required") else ""
                lines.append(f"  - {p['name']}: {p.get('type', 'string')} in {p.get('in', 'query')}{req}")

        if self.schemas:
            lines.append("\nSchemas:")
            for name, info in self.schemas.items():
                lines.append(f"\n### {name}")
                for prop in info.get("properties", []):
                    req = " *" if prop.get("required") else ""
                    lines.append(f"  - {prop['name']}: {prop['type']}{req}")

        return "\n".join(lines)


class SubgraphRetriever:
    def __init__(self, graph: OpenAPIGraph):
        self.graph = graph

    def for_endpoints(self, endpoint_ids: list[str]) -> RetrievedContext:
        G = self.graph.graph
        found, all_schemas, all_params, needs_auth = [], {}, [], False

        for ep_id in endpoint_ids:
            if not G.has_node(ep_id):
                ep_id = self._fuzzy_match(ep_id) or ""
            if not ep_id:
                continue
            found.append(ep_id)

            for _, neighbor, edge_data in G.edges(ep_id, data=True):
                rel = edge_data.get("relation", "")
                if rel == "REQUIRES_AUTH":
                    needs_auth = True
                elif rel == "HAS_PARAM":
                    pd = G.nodes[neighbor]
                    if pd.get("name", "").lower() == "authorization" and pd.get("location") == "header":
                        needs_auth = True
                    all_params.append({"name": pd.get("name", ""), "type": pd.get("param_type", "string"),
                                       "in": pd.get("location", "query"), "required": pd.get("required", False)})
                elif rel in ("ACCEPTS", "RETURNS"):
                    self._collect_schema(neighbor, all_schemas, depth=2)

        return RetrievedContext(endpoints=found, schemas=all_schemas,
                                parameters=all_params, requires_auth=needs_auth, _graph=self.graph)

    def endpoints_from_diff(self, diff: str) -> list[str]:
        G = self.graph.graph
        known_paths = {G.nodes[ep]["path"]: ep for ep in self.graph.endpoints()}

        added = "\n".join(
            line[1:] for line in diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        for text in [added, diff]:
            found = self._match_in_text(text, known_paths)
            if found:
                return list(found)
        return []

    def _match_in_text(self, text: str, known_paths: dict) -> set[str]:
        found = set()
        # FastAPI / Flask decorators
        for m in re.finditer(r'@(?:app|router)\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)', text):
            method, path = m.group(1).upper(), m.group(2)
            ep_id = f"{method} {path}"
            if ep_id in known_paths.values():
                found.add(ep_id)
            else:
                for kp, kep in known_paths.items():
                    if _paths_match(path, kp):
                        found.add(kep)
        # Express / Hono
        for m in re.finditer(r'(?:router|app)\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)', text):
            method, path = m.group(1).upper(), m.group(2)
            for kp, kep in known_paths.items():
                if _paths_match(path, kp):
                    found.add(kep)
        # Fallback: any quoted /api/ path
        if not found:
            for m in re.finditer(r'["\'](/api/[^"\']+)["\']', text):
                for kp, kep in known_paths.items():
                    if _paths_match(m.group(1), kp):
                        found.add(kep)
        return found

    def _collect_schema(self, schema_name: str, collected: dict, depth: int) -> None:
        if schema_name in collected or depth <= 0:
            return
        G = self.graph.graph
        if not G.has_node(schema_name) or G.nodes[schema_name].get("type") != "schema":
            return

        required = G.nodes[schema_name].get("required", [])
        properties = []
        for _, neighbor, edge_data in G.edges(schema_name, data=True):
            rel = edge_data.get("relation", "")
            if rel == "HAS_PROPERTY":
                pd = G.nodes[neighbor]
                prop_name = pd.get("name", neighbor.split(".")[-1])
                properties.append({"name": prop_name, "type": pd.get("property_type", ""),
                                    "required": prop_name in required})
            elif rel == "REFERENCES":
                self._collect_schema(neighbor, collected, depth - 1)
        collected[schema_name] = {"properties": properties}

    def _fuzzy_match(self, query: str) -> str | None:
        for ep in self.graph.endpoints():
            if query in ep:
                return ep
        return None


def _paths_match(actual: str, template: str) -> bool:
    actual = re.sub(r':(\w+)', r'{\1}', actual.rstrip("/"))
    template = template.rstrip("/")
    if actual == template:
        return True
    ap, tp = actual.split("/"), template.split("/")
    if len(ap) != len(tp):
        return False
    for a, t in zip(ap, tp):
        if a == t:
            continue
        if t.startswith("{") and t.endswith("}"):
            if a.startswith("{") and a.endswith("}"):
                continue
            if re.fullmatch(r'\d+', a):
                continue
            if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', a, re.I):
                continue
            return False
        else:
            return False
    return True
