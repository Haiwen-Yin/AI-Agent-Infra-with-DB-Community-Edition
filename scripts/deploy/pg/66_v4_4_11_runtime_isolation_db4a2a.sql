-- v4.4.11 runtime isolation evidence and database-mediated Agent collaboration.
CREATE TABLE IF NOT EXISTS cx_runtime_isolation_contracts (
 contract_id varchar(128) PRIMARY KEY, agent_id varchar(128) NOT NULL,
 instance_id varchar(128) NOT NULL, isolation_level varchar(32) NOT NULL,
 enforcement_mode varchar(32) NOT NULL, runtime_adapter varchar(128) NOT NULL,
 runtime_identity varchar(256), boundaries_json text NOT NULL,
 policy_digest varchar(256), rootfs_digest varchar(256), evidence_ref varchar(512),
 status varchar(32) NOT NULL, version bigint NOT NULL DEFAULT 1,
 created_by varchar(128) NOT NULL, updated_by varchar(128) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT current_timestamp,
 updated_at timestamptz NOT NULL DEFAULT current_timestamp,
 UNIQUE(agent_id, instance_id),
 CHECK (isolation_level IN ('SHARED','DOMAIN_ISOLATED','DEDICATED_RUNTIME','DEDICATED_CONTAINER','DEDICATED_VM')),
 CHECK (enforcement_mode IN ('VERIFIED','UNVERIFIED','NOT_APPLICABLE'))
);
CREATE TABLE IF NOT EXISTS cx_db4a2a_dispatches (
 dispatch_id varchar(128) PRIMARY KEY, task_id varchar(256) NOT NULL,
 sender_principal_id varchar(128) NOT NULL, receiver_agent_id varchar(128) NOT NULL,
 context_ref varchar(256) NOT NULL, snapshot_digest varchar(256) NOT NULL,
 expected_version bigint NOT NULL, scope_ref varchar(256) NOT NULL,
 source_branch varchar(256), branch_policy varchar(32) NOT NULL,
 transport varchar(32) NOT NULL, status varchar(32) NOT NULL,
 child_branch_id varchar(128), created_at timestamptz NOT NULL DEFAULT current_timestamp,
 updated_at timestamptz NOT NULL DEFAULT current_timestamp,
 CHECK (expected_version > 0),
 CHECK (branch_policy IN ('READ_ONLY','CHILD_BRANCH_WRITE')),
 CHECK (transport IN ('DB_MEDIATED','A2A_PAYLOAD'))
);
CREATE INDEX IF NOT EXISTS idx_runtime_isolation_agent ON cx_runtime_isolation_contracts(agent_id,status);
CREATE INDEX IF NOT EXISTS idx_db4a2a_participants ON cx_db4a2a_dispatches(sender_principal_id,receiver_agent_id,created_at);
ALTER TABLE cx_runtime_isolation_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_runtime_isolation_contracts FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_db4a2a_dispatches ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_db4a2a_dispatches FORCE ROW LEVEL SECURITY;
DO $cx_v411_owner_policy$
DECLARE item record;
BEGIN
 FOR item IN
   SELECT c.relname table_name, pg_get_userbyid(c.relowner) owner_name
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname IN ('cx_runtime_isolation_contracts','cx_db4a2a_dispatches')
 LOOP
   EXECUTE format('DROP POLICY IF EXISTS cx_trusted_schema_owner ON public.%I', item.table_name);
   EXECUTE format('CREATE POLICY cx_trusted_schema_owner ON public.%I TO %I USING (true) WITH CHECK (true)', item.table_name, item.owner_name);
 END LOOP;
END
$cx_v411_owner_policy$;
