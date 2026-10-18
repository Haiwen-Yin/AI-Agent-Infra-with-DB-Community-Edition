-- v4.4.5 immutable Graph Run contract snapshot
ALTER TABLE graph_runs ADD COLUMN IF NOT EXISTS definition_digest varchar(128);
ALTER TABLE graph_runs ADD COLUMN IF NOT EXISTS plan_digest varchar(128);
ALTER TABLE graph_runs ADD COLUMN IF NOT EXISTS compatibility_level varchar(32);
ALTER TABLE graph_runs ADD COLUMN IF NOT EXISTS state_schema_version varchar(64);
ALTER TABLE graph_runs ADD COLUMN IF NOT EXISTS budget_schema_version varchar(64);

UPDATE graph_runs r
SET definition_digest = p.definition_digest,
    plan_digest = p.plan_digest,
    compatibility_level = 'COMPATIBLE',
    state_schema_version = v.schema_version,
    budget_schema_version = 'graph-budget/1'
FROM graph_compile_plans p
JOIN graph_versions v ON v.graph_version_id = p.graph_version_id
WHERE p.plan_id = r.plan_id
  AND p.graph_version_id = r.graph_version_id
  AND p.definition_digest = v.definition_digest;
