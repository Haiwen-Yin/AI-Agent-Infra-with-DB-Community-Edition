-- v4.4.11 root bootstrap, Host Manager, and runtime identity leases.
CREATE TABLE IF NOT EXISTS cx_runtime_host_profiles (
 node_id varchar(128) PRIMARY KEY, host_manager_version varchar(128),
 bootstrap_state varchar(32) NOT NULL, root_remote_login varchar(16) NOT NULL,
 recovery_channel varchar(512), uid_min integer NOT NULL, uid_max integer NOT NULL,
 preflight_digest varchar(128), created_by varchar(128) NOT NULL,
 updated_by varchar(128) NOT NULL, last_preflight_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT current_timestamp,
 updated_at timestamptz NOT NULL DEFAULT current_timestamp,
 CHECK (bootstrap_state IN ('PREFLIGHT_FAILED','PREFLIGHT_PASSED','VERIFIED','DRAIN','REVOKED')),
 CHECK (root_remote_login IN ('ENABLED','DISABLED')),
 CHECK (uid_min >= 100000 AND uid_max > uid_min)
);
CREATE TABLE IF NOT EXISTS cx_runtime_uid_leases (
 lease_id varchar(128) PRIMARY KEY, node_id varchar(128) NOT NULL,
 agent_id varchar(128) NOT NULL, instance_id varchar(128) NOT NULL,
 runtime_uid integer NOT NULL, runtime_gid integer NOT NULL,
 status varchar(32) NOT NULL, created_by varchar(128) NOT NULL,
 reason varchar(2000) NOT NULL, released_by varchar(128),
 release_reason varchar(2000), created_at timestamptz NOT NULL DEFAULT current_timestamp,
 released_at timestamptz,
 UNIQUE(node_id,runtime_uid), UNIQUE(node_id,agent_id,instance_id),
 CHECK (status IN ('ACTIVE','RELEASED','REVOKED')),
 CHECK (runtime_uid > 0 AND runtime_gid > 0)
);
CREATE INDEX IF NOT EXISTS idx_runtime_uid_agent ON cx_runtime_uid_leases(agent_id,instance_id,status);
ALTER TABLE cx_runtime_host_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_runtime_host_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_runtime_uid_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_runtime_uid_leases FORCE ROW LEVEL SECURITY;
DO $cx_v411_host_owner_policy$
DECLARE item record;
BEGIN
 FOR item IN
   SELECT c.relname table_name, pg_get_userbyid(c.relowner) owner_name
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname IN ('cx_runtime_host_profiles','cx_runtime_uid_leases')
 LOOP
   EXECUTE format('DROP POLICY IF EXISTS cx_trusted_schema_owner ON public.%I', item.table_name);
   EXECUTE format('CREATE POLICY cx_trusted_schema_owner ON public.%I TO %I USING (true) WITH CHECK (true)', item.table_name, item.owner_name);
 END LOOP;
END
$cx_v411_host_owner_policy$;
INSERT INTO cx_role_templates(role_code,display_name,permissions_json,data_scopes_json)
VALUES ('HOST_PROVISIONER','Host Provisioner','["hosts.read","hosts.manage","agents.read","agents.manage","agents.operate","approvals.read","audit.read"]','["ALL"]')
ON CONFLICT (role_code) DO UPDATE SET display_name=EXCLUDED.display_name,permissions_json=EXCLUDED.permissions_json,
 data_scopes_json=EXCLUDED.data_scopes_json,version=cx_role_templates.version+1,updated_at=current_timestamp;
