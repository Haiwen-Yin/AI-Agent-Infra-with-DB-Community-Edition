-- Portal Agent ownership isolation for multi-node Admin Agent deployments.
BEGIN;
ALTER TABLE agent_registry ADD COLUMN IF NOT EXISTS portal_node_id varchar(128);
CREATE INDEX IF NOT EXISTS idx_ar_portal_node
    ON agent_registry(portal_node_id, status);
COMMIT;
