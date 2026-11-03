"""PostgreSQL native, ID-only authorized Knowledge candidate SQL fragments."""


def limit_clause():
    return " LIMIT :candidate_limit"


def intake_value(column, field):
    return "(CAST(" + column + " AS JSONB)->>'" + field + "')"


def intake_instant(value):
    return 'CAST(' + value + ' AS TIMESTAMPTZ)'


def edge_join(edge_column, entity_column):
    # Both columns in the supported v5 baseline are BIGINT. Preserve their
    # native equality and indexes rather than casting both sides to text.
    return f"{edge_column}={entity_column}"


def artifact_entity_join(native_column, entity_column):
    # Continuity pointers are text; ENTITIES uses BIGINT. Casting ENTITIES to
    # text hides its indexed equality and can create a cross-product plan.
    # Only the exact canonical bigint text may resolve: malformed, overflow,
    # signed zero and zero-padded pointers neither raise nor alias another ID.
    pointer = ("(CASE WHEN " + native_column + " ~ '^(0|-?[1-9][0-9]{0,18})$' "
        "THEN CASE WHEN CAST(" + native_column + " AS NUMERIC) "
        "BETWEEN -9223372036854775808 AND 9223372036854775807 "
        "THEN CAST(" + native_column + " AS BIGINT) END END)")
    return entity_column + '=' + pointer


def knowledge_edge_predicate():
    return "(r.TARGET_TYPE IS NULL OR r.TARGET_TYPE='KNOWLEDGE')"


def channel_sql(channel, tokens, metric):
    if channel == "vector":
        operator = {"COSINE": "<=>", "EUCLIDEAN": "<->", "DOT_PRODUCT": "<#>"}[metric]
        return {"score": "em.EMBEDDING " + operator + " CAST(:vec AS vector)",
                "predicates": [], "params": {}, "ordering": "ASC"}
    if channel != "fulltext":
        raise ValueError("Unknown native search channel")
    expression = "to_tsvector('simple', COALESCE(e.TITLE,'') || ' ' || COALESCE(e.CONTENT,''))"
    match = "plainto_tsquery('simple', :fulltext_query)"
    return {"score": "ts_rank(" + expression + ", " + match + ")",
            "predicates": [expression + " @@ " + match],
            "params": {"fulltext_query": " ".join(tokens)}, "ordering": "DESC"}
