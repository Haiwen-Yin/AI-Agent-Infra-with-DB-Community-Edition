"""Oracle native, ID-only authorized Knowledge candidate SQL fragments."""


def limit_clause():
    return " FETCH FIRST :candidate_limit ROWS ONLY"


def intake_value(column, field):
    return "JSON_VALUE(" + column + ", '$." + field + "')"


def intake_instant(value):
    normalized = "REPLACE(" + value + ",'Z','+00:00')"
    return 'TO_TIMESTAMP_TZ(' + normalized + ",CASE WHEN INSTR(" + value + ",'.')>0 THEN " + \
        "'YYYY-MM-DD\"T\"HH24:MI:SS.FFTZH:TZM' ELSE 'YYYY-MM-DD\"T\"HH24:MI:SSTZH:TZM' END)"


def edge_join(edge_column, entity_column):
    return edge_column + "=" + entity_column


def artifact_entity_join(native_column, entity_column):
    return native_column + '=' + entity_column


def knowledge_edge_predicate():
    # The authoritative legacy edge contract has no TARGET_TYPE column.
    return "1=1"


def channel_sql(channel, tokens, metric):
    if channel == "vector":
        native_metric = {"COSINE": "COSINE", "EUCLIDEAN": "EUCLIDEAN", "DOT_PRODUCT": "DOT"}[metric]
        return {"score": "VECTOR_DISTANCE(em.EMBEDDING, TO_VECTOR(:vec), " + native_metric + ")",
                "predicates": [], "params": {}, "ordering": "ASC"}
    if channel != "fulltext":
        raise ValueError("Unknown native search channel")
    return {"score": "SCORE(1)", "predicates": ["CONTAINS(e.TITLE, :fulltext_query, 1)>0"],
            "params": {"fulltext_query": " OR ".join("{" + token + "}" for token in tokens)},
            "ordering": "DESC"}
