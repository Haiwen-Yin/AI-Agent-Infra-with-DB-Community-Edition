"""YashanDB native Property Graph adapter boundary."""

from typing import Any, Dict, List, Optional, Tuple

try:
    from .graph_predicate import compile_safe_predicate, state_ref
except ImportError:  # source-tree adapter probe
    from lib.graph_predicate import compile_safe_predicate, state_ref

NATIVE_GRAPH_NAME = "YASHAN_EXECUTION_GRAPH"


def projection_statements(version_id: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    # YashanDB's native Property Graph is defined over the same tables.  The
    # relational contract remains the transaction boundary for DML.
    return []


def capability_probe() -> Dict[str, Any]:
    return {
        "native_graph": True, "graph_name": NATIVE_GRAPH_NAME, "adapter": "yashandb-property-graph",
        "predicate_pushdown": {"dialect": "yashandb-json", "fallback": "portable-evaluator"},
    }


def compile_predicate(expression: Any) -> Dict[str, Any]:
    """Compile safe state predicates for YashanDB JSON properties."""
    def resolve(ref: str) -> Optional[str]:
        parts = state_ref(ref)
        if not parts:
            return None
        path = "$." + ".".join(parts)
        return "JSON_VALUE(STATE_JSON, '" + path + "')"

    return compile_safe_predicate(
        expression, dialect="yashandb-json", resolve_ref=resolve,
        placeholder=lambda name: ":" + name,
    )
