"""PostgreSQL 18 Apache AGE projection adapter.

Only this adapter contains AGE/Cypher syntax.  The shared Graph service stays
portable and can later be paired with a PostgreSQL 19 native adapter.
"""

from typing import Any, Dict, List, Optional, Tuple

try:
    from .graph_predicate import compile_safe_predicate, state_ref
except ImportError:  # source-tree adapter probe
    from lib.graph_predicate import compile_safe_predicate, state_ref

NATIVE_GRAPH_NAME = "ai_execution_graph"


def _literal(value: Any) -> str:
    text = str(value or "").replace("\\", "\\\\").replace("'", "\\'")
    return "'" + text + "'"


def _dollar_quote(value: str) -> str:
    """Render AGE's cstring query argument without using an unsafe bind.

    Apache AGE requires the Cypher argument to ``cypher()`` to be a
    dollar-quoted SQL constant.  Choose a tag absent from the generated
    statement so user-controlled node identifiers cannot terminate it.
    """
    for tag in ("ai_graph", "ai_graph_2", "ai_graph_3", "ai_graph_4"):
        marker = f"${tag}$"
        if marker not in value:
            return f"{marker}{value}{marker}"
    raise ValueError("Cypher statement contains an unsupported dollar-quote marker")


def projection_statements(version_id: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    # AGE resolves graphid operator classes through the session search path;
    # connection pools must establish it for every projection transaction.
    statements: List[Tuple[str, Optional[Dict[str, Any]]]] = [
        ("SET LOCAL search_path = public, ag_catalog", None),
    ]
    for node in nodes:
        node_id = str(node.get("node_id") or node.get("id") or "")
        node_key = str(node.get("node_key") or node.get("id") or "")
        node_type = str(node.get("node_type") or node.get("type") or "CONTROL")
        cypher = (
            "CREATE (n:graph_node {node_id: %s, graph_version_id: %s, node_key: %s, node_type: %s})"
            % (_literal(node_id), _literal(version_id), _literal(node_key), _literal(node_type))
        )
        statements.append((
            "SELECT * FROM ag_catalog.cypher(:graph_name, "
            + _dollar_quote(cypher)
            + ") AS (result ag_catalog.agtype)",
            {"graph_name": NATIVE_GRAPH_NAME},
        ))
    node_map = {str(node.get("node_key") or node.get("id")): str(node.get("node_id") or node.get("id")) for node in nodes}
    for edge in edges:
        source = str(edge.get("source_node_key") or "")
        target = str(edge.get("target_node_key") or "")
        if source not in node_map or target not in node_map:
            continue
        cypher = (
            "MATCH (a:graph_node {node_id: %s}), (b:graph_node {node_id: %s}) "
            "CREATE (a)-[:graph_edge {edge_id: %s, graph_version_id: %s, edge_kind: %s}]->(b)"
            % (_literal(node_map[source]), _literal(node_map[target]),
               _literal(edge.get("edge_id") or ""), _literal(version_id),
               _literal(edge.get("edge_kind") or "NORMAL"))
        )
        statements.append((
            "SELECT * FROM ag_catalog.cypher(:graph_name, "
            + _dollar_quote(cypher)
            + ") AS (result ag_catalog.agtype)",
            {"graph_name": NATIVE_GRAPH_NAME},
        ))
    return statements


def capability_probe() -> Dict[str, Any]:
    return {
        "native_graph": True, "graph_name": NATIVE_GRAPH_NAME, "adapter": "postgresql-age",
        "future_native": "postgresql-19",
        "predicate_pushdown": {"dialect": "postgresql-jsonb", "fallback": "portable-evaluator"},
    }


def compile_predicate(expression: Any) -> Dict[str, Any]:
    """Compile safe state predicates for PostgreSQL JSONB/AGE-backed rows."""
    def resolve(ref: str) -> Optional[str]:
        parts = state_ref(ref)
        if not parts:
            return None
        path = "{" + ",".join(parts) + "}"
        return "(STATE_JSON::jsonb #>> '" + path + "')"

    return compile_safe_predicate(
        expression, dialect="postgresql-jsonb", resolve_ref=resolve,
        placeholder=lambda name: "%(" + name + ")s",
    )
