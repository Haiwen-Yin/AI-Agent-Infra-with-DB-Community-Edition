-- v4.4.9 PostgreSQL caller identity and runtime privilege closure.
-- SECURITY DEFINER changes current_user to the function owner. session_user
-- remains the authenticated dedicated Agent login and cannot be forged with a
-- custom setting or by reusing a pooled connection under another login.
CREATE OR REPLACE FUNCTION public.current_agent_identity() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $current_agent_identity$
    SELECT bound.agent_id::text
    FROM public.agent_db_identity bound
    WHERE bound.role_name = session_user
      AND bound.agent_id = NULLIF(current_setting('app.current_agent_id', true), '')
$current_agent_identity$;
REVOKE ALL ON FUNCTION public.current_agent_identity() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_agent_identity() TO ai_agent_runtime;

-- Agent provisioning historically granted every current table to the shared
-- runtime role. Remove control-plane tables explicitly; FORCE RLS remains a
-- second boundary, not a substitute for least privilege.
DO $cx_runtime_boundary$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'cx_platform_commands', 'cx_platform_command_executors',
        'cx_platform_maintenance_tasks', 'cx_platform_maintenance_attempts',
        'cx_platform_safe_autonomy_policies', 'cx_platform_knowledge',
        'cx_platform_knowledge_chunks', 'cx_platform_knowledge_grants',
        'cx_database_isolation_inventory', 'cx_platform_admin_commands',
        'cx_platform_capabilities', 'cx_platform_capability_dependencies',
        'cx_platform_capability_history'
    ] LOOP
        IF to_regclass('public.' || table_name) IS NOT NULL THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM ai_agent_runtime', table_name);
        END IF;
    END LOOP;
END
$cx_runtime_boundary$;
