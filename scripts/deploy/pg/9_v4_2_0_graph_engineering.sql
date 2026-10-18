-- v4.2.0 Graph Engineering - PostgreSQL 18 / Apache AGE execution graph
CREATE EXTENSION IF NOT EXISTS age;
-- AGE is provisioned by a privileged PostgreSQL operator.  The extension's
-- SQL objects are usable by the runtime role after the documented ag_catalog
-- grants; LOAD is superuser-only on hardened installations and is not needed
-- for an already-installed extension.
-- AGE creates graph metadata with an unqualified graphid operator class.
-- Keep the extension namespace visible for the graph namespace bootstrap
-- even when the deployment client runs each statement in autocommit mode.
SET search_path = public, ag_catalog;

CREATE TABLE IF NOT EXISTS graph_definitions (
    graph_id varchar(128) PRIMARY KEY, graph_name varchar(256) NOT NULL,
    description varchar(2000), owner_ref varchar(256) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED','ARCHIVED')),
    metadata_json text, created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS graph_versions (
    graph_version_id varchar(128) PRIMARY KEY, graph_id varchar(128) NOT NULL REFERENCES graph_definitions(graph_id),
    version_no integer NOT NULL, version_label varchar(128),
    status varchar(32) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','VALIDATED','PUBLISHED','DEPRECATED','ARCHIVED')),
    parent_version_id varchar(128) REFERENCES graph_versions(graph_version_id), schema_version varchar(32) NOT NULL,
    input_schema_json text, output_schema_json text, budget_json text, definition_digest varchar(128), signature text,
    validation_diagnostics_json text, risk_level varchar(32) CHECK (risk_level IS NULL OR risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    actor_id varchar(256) NOT NULL, reason varchar(2000) NOT NULL, source_run_id varchar(128), source_checkpoint_id varchar(128),
    created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (graph_id, version_no)
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id) ON DELETE CASCADE,
    node_key varchar(256) NOT NULL, node_type varchar(128) NOT NULL, type_version varchar(64) NOT NULL,
    config_json text, input_schema_json text, output_schema_json text,
    side_effect_class varchar(32) NOT NULL DEFAULT 'NONE' CHECK (side_effect_class IN ('NONE','DB_TRANSACTIONAL','IDEMPOTENT_EXTERNAL','NON_IDEMPOTENT')),
    capability_json text, resource_scope_json text, budget_json text, created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (graph_version_id, node_key)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id) ON DELETE CASCADE,
    source_node_key varchar(256) NOT NULL, target_node_key varchar(256) NOT NULL,
    edge_kind varchar(32) NOT NULL DEFAULT 'NORMAL', decision_type varchar(64) NOT NULL DEFAULT 'FIXED',
    condition_json text, config_json text, order_index integer NOT NULL DEFAULT 0, join_key varchar(256),
    created_at timestamp NOT NULL DEFAULT current_timestamp, UNIQUE (graph_version_id, edge_id)
);

CREATE TABLE IF NOT EXISTS graph_aliases (
    graph_id varchar(128) NOT NULL REFERENCES graph_definitions(graph_id), alias_name varchar(128) NOT NULL,
    graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id), actor_id varchar(256) NOT NULL,
    reason varchar(2000) NOT NULL, updated_at timestamp NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (graph_id, alias_name)
);

CREATE TABLE IF NOT EXISTS graph_type_registry (
    type_id varchar(128) PRIMARY KEY, type_kind varchar(32) NOT NULL, type_name varchar(128) NOT NULL,
    type_version varchar(64) NOT NULL, manifest_json text, status varchar(32) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','DISABLED','DEPRECATED')), actor_id varchar(256) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp, UNIQUE (type_kind, type_name, type_version)
);

CREATE TABLE IF NOT EXISTS graph_compile_plans (
    plan_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id),
    compiler_version varchar(64) NOT NULL, definition_digest varchar(128) NOT NULL, plan_json text NOT NULL,
    plan_digest varchar(128) NOT NULL, diagnostics_json text, risk_level varchar(32) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp, UNIQUE (graph_version_id)
);

CREATE INDEX IF NOT EXISTS idx_graph_version_graph ON graph_versions(graph_id, status, version_no);
CREATE INDEX IF NOT EXISTS idx_graph_node_version ON graph_nodes(graph_version_id, node_key);
CREATE INDEX IF NOT EXISTS idx_graph_edge_version ON graph_edges(graph_version_id, source_node_key, order_index);
CREATE INDEX IF NOT EXISTS idx_graph_alias_version ON graph_aliases(graph_version_id);
CREATE INDEX IF NOT EXISTS idx_graph_type_lookup ON graph_type_registry(type_kind, type_name, type_version, status);

-- AGE graph namespace is kept separate from the relational contract.  The
-- shared service never emits Cypher; adapter hooks maintain this projection.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'ai_execution_graph') THEN
        PERFORM ag_catalog.create_graph('ai_execution_graph');
    END IF;
END $$;
