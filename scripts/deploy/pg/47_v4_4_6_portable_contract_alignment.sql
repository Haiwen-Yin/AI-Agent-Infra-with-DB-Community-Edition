-- Align PostgreSQL physical names with the adapter-neutral runtime contract.
DO $$ BEGIN IF to_regclass('cx_registration_field_policies') IS NOT NULL AND to_regclass('cx_reg_field_policies') IS NULL THEN ALTER TABLE cx_registration_field_policies RENAME TO cx_reg_field_policies; END IF; END $$;
DO $$ BEGIN IF to_regclass('cx_human_registration_tokens') IS NOT NULL AND to_regclass('cx_human_reg_tokens') IS NULL THEN ALTER TABLE cx_human_registration_tokens RENAME TO cx_human_reg_tokens; END IF; END $$;
DO $$ BEGIN IF to_regclass('cx_external_identity_bindings') IS NOT NULL AND to_regclass('cx_external_id_bindings') IS NULL THEN ALTER TABLE cx_external_identity_bindings RENAME TO cx_external_id_bindings; END IF; END $$;
DO $$ BEGIN IF to_regclass('cx_external_login_transactions') IS NOT NULL AND to_regclass('cx_ext_login_txns') IS NULL THEN ALTER TABLE cx_external_login_transactions RENAME TO cx_ext_login_txns; END IF; END $$;
DO $$ BEGIN IF to_regclass('cx_portal_connection_policies') IS NOT NULL AND to_regclass('cx_portal_conn_policies') IS NULL THEN ALTER TABLE cx_portal_connection_policies RENAME TO cx_portal_conn_policies; END IF; END $$;
DO $$ BEGIN IF to_regclass('cx_graph_capability_posture') IS NOT NULL AND to_regclass('cx_graph_cap_posture') IS NULL THEN ALTER TABLE cx_graph_capability_posture RENAME TO cx_graph_cap_posture; END IF; END $$;
