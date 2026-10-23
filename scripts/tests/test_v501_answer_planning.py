"""Retrieval decisions and public metadata for the shared answer path."""
import json

import pytest
from lib import answer_planning as planning, native_runtime


def source(entity, title, content):
    return {"entity_id": entity, "title": title, "content": content, "digest": entity * 64}


def test_query_strategy_reaches_the_authorized_shared_search(monkeypatch):
    calls = []
    def search(actor, agent, query, **kwargs):
        calls.append((actor, agent, query, kwargs))
        return {"status": "NO_MATCH", "items": [], "retrieval_mode": "HYBRID",
                "retrieval": {"actual_strategy": "HYBRID", "available_channels": ["fulltext", "vector"],
                              "degradations": [], "rank_meaning": "RECIPROCAL_RANK_NOT_PROBABILITY"}}
    monkeypatch.setattr(planning.knowledge_grounding, "search", search)
    result = planning.retrieve("human", "agent", "known fact?", strategy="hybrid")
    assert calls == [("human", "agent", "known fact?", {"entity_ids": None, "strategy": "hybrid"})]
    assert result["answer_metadata"]["actual_strategies"] == ["HYBRID"]
    assert result["answer_metadata"]["available_channels"] == ["FULLTEXT", "VECTOR"]
    assert result["answer_metadata"]["rank_meaning"] == "RECIPROCAL_RANK_NOT_PROBABILITY"


def test_unrelated_platform_material_does_not_answer_vendor_company_question(monkeypatch):
    monkeypatch.setattr(planning.knowledge_grounding, "search", lambda *_a, **_k: {
        "status": "MATCHED", "items": [source("a", "川序部署指南", "川序部署在Oracle数据库上。")],
        "retrieval_mode": "KEYWORD"})
    result = planning.retrieve("human", "agent", "甲骨文公司总部在哪里？", strategy="keyword")
    assert result["status"] == "NO_MATCH" and result["items"] == []
    assert result["answer_metadata"]["evidence_status"] == "NO_MATCH"
    configured = {"mode": "KNOWLEDGE_FIRST", "allow_model_supplement": "Y", "disclosure_profiles": ["p"]}
    prepared = planning.prepare("甲骨文公司总部在哪里？", "p", configured, result)
    assert prepared["answer_source"] == "MODEL_SUPPLEMENT"
    assert prepared["messages"][-1]["content"] == "甲骨文公司总部在哪里？"


def test_same_database_name_is_clarified_without_search(monkeypatch):
    calls = []
    monkeypatch.setattr(planning.knowledge_grounding, "search", lambda *a, **k: calls.append((a, k)))
    result = planning.retrieve("human", "agent", "Oracle")
    assert result["status"] == "AMBIGUOUS" and not calls
    prepared = planning.prepare("Oracle", "p", {"mode": "KNOWLEDGE_FIRST", "allow_model_supplement": "Y",
        "disclosure_profiles": ["p"]}, result)
    assert prepared["answer_source"] == "CLARIFICATION_REQUIRED"


def test_multi_part_answer_tracks_missing_part_count_without_subject_ids(monkeypatch):
    def search(_actor, _agent, query, **_kwargs):
        item = source("secret-entity", "川序部署", "川序部署使用关系数据库和独立Agent运行时。")
        return {"status": "MATCHED", "items": [item] if "川序部署" in query else [], "retrieval_mode": "KEYWORD"}
    monkeypatch.setattr(planning.knowledge_grounding, "search", search)
    result = planning.retrieve("human", "agent", "川序部署以及PostgreSQL协议的定义", strategy="fulltext")
    assert result["status"] == "PARTIAL_MATCH"
    assert result["answer_metadata"]["missing_parts_count"] == 1
    assert "secret-entity" not in str(result["answer_metadata"])
    assert "secret-entity" not in str(result["retrieval"])


@pytest.mark.parametrize('question,parts', [
    ('Atlas routing and explain refraction briefly.', ['Atlas routing', 'explain refraction briefly.']),
    ('Atlas路由以及解释光的折射', ['Atlas路由', '解释光的折射']),
])
def test_partial_answer_keeps_supported_request_before_general_supplement(monkeypatch, question, parts):
    item = source('route', 'Atlas routing', 'Atlas routing uses route-742.')
    monkeypatch.setattr(planning.knowledge_grounding, 'search', lambda actor, agent, query, **kw: {
        'items': [item] if query == parts[0] else [], 'retrieval_mode': 'KEYWORD'})
    retrieval = planning.retrieve('human', 'agent', question)
    prepared = planning.prepare(question, 'p', {'mode': 'KNOWLEDGE_FIRST',
        'allow_model_supplement': 'Y', 'disclosure_profiles': ['p']}, retrieval)
    prompt = json.loads(prepared['messages'][-1]['content'])
    assert prepared['answer_source'] == 'MIXED_SOURCES'
    assert prompt['question_parts'] == parts and prompt['question'] == question
    assert prompt['missing_parts'] == [parts[1]]
    assert prompt['authorized_sources'] == [{'citation': 1, 'title': item['title'], 'content': item['content']}]
    assert 'question_parts' not in prepared['answer_metadata']
    assert 'route-742' not in str(prepared['answer_metadata'])
    assert prepared['answer_source_scope'] == {'uncovered_question_parts': [2]}
    raw = 'Atlas uses route-742 [1]. Light bends at a boundary.'
    rendered = planning.render_reply(raw, prepared)
    assert 'question part(s) 2 have no authorized evidence' in rendered
    assert 'general model supplement' in rendered
    assert rendered.endswith(raw)
    # The scope notice cannot supply query keywords or source facts to make
    # an otherwise empty/incorrect answer look substantively correct.
    notice = rendered.removesuffix(raw)
    assert all(value not in notice for value in [*parts, 'route-742', 'Atlas', 'refraction'])
    assert planning.render_reply('', prepared) == ''
    strict = planning.prepare(question, 'p', {'mode': 'KNOWLEDGE_ONLY',
        'allow_model_supplement': 'Y', 'disclosure_profiles': ['p']}, retrieval)
    assert strict['answer_source'] == 'KNOWLEDGE_GROUNDED'
    assert planning.render_reply(raw, strict) == raw
    assert 'question_parts' not in json.loads(strict['messages'][-1]['content'])


def test_mixed_source_notice_handles_old_plans_without_exposing_untrusted_scope():
    raw = 'The response itself.'
    assert 'general model supplements' in planning.render_reply(raw, {'answer_source': 'MIXED_SOURCES'})
    planned = {'answer_source': 'MIXED_SOURCES', 'answer_source_scope': {
        'uncovered_question_parts': [True, -1, 2, 2, 5, '<script>private</script>'],
        'query': 'private query', 'source': 'private source'}}
    rendered = planning.render_reply(raw, planned)
    assert 'question part(s) 2 have no authorized evidence' in rendered
    assert 'private' not in rendered and '<script>' not in rendered
    assert planning.render_reply(raw, {'answer_source': 'MODEL_SUPPLEMENT'}) == raw


def test_explicit_attribute_conflicts_are_reported_and_not_synthesized(monkeypatch):
    documents = [source("hq-a", "甲骨文公司总部", "甲骨文公司总部位于奥斯汀。"),
                 source("hq-b", "甲骨文公司总部", "甲骨文公司总部位于加州。")]
    monkeypatch.setattr(planning.knowledge_grounding, "search", lambda *_a, **_k: {
        "status": "MATCHED", "items": documents, "retrieval_mode": "KEYWORD"})
    result = planning.retrieve("human", "agent", "甲骨文公司总部")
    assert result["status"] == "AMBIGUOUS"
    assert result["answer_metadata"]["contradiction_count"] == 1
    prepared = planning.prepare("甲骨文公司总部", "p", {"mode": "KNOWLEDGE_FIRST",
        "allow_model_supplement": "Y", "disclosure_profiles": ["p"]}, result)
    assert prepared["answer_source"] == "INSUFFICIENT_KNOWLEDGE"
    assert prepared["knowledge_reply"] and "矛盾" in prepared["knowledge_reply"]
    assert prepared["messages"] == []


def test_native_runtime_metadata_is_strictly_whitelisted():
    result = native_runtime._safe_answer_metadata({
        "policy_revision": "answer-evidence-v1", "requested_strategy": "HYBRID",
        "actual_strategies": ["HYBRID", "evil"], "available_channels": ["FULLTEXT", "SECRET"],
        "degradations": [{"channel": "VECTOR", "reason": "PRIVATE_ENDPOINT"}],
        "evidence_status": "MATCHED", "subject_type": "COMPANY", "missing_parts_count": 2,
        "contradiction_count": 0, "rank_meaning": "PROBABILITY",
        "source_ids": ["secret"], "question": "private question"})
    assert result["actual_strategies"] == ["HYBRID"]
    assert result["available_channels"] == ["FULLTEXT"]
    assert result["degradations"] == [{"channel": "VECTOR", "reason": "CHANNEL_UNAVAILABLE"}]
    assert result["rank_meaning"] == "RECIPROCAL_RANK_NOT_PROBABILITY"
    assert "source_ids" not in result and "question" not in result
