-- Keep migration 53's SESSION_USER plus bound-identity agreement unchanged.
-- Parent RLS is not evaluated when a client addresses a leaf directly.
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT relid::regclass AS name FROM pg_partition_tree('public.entities') WHERE level>0 LOOP
    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %s FROM PUBLIC', t.name);
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ai_agent_runtime') THEN
      EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %s FROM ai_agent_runtime', t.name);
    END IF;
  END LOOP;
END $$;
