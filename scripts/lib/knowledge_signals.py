"""Bounded structured Knowledge signals under the human/Agent intersection.

Only IDs and ordering signals leave these queries. This module never generates
text, embeds documents, changes indexes or uses unrestricted legacy search.
"""
from __future__ import annotations

import re
import hashlib
import json
import math

from . import connection, knowledge_api, knowledge_retrieval_adapter as native


_RELATION_INTENT = re.compile(
    r"关联|关系|依赖|来源|派生|上下游|协作|交接|related|relationship|dependenc|depend(?:s|ent)?\b|lineage|handoff|upstream|downstream", re.I)


def needs_graph(query):
    return bool(_RELATION_INTENT.search(query))


def _scope(alias):
    return [f"{alias}.ENTITY_TYPE='KNOWLEDGE'", f"{alias}.STATUS='ACTIVE'",
            f"({alias}.EXPIRES_AT IS NULL OR {alias}.EXPIRES_AT>CURRENT_TIMESTAMP)",
            knowledge_api.knowledge_access_predicate(alias, ":actor"),
            knowledge_api.knowledge_access_predicate(alias, ":agent")]


def candidates(actor, agent, terms, *, channel, entity_ids=None, anchors=(), limit=40,artifact_domain=None,candidate_scope=None):
    from . import embedding_api, knowledge_grounding, knowledge_candidates
    knowledge_grounding.require_reader(actor, agent)
    if channel not in {"relational", "tag", "graph"}:
        raise ValueError("Unknown structured Knowledge signal")
    if (not isinstance(terms, list) or not 1 <= len(terms) <= 24
            or any(not isinstance(term, str) or not term or len(term) > 2000 for term in terms)
            or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 40):
        raise ValueError("Structured Knowledge signal request is invalid")
    if entity_ids is not None and (not isinstance(entity_ids, list) or len(entity_ids) > 50
                                  or any(not isinstance(key, str) or not key for key in entity_ids)):
        raise ValueError("Structured Knowledge source filter is invalid")
    if (not isinstance(anchors, (list, tuple)) or len(anchors) > 8
            or any(not isinstance(key, str) or not key for key in anchors)):
        raise ValueError("Structured Knowledge anchors are invalid")
    if entity_ids == [] or (channel == "graph" and not anchors):
        return []
    params = {"actor": actor, "agent": agent, "candidate_limit": limit}
    predicates = _scope("e")
    predicates.extend(knowledge_grounding.artifact_domain_predicate('e',params,artifact_domain))
    if entity_ids is not None:
        predicates.append("e.ENTITY_ID IN (" + ",".join(f":signal_id{i}" for i in range(len(entity_ids))) + ")")
        params.update({f"signal_id{i}": key for i, key in enumerate(entity_ids)})
    tables, grouping = "ENTITIES e", ""
    if channel in {"relational", "tag"}:
        params.update({f"signal_term{i}": "%" + term.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
                       for i, term in enumerate(terms)})
        if channel == "relational":
            tables += " JOIN KNOWLEDGE_META km ON km.ENTITY_ID=e.ENTITY_ID AND km.ENTITY_TYPE=e.ENTITY_TYPE"
            columns = ("km.DOMAIN", "km.TOPIC", "e.CATEGORY")
        else:
            tables += " JOIN ENTITY_TAGS et ON et.ENTITY_ID=e.ENTITY_ID AND et.ENTITY_TYPE=e.ENTITY_TYPE JOIN TAGS t ON t.TAG_ID=et.TAG_ID"
            columns = ("t.TAG_NAME",)
            grouping = " GROUP BY e.ENTITY_ID"
        matches = ["(" + " OR ".join(f"LOWER({column}) LIKE :signal_term{i} ESCAPE '!'" for column in columns) + ")"
                   for i in range(len(terms))]
        predicates.append("(" + " OR ".join(matches) + ")")
        score = " + ".join("CASE WHEN " + match + " THEN 1 ELSE 0 END" for match in matches)
        if channel == "tag":
            score = "SUM(" + score + ")"
    else:
        # One outgoing hop over authoritative relations, never the execution
        # Graph or a global edge-count popularity score. Both endpoints are
        # currently readable by BOTH principals before any neighbor contributes.
        tables += " JOIN ENTITY_EDGES r ON " + native.edge_join("r.TARGET_ID", "e.ENTITY_ID")
        tables += " JOIN ENTITIES s ON " + native.edge_join("r.SOURCE_ID", "s.ENTITY_ID")
        predicates.extend(_scope("s"))
        predicates.extend(knowledge_grounding.artifact_domain_predicate('s',params,artifact_domain))
        predicates.extend(["r.SOURCE_TYPE='KNOWLEDGE'", native.knowledge_edge_predicate(),
                           "r.STRENGTH>0", "r.CONFIDENCE>0", "s.ENTITY_ID<>e.ENTITY_ID",
                           "s.ENTITY_ID IN (" + ",".join(f":anchor_id{i}" for i in range(len(anchors))) + ")",
                           # Legacy adapters lack a target type. Reject
                           # ambiguous IDs rather than infer a cross-type edge.
                           "NOT EXISTS (SELECT 1 FROM ENTITIES other_entity WHERE other_entity.ENTITY_ID=e.ENTITY_ID AND other_entity.ENTITY_TYPE<>'KNOWLEDGE')"])
        params.update({f"anchor_id{i}": key for i, key in enumerate(anchors)})
        score = "MAX(r.STRENGTH*r.CONFIDENCE)"
        grouping = " GROUP BY e.ENTITY_ID"
    base = "SELECT e.ENTITY_ID," + score + " AS CHANNEL_SCORE FROM " + tables + " WHERE " + " AND ".join(predicates) + grouping
    sql = knowledge_candidates.query(base, params, suffix=native.limit_clause(), bound=candidate_scope,
        deduplicate=channel != 'graph')
    try:
        rows = connection.execute_query(sql, params)
    except PermissionError:
        raise
    except Exception as exc:
        if embedding_api._authorized_search_denied(exc):
            raise PermissionError("Authorized structured Knowledge retrieval is denied") from exc
        raise embedding_api.AuthorizedSearchUnavailable(channel + " channel unavailable") from exc
    return [{"entity_id": str(next(value for key, value in row.items() if key.lower() == "entity_id"))}
            for row in rows]


def links(actor,agent,anchors,targets,*,transaction=None):
    """Exact, bounded one-hop relation facts under both readers at both ends.

    Edges locate related sources; they do not establish truth or a verified
    execution receipt. Call again before model disclosure and answer reads.
    """
    from . import knowledge_grounding
    knowledge_grounding.require_reader(actor,agent,**({'transaction':transaction} if transaction else {}))
    if (not isinstance(anchors,(list,tuple)) or len(anchors)>8 or not isinstance(targets,(list,tuple)) or len(targets)>40
            or any(not isinstance(key,str) or not key for key in [*anchors,*targets])):
        raise ValueError('Knowledge relation scope is invalid')
    if not anchors or not targets:
        return []
    params={'actor':actor,'agent':agent,'candidate_limit':40,
        **{f'link_source{i}':key for i,key in enumerate(anchors)},**{f'link_target{i}':key for i,key in enumerate(targets)}}
    predicates=[*_scope('s'),*_scope('e'),"r.SOURCE_TYPE='KNOWLEDGE'",native.knowledge_edge_predicate(),
        'r.STRENGTH>0','r.CONFIDENCE>0','s.ENTITY_ID<>e.ENTITY_ID',
        's.ENTITY_ID IN ('+','.join(f':link_source{i}' for i in range(len(anchors)))+')',
        'e.ENTITY_ID IN ('+','.join(f':link_target{i}' for i in range(len(targets)))+')',
        "NOT EXISTS (SELECT 1 FROM ENTITIES other_entity WHERE other_entity.ENTITY_ID=e.ENTITY_ID AND other_entity.ENTITY_TYPE<>'KNOWLEDGE')"]
    sql=('SELECT r.EDGE_ID,r.SOURCE_ID,r.TARGET_ID,r.EDGE_TYPE,r.STRENGTH,r.CONFIDENCE '
        'FROM ENTITY_EDGES r JOIN ENTITIES s ON '+native.edge_join('r.SOURCE_ID','s.ENTITY_ID')+
        ' JOIN ENTITIES e ON '+native.edge_join('r.TARGET_ID','e.ENTITY_ID')+
        ' WHERE '+' AND '.join(predicates)+' ORDER BY r.STRENGTH*r.CONFIDENCE DESC,r.EDGE_ID'+native.limit_clause())
    query=transaction.query if transaction is not None else connection.execute_query
    result=[]
    for raw in query(sql,params):
        row={str(key).lower():value for key,value in raw.items()}
        strength,confidence=float(row['strength']),float(row['confidence'])
        if not math.isfinite(strength) or not math.isfinite(confidence):
            continue
        fact=dict(edge_id=str(row['edge_id']),source_entity_id=str(row['source_id']),
            target_entity_id=str(row['target_id']),edge_type=str(row['edge_type']),strength=strength,confidence=confidence)
        result.append(dict(fact,edge_digest=hashlib.sha256(json.dumps(fact,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
    return result
