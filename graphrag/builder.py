"""Build a directed graph from an OpenAPI 3.x spec.

Nodes: endpoints, schemas, properties, parameters, security schemes.
Edges: RETURNS, ACCEPTS, HAS_PROPERTY, REFERENCES, REQUIRES_AUTH, HAS_PARAM.
"""
from __future__ import annotations
from .digraph import DiGraph


class OpenAPIGraph:
    """Deterministic knowledge graph built from an OpenAPI spec."""

    def __init__(self, graph: DiGraph):
        self.graph = graph

    @classmethod
    def from_spec(cls, spec: dict) -> OpenAPIGraph:
        G = DiGraph()
        schemas = spec.get("components", {}).get("schemas", {})
        security_schemes = spec.get("components", {}).get("securitySchemes", {})

        for name, scheme in security_schemes.items():
            G.add_node(f"security:{name}", type="security",
                       scheme_type=scheme.get("type", ""), scheme=scheme.get("scheme", ""))

        for schema_name, schema_def in schemas.items():
            G.add_node(schema_name, type="schema", required=schema_def.get("required", []))
            _add_properties(G, schema_name, schema_def, schemas)

        for path, path_item in spec.get("paths", {}).items():
            for method in ("get", "post", "put", "patch", "delete"):
                if method not in path_item:
                    continue
                op = path_item[method]
                node_id = f"{method.upper()} {path}"
                G.add_node(node_id, type="endpoint", method=method.upper(), path=path,
                           summary=op.get("summary", ""), operation_id=op.get("operationId", ""))

                for content in op.get("requestBody", {}).get("content", {}).values():
                    ref = _resolve_ref(content.get("schema", {}))
                    if ref and ref in schemas:
                        G.add_edge(node_id, ref, relation="ACCEPTS")

                for resp in op.get("responses", {}).values():
                    for content in resp.get("content", {}).values():
                        ref = _resolve_ref(content.get("schema", {}))
                        if ref and ref in schemas:
                            G.add_edge(node_id, ref, relation="RETURNS")

                params = op.get("parameters", []) + path_item.get("parameters", [])
                for param in params:
                    param_id = f"{node_id}:param:{param['name']}"
                    G.add_node(param_id, type="parameter", name=param["name"],
                               location=param.get("in", ""),
                               param_type=param.get("schema", {}).get("type", ""),
                               required=param.get("required", False))
                    G.add_edge(node_id, param_id, relation="HAS_PARAM")

                for sec_req in op.get("security", []):
                    for sec_name in sec_req:
                        sec_node = f"security:{sec_name}"
                        if G.has_node(sec_node):
                            G.add_edge(node_id, sec_node, relation="REQUIRES_AUTH")

        return cls(G)

    def endpoints(self) -> list[str]:
        return [n for n, d in self.graph.nodes(data=True) if d.get("type") == "endpoint"]

    def schemas(self) -> list[str]:
        return [n for n, d in self.graph.nodes(data=True) if d.get("type") == "schema"]

    def has_node(self, node_id: str) -> bool:
        return self.graph.has_node(node_id)

    def stats(self) -> dict:
        return {
            "endpoints": len(self.endpoints()),
            "schemas": len(self.schemas()),
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }


def _resolve_ref(schema: dict) -> str | None:
    ref = schema.get("$ref", "")
    if ref.startswith("#/components/schemas/"):
        return ref.split("/")[-1]
    return None


def _add_properties(G: DiGraph, schema_name: str, schema_def: dict, all_schemas: dict) -> None:
    properties = dict(schema_def.get("properties", {}))

    for sub in schema_def.get("allOf", []):
        ref = _resolve_ref(sub)
        if ref and ref in all_schemas:
            G.add_edge(schema_name, ref, relation="REFERENCES")
        elif "properties" in sub:
            properties.update(sub["properties"])

    required = schema_def.get("required", [])
    for prop_name, prop_def in properties.items():
        prop_node = f"{schema_name}.{prop_name}"
        prop_type = prop_def.get("type", "")
        if not prop_type and "anyOf" in prop_def:
            prop_type = "|".join(t.get("type", "?") for t in prop_def["anyOf"] if isinstance(t, dict))

        ref = _resolve_ref(prop_def)
        if ref and ref in all_schemas:
            G.add_node(prop_node, type="property", name=prop_name, property_type=f"$ref:{ref}",
                       required=prop_name in required)
            G.add_edge(schema_name, prop_node, relation="HAS_PROPERTY")
            G.add_edge(schema_name, ref, relation="REFERENCES")
            continue

        items = prop_def.get("items", {})
        item_ref = _resolve_ref(items)
        if item_ref and item_ref in all_schemas:
            G.add_node(prop_node, type="property", name=prop_name,
                       property_type=f"array<{item_ref}>", required=prop_name in required)
            G.add_edge(schema_name, prop_node, relation="HAS_PROPERTY")
            G.add_edge(schema_name, item_ref, relation="REFERENCES")
            continue

        G.add_node(prop_node, type="property", name=prop_name,
                   property_type=prop_type, required=prop_name in required)
        G.add_edge(schema_name, prop_node, relation="HAS_PROPERTY")
