"""YashanDB native, ID-only authorized Knowledge candidate SQL fragments."""


def fulltext_literal(tokens):
    # This native CONTAINS implementation requires a constant expression.
    # Terms still come from the bounded query parser; escape SQL literals,
    # never interpolate identifiers or relax the bound authority predicates.
    if (not isinstance(tokens,list) or not 1<=len(tokens)<=24
            or any(not isinstance(token,str) or not token or len(token)>2000
                   or any(ord(char)<32 for char in token) for token in tokens)):
        raise ValueError('Invalid bounded fulltext terms')
    query=' OR '.join('{'+token+'}' for token in tokens)
    return "'"+query.replace("'","''")+"'"


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
    return "1=1"


def channel_sql(channel, tokens, metric):
    if channel == "vector":
        native_metric = {"COSINE": "COSINE", "EUCLIDEAN": "EUCLIDEAN", "DOT_PRODUCT": "DOT"}[metric]
        return {"score": "VECTOR_DISTANCE(em.EMBEDDING, TO_VECTOR(:vec), " + native_metric + ")",
                "predicates": [], "params": {}, "ordering": "ASC"}
    if channel != "fulltext":
        raise ValueError("Unknown native search channel")
    # YashanDB CONTAINS is a two-argument predicate, unsupported in SELECT
    # expressions. Membership is native; ID tie-breaking is deterministic.
    query=fulltext_literal(tokens)
    # Keep the two SEARCH predicates in separate UNION branches. This native
    # release loses body matches when TITLE/CONTENT CONTAINS are joined with
    # OR alongside ordinary filters. The ID set stays inside the database;
    # caller lifecycle/dual-authority predicates apply before the outer limit.
    title='SELECT ft.ENTITY_ID FROM ENTITIES ft WHERE CONTAINS(ft.TITLE, '+query+')>0'
    body='SELECT ft.ENTITY_ID FROM ENTITIES ft WHERE CONTAINS(ft.CONTENT, '+query+')>0'
    return {"score": '1',
            "predicates": ['e.ENTITY_ID IN ('+title+' UNION '+body+')'],
            "params": {},
            "ordering": "DESC"}
