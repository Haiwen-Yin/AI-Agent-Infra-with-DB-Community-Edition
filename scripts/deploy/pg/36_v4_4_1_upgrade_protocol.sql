-- v4.4.1 additive approval evidence for the controlled-upgrade protocol.
-- Every approval is attributable. Runtime agents submit their own vote through
-- the authenticated Gateway; no browser-supplied Agent identity is trusted.
CREATE TABLE IF NOT EXISTS cx_upgrade_approvals (
    approval_id varchar(128) PRIMARY KEY,
    upgrade_id varchar(128) NOT NULL,
    approval_kind varchar(32) NOT NULL,
    principal_id varchar(128) NOT NULL,
    decision varchar(32) NOT NULL,
    term bigint,
    fencing_token bigint,
    reason varchar(2000) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(upgrade_id, approval_kind, principal_id)
);
CREATE INDEX IF NOT EXISTS idx_cx_upgrade_approval_plan ON cx_upgrade_approvals(upgrade_id,approval_kind,decision);
