"""Shared user/Agent intersection retrieval with fresh citation authorization."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from . import connection, content_security, identity_api, knowledge_api, agent_registration

RETRIEVAL_POLICY = "authorized-rrf-v1"
RRF_CONSTANT = 60


class GroundingError(ValueError):
    pass


# Conversational filler is not evidence of subject relevance. In particular,
# matching "in"/"one"/"explain" previously returned unrelated enterprise text.
_QUERY_STOP_WORDS = frozenset('a an the and or of to in on at for from with by '
    'is are was were be been being it its this that these those i me my we our '
    'you your they their what which who when where why how can could would should '
    'do does did please explain describe tell about one sentence sentences briefly'.split())


def _search_terms(query: str) -> list[str]:
    # Keep Chinese subjects intact: a shared fragment such as 公司 must not
    # make 甲骨文公司 match an unrelated company policy. Strip only anchored
    # conversational wrappers, never arbitrary characters inside the subject.
    terms = []
    for term in re.findall(r'[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}', query.lower()):
        if re.fullmatch(r'[\u4e00-\u9fff]+', term):
            previous = None
            while term != previous:
                previous = term
                term = re.sub(r'^(?:请问|请|帮我|给我|麻烦|我想了解|想了解|查询一下|查询|查一下|介绍一下|介绍|解释一下|解释|告诉我|了解一下|了解|关于)', '', term)
                term = re.sub(r'(?:是什么|有哪些功能|有什么功能|的相关信息|的基本情况|的信息|的情况|怎么样)$', '', term)
        if len(term) >= 2 and term not in _QUERY_STOP_WORDS:
            terms.append(term)
    return list(dict.fromkeys(terms))


def _matches_subject(item: dict[str, Any], terms: list[str]) -> bool:
    # Summary is candidate metadata, not the title/content sent to the model.
    # Require the actual authorized source to support every subject term.
    text = (str(item.get('title') or '') + '\n' + str(item.get('content') or '')).lower()
    return all(bool(re.search(r'(?<![a-z0-9_])' + re.escape(term) + r'(?![a-z0-9_])', text))
               if re.fullmatch(r'[a-z0-9_]+', term) else term in text for term in terms)


def require_reader(actor: str, agent: str) -> None:
    if not actor or not agent:
        raise PermissionError("Authenticated user and Agent are required")
    for principal in {actor, agent}:
        if identity_api.effective_access(principal, "knowledge.read").get("decision") != "ALLOW":
            raise PermissionError("Knowledge access is unavailable")
        row = connection.execute_query_one("SELECT STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:id", {"id": principal})
        if row:
            if str(next((v for k, v in row.items() if k.lower() == "status"), "")).upper() != "ACTIVE":
                raise PermissionError("Knowledge principal is inactive")
        elif principal == agent:
            # Pool Agents may expose a registry alias instead of a principal id.
            # Their admission is authoritative in the registration inventory.
            registration = agent_registration.get_registration(principal)
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


def citation(actor: str, agent: str, entity_id: str, expected_digest: str = "") -> dict[str, Any]:
    require_reader(actor, agent)
    item = knowledge_api.get_knowledge(entity_id, principal_id=actor)
    delegated = knowledge_api.get_knowledge(entity_id, principal_id=agent)
    if not item or not delegated or not _valid(item) or not _valid(delegated):
        raise PermissionError("Knowledge is unavailable")
    content = str(item.get("content") or "")
    digest = hashlib.sha256(json.dumps({"content": content, "title": item.get("title"),
        "updated_at": str(item.get("updated_at") or "")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if expected_digest and digest != expected_digest:
        raise GroundingError("Knowledge version changed")
    content_security.enforce(content, "KNOWLEDGE")
    return {"entity_id": str(entity_id), "title": str(item.get("title") or ""),
            "content": content, "digest": digest, "updated_at": str(item.get("updated_at") or ""),
            "expires_at": str(item.get("expires_at") or ""),
            "domain": str(item.get("domain") or ""), "visibility": str(item.get("visibility") or "")}


def search(actor: str, agent: str, query: str, *, limit: int = 8, entity_ids: list[str] | None = None,
           strategy: str = "keyword") -> dict[str, Any]:
    require_reader(actor, agent)
    if not isinstance(query, str) or len(query) > 2000:
        raise GroundingError("Knowledge query is invalid")
    if entity_ids is not None and (not isinstance(entity_ids, list) or len(entity_ids) > 50 or any(not isinstance(x, str) for x in entity_ids)):
        raise GroundingError("Knowledge source filter is invalid")
    if strategy not in {"keyword", "fulltext", "vector", "hybrid"}:
        raise GroundingError("Knowledge retrieval strategy is invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise GroundingError("Knowledge retrieval limit is invalid")
    if strategy != "keyword":
        return _multi_route_search(actor, agent, query, limit=limit, entity_ids=entity_ids, strategy=strategy)
    # Every candidate is SQL-filtered by BOTH principals. Global read.all
    # cannot turn a delegated model request into unrestricted retrieval.
    terms = _search_terms(query)
    if query.strip() and (not terms or len(terms) > 24):
        return {"status": "NO_MATCH", "items": [], "retrieval_mode": "KEYWORD"}
    rows = _keyword_candidates(actor, agent, terms, entity_ids=entity_ids)
    items = []
    for row in rows:
        entity_id = str(next(v for k, v in row.items() if k.lower() == "entity_id"))
        try:
            item = citation(actor, agent, entity_id)
        except PermissionError:
            continue
        if terms and not _matches_subject(item, terms):
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return {"status": "MATCHED" if items else "NO_MATCH", "items": items, "retrieval_mode": "KEYWORD",
            "retrieval": {"policy_revision": RETRIEVAL_POLICY,
                          "requested_strategy": "KEYWORD", "actual_strategies": ["KEYWORD"],
                          "available_channels": ["KEYWORD"], "degradations": [],
                          "rank_meaning": "ORDERED_RELEVANCE_NOT_PROBABILITY"}}


def _keyword_candidates(actor, agent, terms, *, entity_ids):
    """ID-only lexical candidates; bodies are loaded under fresh authority."""
    params: dict[str, Any] = {"actor": actor, "agent": agent, "lim": 100}
    predicates = ["e.ENTITY_TYPE='KNOWLEDGE'", "e.STATUS='ACTIVE'",
        "(e.EXPIRES_AT IS NULL OR e.EXPIRES_AT>CURRENT_TIMESTAMP)",
        knowledge_api.knowledge_access_predicate("e", ":actor"), knowledge_api.knowledge_access_predicate("e", ":agent")]
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
    return connection.execute_query("SELECT e.ENTITY_ID FROM ENTITIES e WHERE " + " AND ".join(predicates) + " ORDER BY (" + relevance + ") DESC, e.UPDATED_AT DESC,e.ENTITY_ID" + suffix, params)


def _load_candidates(actor: str, agent: str, entity_ids: list[str]) -> list[dict[str, Any]]:
    """Load a bounded candidate batch with fresh dual authority and validity.

    Reusing the source-version digest contract lets existing Portal and Channel
    disclosure checks detect changes made after this batch was read.
    """
    require_reader(actor, agent)
    if not entity_ids:
        return []
    params = {"actor": actor, "agent": agent, **{f"candidate_id{i}": key for i, key in enumerate(entity_ids)}}
    rows = connection.execute_query(
        "SELECT e.ENTITY_ID,e.TITLE,e.CONTENT,e.STATUS,e.VISIBILITY,km.DOMAIN,"
        "TO_CHAR(e.UPDATED_AT, 'YYYY-MM-DD HH24:MI:SS') AS UPDATED_AT,"
        "TO_CHAR(e.EXPIRES_AT, 'YYYY-MM-DD HH24:MI:SS') AS EXPIRES_AT "
        "FROM ENTITIES e JOIN KNOWLEDGE_META km ON km.ENTITY_ID=e.ENTITY_ID AND km.ENTITY_TYPE=e.ENTITY_TYPE "
        "WHERE e.ENTITY_TYPE='KNOWLEDGE' AND e.STATUS='ACTIVE' "
        "AND (e.EXPIRES_AT IS NULL OR e.EXPIRES_AT>CURRENT_TIMESTAMP) AND e.ENTITY_ID IN ("
        + ",".join(f":candidate_id{i}" for i in range(len(entity_ids))) + ") AND "
        + knowledge_api.knowledge_access_predicate("e", ":actor") + " AND "
        + knowledge_api.knowledge_access_predicate("e", ":agent"), params)
    items = []
    for raw in rows:
        row = {str(key).lower(): value for key, value in dict(raw).items()}
        if not _valid(row):
            continue
        content = str(row.get("content") or "")
        content_security.enforce(content, "KNOWLEDGE")
        digest = hashlib.sha256(json.dumps({"content": content, "title": row.get("title"),
            "updated_at": str(row.get("updated_at") or "")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        items.append({"entity_id": str(row["entity_id"]), "title": str(row.get("title") or ""),
                      "content": content, "digest": digest, "updated_at": str(row.get("updated_at") or ""),
                      "expires_at": str(row.get("expires_at") or ""),
                      "domain": str(row.get("domain") or ""), "visibility": str(row.get("visibility") or "")})
    return items


def _multi_route_search(actor, agent, query, *, limit, entity_ids, strategy):
    from . import embedding_api
    started = time.monotonic()
    terms = _search_terms(query)
    channels, unavailable, ranked = {}, [], {}
    requested = ["fulltext", "vector"] if strategy == "hybrid" else [strategy]
    if not terms or len(terms) > 24 or entity_ids == []:
        requested = []
    for channel in requested:
        try:
            channels[channel] = embedding_api.search_authorized_knowledge(
                query, channel=channel, actor=actor, agent=agent,
                entity_ids=entity_ids, limit=40)
        except embedding_api.AuthorizedSearchUnavailable:
            unavailable.append({"channel": channel, "reason": "CHANNEL_UNAVAILABLE"})
    # Text fallback keeps working when an optional index/provider is unavailable.
    # Errors from the authorized SQL route propagate; they are never NO_MATCH.
    if terms and len(terms) <= 24 and entity_ids != [] and (strategy == "hybrid" or unavailable):
        channels["keyword"] = [{"entity_id": str(next(value for key, value in row.items() if key.lower() == "entity_id"))}
                               for row in _keyword_candidates(actor, agent, terms, entity_ids=entity_ids)][:40]
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
    ordered = sorted(ranked, key=lambda key: (-ranked[key]["rank_score"], key))[:40]
    loaded = {item["entity_id"]: item for item in _load_candidates(actor, agent, ordered)} if ordered else {}
    items = []
    for key in ordered:
        if key in loaded:
            items.append({**loaded[key], "retrieval_rank": {**ranked[key], "rank_score": round(ranked[key]["rank_score"], 8)}})
            if len(items) == limit:
                break
    actual = "HYBRID" if len(channels) > 1 else next(iter(channels), "none").upper()
    return {"status": "MATCHED" if items else "NO_MATCH", "items": items, "retrieval_mode": actual,
            "retrieval": {"policy_revision": RETRIEVAL_POLICY, "requested_strategy": strategy.upper(),
                          "actual_strategy": actual, "available_channels": list(channels),
                          "degradations": unavailable, "rank_meaning": "RECIPROCAL_RANK_NOT_PROBABILITY",
                          "candidate_count": len(ranked), "loaded_count": len(loaded),
                          "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}}
