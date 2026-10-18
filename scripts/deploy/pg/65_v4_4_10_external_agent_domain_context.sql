-- v4.4.10 PostgreSQL external Agent Security Domain context closure.
-- A dedicated Agent login must see its own active domain memberships and the
-- corresponding domain rows when creating additional Gateway instances.
ALTER TABLE cx_domain_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_domain_members FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_domain_members_agent_self ON cx_domain_members;
CREATE POLICY cx_domain_members_agent_self ON cx_domain_members FOR SELECT
  USING (principal_id = public.current_agent_identity());

CREATE OR REPLACE FUNCTION public.cx_agent_security_domain_member(p_domain_id varchar)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_agent_security_domain_member$
  SELECT EXISTS (
    SELECT 1
    FROM public.cx_domain_members member
    WHERE member.security_domain_id = p_domain_id
      AND member.principal_id = public.current_agent_identity()
      AND member.status = 'ACTIVE'
      AND (member.valid_until IS NULL OR member.valid_until > current_timestamp)
  )
$cx_agent_security_domain_member$;
REVOKE ALL ON FUNCTION public.cx_agent_security_domain_member(varchar) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cx_agent_security_domain_member(varchar) TO ai_agent_runtime;

ALTER TABLE cx_security_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_security_domains FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_security_domains_agent_member ON cx_security_domains;
CREATE POLICY cx_security_domains_agent_member ON cx_security_domains FOR SELECT
  USING (public.cx_agent_security_domain_member(security_domain_id));

-- FORCE RLS also applies to a non-superuser table owner. Converge one explicit
-- owner policy on every forced table before native bootstrap and postflight;
-- ordinary Agent roles are not members of the Schema Owner and continue to be
-- restricted by their table-specific policies.
DO $cx_force_rls_owner_closure$
DECLARE
  item record;
BEGIN
  FOR item IN
    SELECT class.relname AS table_name,
           pg_get_userbyid(class.relowner) AS owner_name
      FROM pg_class class
      JOIN pg_namespace namespace ON namespace.oid = class.relnamespace
     WHERE namespace.nspname = 'public'
       AND class.relkind IN ('r', 'p')
       AND class.relforcerowsecurity
  LOOP
    EXECUTE format(
      'DROP POLICY IF EXISTS %I ON public.%I',
      'cx_trusted_schema_owner', item.table_name
    );
    EXECUTE format(
      'CREATE POLICY %I ON public.%I TO %I USING (true) WITH CHECK (true)',
      'cx_trusted_schema_owner', item.table_name, item.owner_name
    );
  END LOOP;
END
$cx_force_rls_owner_closure$;
