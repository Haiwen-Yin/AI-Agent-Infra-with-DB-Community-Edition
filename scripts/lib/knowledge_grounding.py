"""Shared user/Agent intersection retrieval with fresh citation authorization."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from . import connection, content_security, identity_api, knowledge_api, agent_registration, answer_query, knowledge_applicability, knowledge_candidates

RETRIEVAL_POLICY = "authorized-rrf-v3"
RRF_CONSTANT = 60


class GroundingError(ValueError):
    pass


def _search_terms(query: str) -> list[str]:
    return answer_query.interpret(query).terms


def _matches_subject(item: dict[str, Any], terms: list[str]) -> bool:
    # Summary is candidate metadata, not the title/content sent to the model.
    # Require the actual authorized source to support every subject term.
    text = (str(item.get('title') or '') + '\n' + str(item.get('content') or '')).lower()
    return all(answer_query.supports_term(text, term) for term in terms)


def require_reader(actor: str, agent: str, *, transaction=None) -> None:
    if not actor or not agent:
        raise PermissionError("Authenticated user and Agent are required")
    for principal in {actor, agent}:
        if identity_api.effective_access(principal, "knowledge.read").get("decision") != "ALLOW":
            raise PermissionError("Knowledge access is unavailable")
        query = transaction.query_one if transaction is not None else connection.execute_query_one
        row = query("SELECT STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:id", {"id": principal})
        if row:
            if str(next((v for k, v in row.items() if k.lower() == "status"), "")).upper() != "ACTIVE":
                raise PermissionError("Knowledge principal is inactive")
        elif principal == agent:
            # Pool Agents may expose a registry alias instead of a principal id.
            # Their admission is authoritative in the registration inventory.
            registration = agent_registration.get_registration(principal, **({"transaction": transaction} if transaction is not None else {}))
            if not registration or str(registration.get("status") or "").upper() != "ACTIVE":
                raise PermissionError("Knowledge Agent is inactive")
        else:
            raise PermissionError("Knowledge principal is inactive")


def _valid(item: dict[str, Any]) -> bool:
    if str(item.get("status", "")).upper() != "ACTIVE":
        return False
    expiry = item.get("expires_at")
    if not expiry:
        return True
    try:
        instant = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        return instant.replace(tzinfo=instant.tzinfo or timezone.utc) > datetime.now(timezone.utc)
    except ValueError:
        return False


def citation(actor: str, agent: str, entity_id: str, expected_digest: str = "", *, transaction=None) -> dict[str, Any]:
    options = {"transaction": transaction} if transaction is not None else {}
    require_reader(actor, agent, **options)
    item = knowledge_api.get_knowledge(entity_id, principal_id=actor, **options)
    # A self-query has one principal intersection. Reuse this call's exact
    # authorized read instead of reopening the same source transaction twice.
    # Distinct principals and every later citation still authorize separately.
    delegated = item if agent == actor else knowledge_api.get_knowledge(entity_id, principal_id=agent, **options)
    if not item or not delegated or not _valid(item) or not _valid(delegated):
        raise PermissionError("Knowledge is unavailable")
    content = str(item.get("content") or "")
    digest = hashlib.sha256(json.dumps({"content": content, "title": item.get("title"),
        "updated_at": str(item.get("updated_at") or ""),
        **({'source_context':item['source_context']} if item.get('source_context') else {})},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if expected_digest and digest != expected_digest:
        raise GroundingError("Knowledge version changed")
    content_security.enforce(content, "KNOWLEDGE")
    return {"entity_id": str(entity_id), "title": str(item.get("title") or ""),
            "content": content, "digest": digest, "updated_at": str(item.get("updated_at") or ""),
            "expires_at": str(item.get("expires_at") or ""),
            "domain": str(item.get("domain") or ""), "visibility": str(item.get("visibility") or ""),
            **({'source_context':item['source_context']} if item.get('source_context') else {})}


def validate_citation(actor,agent,item,*,transaction=None):
    """Reauthorize a source and its exact relation lineage without recursion."""
    options={'transaction':transaction} if transaction is not None else {}
    result=citation(actor,agent,item['entity_id'],item['digest'],**options)
    if item.get('applicability_constraints'):
        if not knowledge_applicability.matches(result,item['applicability_constraints']):
            raise GroundingError('Knowledge applicability changed')
    relations=item.get('relationship_evidence') or []
    if not isinstance(relations,list) or len(relations)>8:
        raise GroundingError('Knowledge relationship evidence is invalid')
    if relations:
        from . import knowledge_signals
        anchors=[]
        for relation in relations:
            if (not isinstance(relation,dict) or relation.get('target_entity_id')!=str(item['entity_id'])
                    or relation.get('target_digest')!=item['digest']):
                raise GroundingError('Knowledge relationship evidence changed')
            citation(actor,agent,relation['source_entity_id'],relation['source_digest'],**options)
            anchors.append(relation['source_entity_id'])
        current=knowledge_signals.links(actor,agent,list(dict.fromkeys(anchors)),[str(item['entity_id'])],**options)
        facts={(value['edge_id'],value['edge_digest']) for value in current}
        if any((relation.get('edge_id'),relation.get('edge_digest')) not in facts for relation in relations):
            raise GroundingError('Knowledge relationship evidence changed')
    return result


def artifact_domain_predicate(alias, params, domain):
    """Narrow recall to current governed artifacts before channel limits.

    Domain selection confers no source or membership grant; normal dual reader
    predicates and the exact continuity resolver still apply separately.
    """
    if domain is None:
        return []
    if not isinstance(domain,str) or not domain.strip() or len(domain)>128:
        raise GroundingError('Knowledge artifact domain is invalid')
    if alias not in {'e','s'}:
        raise ValueError('Unsupported internal Knowledge alias')
    params['artifact_domain']=domain
    return ["EXISTS (SELECT 1 FROM CX_CONTINUITY_ARTIFACTS cx_scope_a "
        "JOIN CX_CONTINUITY_ARTIFACT_REVS cx_scope_r ON cx_scope_r.ARTIFACT_ID=cx_scope_a.ARTIFACT_ID "
        "AND cx_scope_r.REVISION_ID=cx_scope_a.CURRENT_REVISION_ID "
        "WHERE cx_scope_a.FAMILY='KNOWLEDGE' AND cx_scope_a.STATUS='ACTIVE' "
        "AND cx_scope_a.SECURITY_DOMAIN_ID=:artifact_domain AND " +
        knowledge_candidates.artifact_entity_join('cx_scope_r.NATIVE_ENTITY_ID', alias + '.ENTITY_ID') + ")"]


def search(actor: str, agent: str, query: str, *, limit: int = 8, entity_ids: list[str] | None = None,
           strategy: str = "keyword", applicability=None, artifact_domain=None, transaction=None) -> dict[str, Any]:
    options={'transaction':transaction} if transaction is not None else {}
    require_reader(actor, agent,**options)
    if not isinstance(query, str) or len(query) > 2000:
        raise GroundingError("Knowledge query is invalid")
    if entity_ids is not None and (not isinstance(entity_ids, list) or len(entity_ids) > 50 or any(not isinstance(x, str) for x in entity_ids)):
        raise GroundingError("Knowledge source filter is invalid")
    if strategy not in {"keyword", "fulltext", "vector", "hybrid"}:
        raise GroundingError("Knowledge retrieval strategy is invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise GroundingError("Knowledge retrieval limit is invalid")
    scope={'artifact_domain':artifact_domain} if artifact_domain is not None else {}
    artifact_domain_predicate('e',{},artifact_domain)
    try:
        bound=knowledge_applicability.constraints(query,applicability)
    except ValueError as exc:
        raise GroundingError('Knowledge applicability filter is invalid') from exc
    if strategy != "keyword":
        return _multi_route_search(actor, agent, query, limit=limit, entity_ids=entity_ids, strategy=strategy, bound=bound,**scope,**options)
    # Every candidate is SQL-filtered by BOTH principals. Global read.all
    # cannot turn a delegated model request into unrestricted retrieval.
    terms = _search_terms(query)
    if query.strip() and (not terms or len(terms) > 24):
        return {"status": "NO_MATCH", "items": [], "retrieval_mode": "KEYWORD"}
    rows = _keyword_candidates(actor, agent, terms, entity_ids=entity_ids,candidate_scope=bound,**scope)
    items = []
    for row in rows:
        entity_id = str(next(v for k, v in row.items() if k.lower() == "entity_id"))
        try:
            item = citation(actor, agent, entity_id,**options)
        except PermissionError:
            continue
        if not knowledge_applicability.matches(item,bound):
            continue
        if terms and not _matches_subject(item, terms):
            continue
        if knowledge_applicability.active(bound):item['applicability_constraints']=bound
        items.append(item)
        if entity_ids is None:
            items=knowledge_candidates.distinct(items)
        if len(items) >= limit:
            break
    return {"status": "MATCHED" if items else "NO_MATCH", "items": items, "retrieval_mode": "KEYWORD",
            "retrieval": {"policy_revision": RETRIEVAL_POLICY,
                          "requested_strategy": "KEYWORD", "actual_strategies": ["KEYWORD"],
                          "available_channels": ["KEYWORD"], "degradations": [],
                          "ranking_generation_calls":0,
                          "rank_meaning": "ORDERED_RELEVANCE_NOT_PROBABILITY"}}


def _keyword_candidates(actor, agent, terms, *, entity_ids,artifact_domain=None,candidate_scope=None):
    """ID-only lexical candidates; bodies are loaded under fresh authority."""
    params: dict[str, Any] = {"actor": actor, "agent": agent, "lim": 100}
    predicates = ["e.ENTITY_TYPE='KNOWLEDGE'", "e.STATUS='ACTIVE'",
        "(e.EXPIRES_AT IS NULL OR e.EXPIRES_AT>CURRENT_TIMESTAMP)",
        knowledge_api.knowledge_access_predicate("e", ":actor"), knowledge_api.knowledge_access_predicate("e", ":agent")]
    predicates.extend(artifact_domain_predicate('e',params,artifact_domain))
    if terms:
        predicates.append("(" + " AND ".join(f"(LOWER(e.TITLE) LIKE :q{i} ESCAPE '!' OR LOWER(e.SUMMARY) LIKE :q{i} ESCAPE '!' OR LOWER(e.CONTENT) LIKE :q{i} ESCAPE '!')" for i in range(len(terms))) + ")")
        params.update({f"q{i}": "%" + term.replace('!', '!!').replace('%', '!%').replace('_', '!_') + "%" for i, term in enumerate(terms)})
        relevance = " + ".join(
            f"CASE WHEN LOWER(e.TITLE) LIKE :q{i} ESCAPE '!' THEN 8 WHEN LOWER(e.SUMMARY) LIKE :q{i} ESCAPE '!' THEN 3 WHEN LOWER(e.CONTENT) LIKE :q{i} ESCAPE '!' THEN 1 ELSE 0 END"
            for i in range(len(terms))
        )
    else:
        # Empty-query inventory must use valid sortable SQL on every adapter.
        relevance = "e.UPDATED_AT"
    if entity_ids is not None:
        if not entity_ids:
            return []
        predicates.append("e.ENTITY_ID IN (" + ",".join(f":id{i}" for i in range(len(entity_ids))) + ")")
        params.update({f"id{i}": key for i, key in enumerate(entity_ids)})
    suffix = " LIMIT :lim" if str(connection.DATABASE_DIALECT).lower() in {"pg", "postgresql"} else " FETCH FIRST :lim ROWS ONLY"
    base = "SELECT e.ENTITY_ID,(" + relevance + ") AS CHANNEL_SCORE FROM ENTITIES e WHERE " + " AND ".join(predicates)
    sql = knowledge_candidates.query(base, params, suffix=suffix, bound=candidate_scope)
    return connection.execute_query(sql, params)


def _load_candidates(actor: str, agent: str, entity_ids: list[str],*,transaction=None) -> list[dict[str, Any]]:
    """Load a bounded candidate batch with fresh dual authority and validity.

    Reusing the source-version digest contract lets existing Portal and Channel
    disclosure checks detect changes made after this batch was read.
    """
    options={'transaction':transaction} if transaction is not None else {}
    require_reader(actor, agent,**options)
    if not entity_ids:
        return []
    params = {"actor": actor, "agent": agent, **{f"candidate_id{i}": key for i, key in enumerate(entity_ids)}}
    query=transaction.query if transaction is not None else connection.execute_query
    rows = query(
        "SELECT e.ENTITY_ID,e.TITLE,e.CONTENT,e.STATUS,e.VISIBILITY,km.DOMAIN,"
        "TO_CHAR(e.UPDATED_AT, 'YYYY-MM-DD HH24:MI:SS') AS UPDATED_AT,"
        "TO_CHAR(e.EXPIRES_AT, 'YYYY-MM-DD HH24:MI:SS') AS EXPIRES_AT "
        "FROM ENTITIES e JOIN KNOWLEDGE_META km ON km.ENTITY_ID=e.ENTITY_ID AND km.ENTITY_TYPE=e.ENTITY_TYPE "
        "WHERE e.ENTITY_TYPE='KNOWLEDGE' AND e.STATUS='ACTIVE' "
        "AND (e.EXPIRES_AT IS NULL OR e.EXPIRES_AT>CURRENT_TIMESTAMP) AND e.ENTITY_ID IN ("
        + ",".join(f":candidate_id{i}" for i in range(len(entity_ids))) + ") AND "
        + knowledge_api.knowledge_access_predicate("e", ":actor") + " AND "
        + knowledge_api.knowledge_access_predicate("e", ":agent"), params)
    source_contexts=_projection_contexts(actor,agent,entity_ids,**options)
    items = []
    for raw in rows:
        row = {str(key).lower(): value for key, value in dict(raw).items()}
        if not _valid(row):
            continue
        key=str(row['entity_id'])
        if key in source_contexts and source_contexts[key] is None:
            continue
        source_context=source_contexts.get(key)
        content = str(row.get("content") or "")
        content_security.enforce(content, "KNOWLEDGE")
        digest = hashlib.sha256(json.dumps({"content": content, "title": row.get("title"),
            "updated_at": str(row.get("updated_at") or ""),
            **({'source_context':source_context} if source_context else {})},
            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        items.append({"entity_id": str(row["entity_id"]), "title": str(row.get("title") or ""),
                      "content": content, "digest": digest, "updated_at": str(row.get("updated_at") or ""),
                      "expires_at": str(row.get("expires_at") or ""),
                      "domain": str(row.get("domain") or ""), "visibility": str(row.get("visibility") or ""),
                      **({'source_context':source_context} if source_context else {})})
    return items


def _projection_contexts(actor,agent,entity_ids,*,transaction=None):
    """One bounded metadata query skips legacy/manual rows without N+1 reads.

    Every derived result then rechecks original sources for both principals.
    A hidden original omits that result; an integrity/database failure propagates.
    """
    from .continuity_promotions import original_source_contexts
    return original_source_contexts((actor,agent),entity_ids,**({'transaction':transaction} if transaction is not None else {}))


def _multi_route_search(actor, agent, query, *, limit, entity_ids, strategy, bound,artifact_domain=None,transaction=None):
    from . import embedding_api, knowledge_signals
    started = time.monotonic()
    terms = _search_terms(query)
    channels, unavailable, ranked = {}, [], {}
    seeds=[]
    scope={'artifact_domain':artifact_domain} if artifact_domain is not None else {}
    scope['candidate_scope']=bound
    requested = ["fulltext", "vector"] if strategy == "hybrid" else [strategy]
    if not terms or len(terms) > 24 or entity_ids == []:
        requested = []
    for channel in requested:
        try:
            channels[channel] = embedding_api.search_authorized_knowledge(
                query, channel=channel, actor=actor, agent=agent,
                entity_ids=entity_ids, limit=40,**scope)
        except embedding_api.AuthorizedSearchUnavailable:
            unavailable.append({"channel": channel, "reason": "CHANNEL_UNAVAILABLE"})
    # Text fallback keeps working when an optional index/provider is unavailable.
    # Errors from the authorized SQL route propagate; they are never NO_MATCH.
    if terms and len(terms) <= 24 and entity_ids != [] and (strategy == "hybrid" or unavailable):
        channels["keyword"] = [{"entity_id": str(next(value for key, value in row.items() if key.lower() == "entity_id"))}
                               for row in _keyword_candidates(actor, agent, terms, entity_ids=entity_ids,**scope)][:40]
    if terms and len(terms) <= 24 and entity_ids != [] and strategy == "hybrid":
        for channel in ("relational", "tag"):
            try:
                channels[channel] = knowledge_signals.candidates(
                    actor, agent, terms, channel=channel, entity_ids=entity_ids,**scope)
            except embedding_api.AuthorizedSearchUnavailable:
                unavailable.append({"channel": channel, "reason": "CHANNEL_UNAVAILABLE"})
        if knowledge_signals.needs_graph(query):
            seeds = list(_fuse_channels(channels))[:8]
            if seeds:
                try:
                    channels["graph"] = knowledge_signals.candidates(
                        actor, agent, terms, channel="graph", entity_ids=entity_ids, anchors=seeds,**scope)
                except embedding_api.AuthorizedSearchUnavailable:
                    unavailable.append({"channel": "graph", "reason": "CHANNEL_UNAVAILABLE"})
    ranked = _fuse_channels(channels)
    ordered = list(ranked)[:40]
    options={'transaction':transaction} if transaction is not None else {}
    loaded = {item["entity_id"]: item for item in _load_candidates(actor, agent, ordered,**options)} if ordered else {}
    loaded = {key:item for key,item in loaded.items() if knowledge_applicability.matches(item,bound)}
    if knowledge_applicability.active(bound):
        for item in loaded.values():item['applicability_constraints']=bound
    items = []
    for key in ordered:
        if key in loaded:
            items.append({**loaded[key], "retrieval_rank": {**ranked[key], "rank_score": round(ranked[key]["rank_score"], 8)}})
    if entity_ids is None:
        items=knowledge_candidates.distinct(items)
    items=items[:limit]
    relationships=[]
    if channels.get('graph') and seeds and loaded:
        try:
            links=knowledge_signals.links(actor,agent,seeds,list(loaded),**options)
        except PermissionError:
            raise
        except Exception as exc:
            # An edge provenance failure cannot authorize a graph-only source.
            # Ordinary lexical/vector/metadata results remain usable.
            from . import embedding_api
            if embedding_api._authorized_search_denied(exc):
                raise PermissionError('Knowledge relationship access is denied') from exc
            unavailable.append({'channel':'graph','reason':'LINEAGE_UNAVAILABLE'})
            channels.pop('graph',None)
            ranked=_fuse_channels(channels)
            ordered=list(ranked)[:40]
            links=[]
        incoming={}
        for link in links:
            if link['source_entity_id'] in loaded and link['target_entity_id'] in loaded:
                incoming.setdefault(link['target_entity_id'],[]).append(link)
        # Keep an anchor with each graph-only neighbor within the same total
        # item bound. Do not displace its source and then imply a relationship.
        selected=[]
        selected_signatures=set()
        endpoints={value[field] for value in links for field in ('source_entity_id','target_entity_id')}
        for key in ordered:
            if key not in loaded:
                continue
            signature=knowledge_candidates.signature(loaded[key])
            if entity_ids is None and key not in endpoints and signature in selected_signatures:
                continue
            graph_only=set(ranked[key]['channel_ranks'])=={'graph'}
            parents=incoming.get(key,[])[:1] if graph_only else []
            if graph_only and not parents:
                continue
            required=[value['source_entity_id'] for value in parents]+[key]
            pending=[value for value in dict.fromkeys(required) if value not in selected]
            if len(selected)+len(pending)<=limit:
                selected.extend(pending)
                selected_signatures.update(knowledge_candidates.signature(loaded[value]) for value in pending)
        items=[dict(loaded[key],retrieval_rank={**ranked[key],'rank_score':round(ranked[key]['rank_score'],8)}) for key in selected]
        chosen={item['entity_id']:item for item in items}
        for key,item in chosen.items():
            for link in incoming.get(key,[])[:8]:
                if link['source_entity_id'] in chosen:
                    relation=dict(link,source_digest=chosen[link['source_entity_id']]['digest'],target_digest=item['digest'])
                    item.setdefault('relationship_evidence',[]).append(relation)
                    relationships.append(relation)
    actual = "HYBRID" if len(channels) > 1 else next(iter(channels), "none").upper()
    return {"status": "MATCHED" if items else "NO_MATCH", "items": items, "retrieval_mode": actual,
            **({'relationships':relationships} if relationships else {}),
            "retrieval": {"policy_revision": RETRIEVAL_POLICY, "requested_strategy": strategy.upper(),
                          "actual_strategy": actual, "available_channels": list(channels),
                          "degradations": unavailable, "rank_meaning": "RECIPROCAL_RANK_NOT_PROBABILITY",
                          "candidate_count": len(ranked), "loaded_count": len(loaded),
                          "ranking_generation_calls": 0,
                          "graph_engine": ("RELATIONAL_ENTITY_EDGES" if "graph" in channels else
                                           "UNAVAILABLE" if any(item["channel"] == "graph" for item in unavailable) else "NOT_REQUESTED"),
                          "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}}


def _fuse_channels(channels):
    ranked = {}
    for channel, rows in channels.items():
        seen = set()
        for row in rows:
            key = str(row["entity_id"])
            if key in seen:
                continue
            seen.add(key)
            rank = len(seen)
            entry = ranked.setdefault(key, {"entity_id": key, "rank_score": 0.0, "channel_ranks": {}})
            entry["rank_score"] += 1.0 / (RRF_CONSTANT + rank)
            entry["channel_ranks"][channel] = rank
    return {key: ranked[key] for key in sorted(ranked, key=lambda key: (-ranked[key]["rank_score"], key))}
