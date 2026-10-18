-- v4.4.10 Agent knowledge provenance: relational org/group snapshot plus graph trace.
CREATE TABLE IF NOT EXISTS cx_knowledge_contexts (
    context_id varchar(128) PRIMARY KEY, entity_id varchar(128) NOT NULL UNIQUE,
    agent_id varchar(128) NOT NULL, principal_id varchar(128), organization_id varchar(128),
    organization_chain_json text NOT NULL, responsible_groups_json text NOT NULL,
    execution_groups_json text NOT NULL, sharing_scope varchar(32) NOT NULL,
    graph_snapshot_digest varchar(64) NOT NULL, reason varchar(2000) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (sharing_scope IN ('PUBLIC_COMPANY','ORGANIZATION_SUBTREE','ORGANIZATION_LEVEL','PRINCIPAL_PRIVATE'))
);
CREATE INDEX IF NOT EXISTS idx_cx_kctx_agent ON cx_knowledge_contexts(agent_id,created_at);
CREATE INDEX IF NOT EXISTS idx_cx_kctx_org ON cx_knowledge_contexts(organization_id,sharing_scope);
ALTER TABLE cx_knowledge_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_knowledge_contexts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_kctx_scope ON cx_knowledge_contexts;
CREATE POLICY cx_kctx_scope ON cx_knowledge_contexts USING (principal_id = public.current_agent_identity() OR organization_id IS NULL);
