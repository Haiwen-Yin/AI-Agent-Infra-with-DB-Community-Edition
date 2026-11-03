"""SQL-executed structured retrieval isolation and deterministic fusion tests.

SQLite verifies portable query semantics, not native indexes or driver parity.
All networking, process launches and text generation are forbidden here.
"""
import importlib.util
from pathlib import Path
import socket
import sqlite3
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lib import answer_planning, embedding_api, knowledge_grounding as grounding, knowledge_signals as signals
from lib import portal_grounding,business_channel_runtime,knowledge_candidates

pytestmark = pytest.mark.skipif(not (Path(__file__).resolve().parents[2] / "adapters").is_dir(),
    reason="Cross-adapter SQL tests run from the source checkout; native package checks are separate")

def adapter(database):
    spec = importlib.util.spec_from_file_location("knowledge_sql_" + database,
        Path(__file__).resolve().parents[2] / "adapters" / database / "knowledge_retrieval_adapter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_external_work(monkeypatch):
    def forbidden(*_a, **_kw):
        pytest.fail("Structured sorting must not call a model, network or process")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(embedding_api, "generate_embedding", forbidden)


@pytest.fixture
def store(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.create_function("TO_CHAR", 2, lambda value, _fmt: value)
    db.executescript("""
      CREATE TABLE ENTITIES (ENTITY_ID TEXT,ENTITY_TYPE TEXT,STATUS TEXT,EXPIRES_AT TEXT,
        TITLE TEXT,SUMMARY TEXT,CONTENT TEXT,UPDATED_AT TEXT,VISIBILITY TEXT,CATEGORY TEXT,
        ALLOW_HUMAN INT,ALLOW_AGENT INT,CREATED_AT TEXT);
      CREATE TABLE KNOWLEDGE_META (ENTITY_ID TEXT,ENTITY_TYPE TEXT,DOMAIN TEXT,TOPIC TEXT);
      CREATE TABLE TAGS (TAG_ID INT,TAG_NAME TEXT);
      CREATE TABLE ENTITY_TAGS (ENTITY_ID TEXT,ENTITY_TYPE TEXT,TAG_ID INT);
      CREATE TABLE ENTITY_EDGES (EDGE_ID INTEGER PRIMARY KEY,EDGE_TYPE TEXT DEFAULT 'RELATED_TO',SOURCE_ID TEXT,SOURCE_TYPE TEXT,TARGET_ID TEXT,TARGET_TYPE TEXT,
        STRENGTH REAL,CONFIDENCE REAL);
      CREATE TABLE CX_CONTINUITY_ARTIFACTS(ARTIFACT_ID TEXT,FAMILY TEXT,SECURITY_DOMAIN_ID TEXT,
        STATUS TEXT,CURRENT_REVISION_ID TEXT);
      CREATE TABLE CX_CONTINUITY_ARTIFACT_REVS(ARTIFACT_ID TEXT,NATIVE_ENTITY_ID TEXT,REVISION_ID TEXT,
        CANDIDATE_ID TEXT,CANDIDATE_REVISION_NO INT,CONTENT_DIGEST TEXT);
      CREATE TABLE CX_KNOWLEDGE_INTAKE(CANDIDATE_ID TEXT,REVISION_NO INT,METADATA_JSON TEXT);
    """)
    def add(key, *, domain="", topic="", tag=None, human=1, agent=1, status="ACTIVE", expiry=None):
        db.execute("INSERT INTO ENTITIES VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (key, "KNOWLEDGE", status, expiry, "Document " + key, "", "Authorized procedure " + key,
             "2026-11-01", "PRIVATE", "GUIDE", human, agent, "2026-11-01"))
        db.execute("INSERT INTO KNOWLEDGE_META VALUES (?, 'KNOWLEDGE', ?, ?)", (key, domain, topic))
        if tag:
            tag_id = db.execute("SELECT COUNT(*)+1 FROM TAGS").fetchone()[0]
            db.execute("INSERT INTO TAGS VALUES (?,?)", (tag_id, tag))
            db.execute("INSERT INTO ENTITY_TAGS VALUES (?, 'KNOWLEDGE', ?)", (key, tag_id))
    monkeypatch.setattr(signals, "native", adapter("pg"))
    monkeypatch.setattr(knowledge_candidates, 'native', SimpleNamespace(
        artifact_entity_join=lambda native,entity:native+'=CAST('+entity+' AS VARCHAR(128))',
        intake_value=lambda column,field:"json_extract("+column+", '$."+field+"')",
        intake_instant=lambda value:'julianday('+value+')'))
    monkeypatch.setattr(grounding, "require_reader", lambda *_a: None)
    monkeypatch.setattr(grounding.knowledge_api, "knowledge_access_predicate",
        lambda alias, principal: alias + (".ALLOW_HUMAN=1" if principal == ":actor" else ".ALLOW_AGENT=1"))
    monkeypatch.setattr(grounding.connection, "DATABASE_DIALECT", "pg")
    monkeypatch.setattr(grounding.connection, "execute_query",
        lambda sql, params: [dict(row) for row in db.execute(sql, params)])
    monkeypatch.setattr(grounding.content_security, "enforce", lambda *_a: None)
    monkeypatch.setattr(embedding_api, "search_authorized_knowledge", lambda *_a, **_kw: [])
    yield db, add
    db.close()


def ids(rows):
    return [row["entity_id"] for row in rows]


def test_yashandb_native_fulltext_constants_are_escaped_and_bounded():
    native=adapter('yashandb')
    fragment=native.channel_sql('fulltext',["x'); DROP TABLE ENTITIES;--"],'COSINE')
    assert native.fulltext_literal(["O'Brien"])=="'{O''Brien}'"
    assert fragment['params']=={}
    assert 'SCORE(' not in fragment['score']
    assert 'CONTAINS(ft.CONTENT,' in fragment['predicates'][0]
    assert ' UNION ' in fragment['predicates'][0]
    with pytest.raises(ValueError):native.fulltext_literal(['bad\nquery'])
    with pytest.raises(ValueError):native.fulltext_literal(['x']*25)


def test_yashandb_fulltext_id_union_preserves_dual_authority_before_limit():
    native=adapter('yashandb')
    fragment=native.channel_sql('fulltext',['billing'],'COSINE')
    db=sqlite3.connect(':memory:')
    db.create_function('CONTAINS',2,lambda body,_query:int('billing' in body))
    db.executescript('CREATE TABLE ENTITIES(ENTITY_ID TEXT,TITLE TEXT,CONTENT TEXT,ALLOW_HUMAN INT,ALLOW_AGENT INT)')
    db.executemany('INSERT INTO ENTITIES VALUES(?,?,?,?,?)',[
        ('a-private','billing','billing',1,0),('b-private','billing','billing',0,1),
        ('c-body','unrelated','billing',1,1),('d-title','billing','unrelated',1,1),
        ('e-both','billing','billing',1,1),('f-no-match','unrelated','unrelated',1,1)])
    try:
        sql=('SELECT e.ENTITY_ID FROM ENTITIES e WHERE e.ALLOW_HUMAN=1 AND e.ALLOW_AGENT=1 AND '
            +fragment['predicates'][0]+' ORDER BY e.ENTITY_ID LIMIT 2')
        assert [row[0] for row in db.execute(sql)]==['c-body','d-title']
        db.execute("UPDATE ENTITIES SET ALLOW_AGENT=0 WHERE ENTITY_ID='c-body'")
        assert [row[0] for row in db.execute(sql)]==['d-title','e-both']
    finally:db.close()


def test_bulk_loading_preserves_applicability_and_rechecks_each_original_reader(store,monkeypatch):
    from lib import continuity_promotions
    db,add=store
    add('derived',domain='billing');add('ordinary',domain='billing')
    db.execute("INSERT INTO CX_CONTINUITY_ARTIFACTS(ARTIFACT_ID,FAMILY,STATUS,CURRENT_REVISION_ID) VALUES('a','KNOWLEDGE','ACTIVE','r')")
    db.execute("INSERT INTO CX_CONTINUITY_ARTIFACT_REVS(ARTIFACT_ID,NATIVE_ENTITY_ID,REVISION_ID) VALUES('a','derived','r')")
    context=dict(candidate_digest='c'*64,intake=dict(decision_status='HISTORICAL',applicable_version='3.2.1'))
    calls=[];denied=[False]
    def authorize(actors,entities,**options):
        assert set(entities)=={'derived','ordinary'}
        calls.extend((actor,'derived') for actor in dict.fromkeys(actors))
        return {'derived':None if denied[0] else context}
    # This consumer test uses the batch authority boundary. Real original
    # reads, both actors and mid-read revocation have relational coverage in
    # test_knowledge_curated rather than synthetic incomplete candidate rows.
    monkeypatch.setattr(continuity_promotions,'original_source_contexts',authorize)
    result=grounding._load_candidates('human','agent',['derived','ordinary'])
    assert calls==[('human','derived'),('agent','derived')]
    assert result[0]['source_context']==context and 'source_context' not in result[1]
    denied[0]=True
    assert ids(grounding._load_candidates('human','agent',['derived','ordinary']))==['ordinary']


def test_metadata_and_tag_signals_recall_sources_whose_body_lacks_the_query(store):
    _db, add = store
    add("both", domain="billing", tag="billing")
    add("metadata", domain="billing")
    add("tag", tag="billing")
    for number in range(100):
        add("noise" + str(number), domain="unrelated", tag="other")
    result = grounding.search("human", "agent", "billing", strategy="hybrid")
    assert ids(result["items"]) == ["both", "metadata", "tag"]
    assert set(result["items"][0]["retrieval_rank"]["channel_ranks"]) == {"relational", "tag"}
    assert result["retrieval"]["ranking_generation_calls"] == 0
    assert result["retrieval"]["graph_engine"] == "NOT_REQUESTED"


def test_hybrid_source_checks_share_the_callers_transaction_and_recheck_both_readers(store,monkeypatch):
    from lib import continuity_promotions
    db,add=store
    add('derived',domain='billing');add('ordinary',domain='billing')
    db.execute("INSERT INTO CX_CONTINUITY_ARTIFACTS(ARTIFACT_ID,FAMILY,STATUS,CURRENT_REVISION_ID) VALUES('a','KNOWLEDGE','ACTIVE','r')")
    db.execute("INSERT INTO CX_CONTINUITY_ARTIFACT_REVS(ARTIFACT_ID,NATIVE_ENTITY_ID,REVISION_ID) VALUES('a','derived','r')")
    class Transaction:
        def query(self,sql,params):
            return [dict(row) for row in db.execute(sql,params)]
    tx=Transaction();calls=[];denied=[False]
    def authorize(actors,entities,*,transaction):
        assert transaction is tx and set(entities)=={'derived','ordinary'}
        calls.extend((actor,'derived') for actor in dict.fromkeys(actors))
        return {'derived':None if denied[0] else dict(candidate_digest='c'*64)}
    monkeypatch.setattr(continuity_promotions,'original_source_contexts',authorize)
    monkeypatch.setattr(grounding,'require_reader',lambda *_a,**_kw:None)
    monkeypatch.setattr(grounding.connection,'execute_transaction_callback',
        lambda *_a:pytest.fail('Source checks must not start an independent transaction under the caller locks'))
    result=grounding.search('human','agent','billing',strategy='hybrid',transaction=tx)
    assert ids(result['items'])==['derived','ordinary']
    assert calls==[('human','derived'),('agent','derived')]
    assert result['items'][0]['source_context']==dict(candidate_digest='c'*64)
    denied[0]=True
    assert ids(grounding.search('human','agent','billing',strategy='hybrid',transaction=tx)['items'])==['ordinary']


@pytest.mark.parametrize('channel',['relational','tag','graph'])
def test_domain_current_artifacts_are_filtered_before_the_channel_limit(store,channel):
    db,add=store
    add('anchor');add('z-current',domain='billing',tag='billing')
    for key,domain,status,current in [('anchor','domain','ACTIVE','r-anchor'),('z-current','domain','ACTIVE','r-current')]+[
            ('a-other-'+str(index),'other','ACTIVE','r-other-'+str(index)) for index in range(45)]+[
            ('b-old','domain','ACTIVE','newer'),('c-retired','domain','RETIRED','r-retired')]:
        if key not in {'anchor','z-current'}:add(key,domain='billing',tag='billing')
        revision='old' if key=='b-old' else current
        db.execute("INSERT INTO CX_CONTINUITY_ARTIFACTS VALUES(?,'KNOWLEDGE',?,?,?)",(key,domain,status,current))
        db.execute('INSERT INTO CX_CONTINUITY_ARTIFACT_REVS(ARTIFACT_ID,NATIVE_ENTITY_ID,REVISION_ID) VALUES(?,?,?)',(key,key,revision))
        if key!='anchor':edge(db,'anchor',key)
    result=signals.candidates('human','agent',['billing'],channel=channel,
        artifact_domain='domain',anchors=['anchor'] if channel=='graph' else (),limit=1)
    assert ids(result)==['z-current']


@pytest.mark.parametrize("channel", ["relational", "tag"])
def test_structured_signals_enforce_both_readers_lifecycle_and_explicit_sources(store, channel):
    _db, add = store
    for key, options in [("good", {}), ("other", {}), ("private-human", {"agent": 0}),
                         ("private-agent", {"human": 0}), ("retired", {"status": "ARCHIVED"}),
                         ("expired", {"expiry": "2000-01-01"})]:
        add(key, domain="billing", tag="billing", **options)
    assert ids(signals.candidates("human", "agent", ["billing"], channel=channel)) == ["good", "other"]
    assert ids(signals.candidates("human", "agent", ["billing"], channel=channel, entity_ids=["good"])) == ["good"]
    assert signals.candidates("human", "agent", ["billing"], channel=channel, entity_ids=[]) == []


def edge(db, source, target, target_type="KNOWLEDGE"):
    db.execute("INSERT INTO ENTITY_EDGES(SOURCE_ID,SOURCE_TYPE,TARGET_ID,TARGET_TYPE,STRENGTH,CONFIDENCE) VALUES (?, 'KNOWLEDGE', ?, ?, 1, 1)", (source, target, target_type))


def test_graph_rechecks_both_endpoints_and_revocation_on_each_use(store):
    db, add = store
    add("seed"); add("neighbor"); add("private", agent=0); add("expired", expiry="2000-01-01")
    for key in ("neighbor", "private", "expired"):
        edge(db, "seed", key)
    request = lambda **kw: signals.candidates("human", "agent", ["billing"], channel="graph", anchors=["seed"], **kw)
    assert ids(request()) == ["neighbor"]
    assert request(entity_ids=["seed"]) == []
    db.execute("UPDATE ENTITIES SET ALLOW_HUMAN=0 WHERE ENTITY_ID='seed'")
    assert request() == []
    db.execute("UPDATE ENTITIES SET ALLOW_HUMAN=1 WHERE ENTITY_ID='seed'")
    db.execute("UPDATE ENTITIES SET ALLOW_AGENT=0 WHERE ENTITY_ID='neighbor'")
    assert request() == []


def test_graph_excludes_execution_entities_and_ambiguous_legacy_ids(store):
    db, add = store
    add("seed"); add("neighbor"); add("wrong-type")
    edge(db, "seed", "neighbor", None)
    edge(db, "seed", "wrong-type", "TASK")
    assert ids(signals.candidates("human", "agent", ["billing"], channel="graph", anchors=["seed"])) == ["neighbor"]
    db.execute("INSERT INTO ENTITIES (ENTITY_ID,ENTITY_TYPE) VALUES ('neighbor','TASK')")
    assert signals.candidates("human", "agent", ["billing"], channel="graph", anchors=["seed"]) == []


def test_hybrid_runs_one_bounded_graph_hop_only_for_relationship_intent(store):
    db, add = store
    add("seed", domain="billing"); add("neighbor"); edge(db, "seed", "neighbor")
    result = grounding.search("human", "agent", "billing dependency", strategy="hybrid")
    assert set(ids(result["items"])) == {"seed", "neighbor"}
    assert result["retrieval"]["graph_engine"] == "RELATIONAL_ENTITY_EDGES"
    neighbor = next(item for item in result["items"] if item["entity_id"] == "neighbor")
    assert neighbor["retrieval_rank"]["channel_ranks"] == {"graph": 1}


def test_exact_native_edge_and_both_sources_reach_shared_answer_context(store,monkeypatch):
    db,add=store
    add('seed',domain='billing');add('neighbor');edge(db,'seed','neighbor')
    db.execute("UPDATE ENTITIES SET TITLE='Billing procedure',CONTENT='Billing uses a verified original receipt.' WHERE ENTITY_ID='seed'")
    question='Explain related sources for billing'
    retrieval=answer_planning.retrieve('human','agent',question)
    assert retrieval['status']=='MATCHED' and set(ids(retrieval['items']))=={'seed','neighbor'}
    planned=answer_planning.prepare(question,'p',dict(mode='KNOWLEDGE_ONLY',disclosure_profiles=['p']),retrieval)
    import json
    wire=json.loads(planned['messages'][-1]['content'])
    assert len(wire['authorized_sources'])==2 and len(wire['authorized_relationships'])==1
    link=wire['authorized_relationships'][0]
    assert link['edge_type']=='RELATED_TO' and link['source_citation']!=link['target_citation']
    assert wire['evidence_requirements'][0]['source_citations']==[1,2]
    assert retrieval['retrieval']['ranking_generation_calls']==0
    # Exercise the actual shared lineage reader used by both Portal and
    # Channel. Only the source-body reader is adapted to this SQLite harness.
    def read(actor,agent,key,expected='',**kwargs):
        rows=grounding._load_candidates(actor,agent,[key])
        if not rows:
            raise PermissionError('Knowledge unavailable')
        if expected and rows[0]['digest']!=expected:
            raise grounding.GroundingError('Knowledge version changed')
        return rows[0]
    monkeypatch.setattr(grounding,'citation',read)
    neighbor=next(item for item in planned['citations'] if item['entity_id']=='neighbor')
    grounding.validate_citation('human','agent',neighbor)
    dispatch=dict(requester_principal_id='human')
    business_channel_runtime._check_sources('agent',dispatch,[neighbor],{'human'})
    configured=dict(mode='KNOWLEDGE_ONLY',allow_model_supplement='N',disclosure_profiles=[],version=1)
    monkeypatch.setattr(portal_grounding,'policy',lambda:configured)
    result=portal_grounding.answer(dict(principal_id='human',agent_id='agent'),question,dict(profile_id='p'))
    assert result['answer_source']=='KNOWLEDGE_EXTRACTS' and len(result['citations'])==2
    db.execute("UPDATE ENTITY_EDGES SET EDGE_TYPE='CITES'")
    with pytest.raises(grounding.GroundingError,match='relationship evidence changed'):
        business_channel_runtime._check_sources('agent',dispatch,[neighbor],{'human'})
    db.execute("UPDATE ENTITY_EDGES SET EDGE_TYPE='RELATED_TO'")
    db.execute("UPDATE ENTITIES SET ALLOW_AGENT=0 WHERE ENTITY_ID='seed'")
    with pytest.raises(PermissionError):
        grounding.validate_citation('human','agent',neighbor)


def test_a_related_edge_cannot_prove_a_dependency_or_a_different_release(store):
    db,add=store
    add('seed',domain='billing');add('neighbor');edge(db,'seed','neighbor')
    db.execute("UPDATE ENTITIES SET TITLE='Billing guide',CONTENT='Billing v3.2.1 operation.' WHERE ENTITY_ID='seed'")
    # RELATED_TO is not DEPENDS_ON, and a source version cannot silently give
    # an unversioned neighbor that same applicability.
    result=answer_planning.retrieve('human','agent','Explain dependencies for billing')
    assert result['status']=='NO_MATCH'
    db.execute("UPDATE ENTITY_EDGES SET EDGE_TYPE='DEPENDS_ON'")
    result=answer_planning.retrieve('human','agent','Explain dependencies for billing v3.2.1')
    assert result['status']=='NO_MATCH'


def test_literal_query_tokens_cannot_become_wildcards_or_sql(store):
    _db, add = store
    add("match", domain="sales_100%"); add("noise", domain="salesX100more")
    assert ids(signals.candidates("human", "agent", ["sales_100%"], channel="relational")) == ["match"]
    assert signals.candidates("human", "agent", ["' OR 1=1 --"], channel="tag") == []


def test_signal_error_is_degraded_and_denial_is_fatal(store, monkeypatch):
    _db, add = store
    add("seed", domain="billing")
    def unavailable(*_a, **_kw):
        raise embedding_api.AuthorizedSearchUnavailable("private native detail")
    monkeypatch.setattr(signals, "candidates", unavailable)
    result = grounding.search("human", "agent", "billing", strategy="hybrid")
    assert {item["channel"] for item in result["retrieval"]["degradations"]} == {"relational", "tag"}
    assert "private native detail" not in str(result)
    monkeypatch.setattr(signals, "candidates", Mock(side_effect=PermissionError("denied")))
    with pytest.raises(PermissionError):
        grounding.search("human", "agent", "billing", strategy="hybrid")


def test_private_signal_counts_do_not_enter_public_answer_metadata(store):
    _db, add = store
    add("seed", domain="billing")
    result = grounding.search("human", "agent", "billing", strategy="hybrid")
    metadata = answer_planning._public_metadata(result)
    assert "candidate_count" not in metadata and "loaded_count" not in metadata
    assert "seed" not in str(metadata)


def test_structured_signals_affect_the_shared_answer_consumer_without_overriding_evidence(store, monkeypatch):
    db, add = store
    add("a-text-only")
    add("z-specific", domain="billing", tag="billing")
    db.execute("UPDATE ENTITIES SET TITLE='Billing procedure',CONTENT='Billing requires a verified receipt.'")
    monkeypatch.setattr(embedding_api, "search_authorized_knowledge",
        lambda *_a, **_kw: [{"entity_id": "a-text-only"}, {"entity_id": "z-specific"}])
    result = answer_planning.retrieve("human", "agent", "billing", strategy="hybrid")
    assert result["status"] == "MATCHED"
    assert ids(result["items"])[0] == "z-specific"
    assert set(result["items"][0]["retrieval_rank"]["channel_ranks"]) == {"keyword", "vector", "fulltext", "relational", "tag"}
    assert result["evidence_decision"]["rank_used_as_confidence"] is False


@pytest.mark.parametrize("database", ["oracle", "pg", "yashandb"])
def test_native_sql_boundary_retains_exact_scope_and_one_embedding(monkeypatch, database):
    native = adapter(database)
    monkeypatch.setattr(embedding_api, "knowledge_retrieval_adapter", native)
    monkeypatch.setattr(knowledge_candidates, 'native', native)
    monkeypatch.setattr(grounding, "require_reader", lambda *_a: None)
    context = {"space": {"space_id": "s"}, "contract": {"contract_id": "c", "distance_metric": "COSINE"}}
    embedding = Mock(return_value=(context, "[0.1,0.2]"))
    monkeypatch.setattr(embedding_api, "_query_embedding", embedding)
    query = Mock(return_value=[])
    monkeypatch.setattr(embedding_api, "execute_query", query)
    assert embedding_api.search_authorized_knowledge("billing", channel="vector", actor="human", agent="agent", entity_ids=["11"]) == []
    assert embedding.call_count == 1
    sql, params = query.call_args.args
    assert params["emb_space"] == "s" and params["emb_contract"] == "c"
    assert "em.VALIDATION_STATUS='VERIFIED'" in sql
    assert "kap.PRINCIPAL_ID=:actor" in sql and "kap.PRINCIPAL_ID=:agent" in sql
    assert params["source_id0"] == "11"
