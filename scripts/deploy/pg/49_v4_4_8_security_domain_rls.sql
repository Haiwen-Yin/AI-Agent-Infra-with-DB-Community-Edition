-- v4.4.8 Security Domain member enforcement for governed Channel resources.
-- Identity resolves first from a dedicated database role. The custom setting
-- remains useful only for the app's bounded transaction context and cannot
-- override a mapped runtime role.
CREATE OR REPLACE FUNCTION public.current_agent_identity() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $current_agent_identity$
    SELECT bound.agent_id::text
    FROM public.agent_db_identity bound
    WHERE bound.role_name = current_user
      AND EXISTS (
          SELECT 1
          FROM public.agent_db_identity expected
          WHERE expected.role_name = bound.role_name
            AND expected.agent_id = NULLIF(current_setting('app.current_agent_id', true), '')
      )

    UNION ALL

    SELECT NULLIF(current_setting('app.current_agent_id', true), '')
    WHERE NOT EXISTS (SELECT 1 FROM public.agent_db_identity WHERE role_name = current_user)
$current_agent_identity$;

CREATE OR REPLACE FUNCTION public.cx_channel_domain_member(p_channel_id varchar, p_principal_id varchar)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_channel_domain_member$
    SELECT EXISTS (
        SELECT 1
        FROM public.cx_channels channel
        JOIN public.cx_domain_members domain_member
          ON domain_member.security_domain_id = channel.security_domain_id
         AND domain_member.principal_id = p_principal_id
         AND domain_member.status = 'ACTIVE'
         AND (domain_member.valid_until IS NULL OR domain_member.valid_until > current_timestamp)
        JOIN public.cx_principals principal
          ON principal.principal_id = p_principal_id
         AND principal.status = 'ACTIVE'
        WHERE channel.channel_id = p_channel_id
          AND channel.status = 'ACTIVE'
    )
$cx_channel_domain_member$;
REVOKE ALL ON FUNCTION public.cx_channel_domain_member(varchar, varchar) FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.cx_agent_channel_member(p_channel_id varchar, p_principal_id varchar)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_agent_channel_member$
    SELECT p_principal_id = public.current_agent_identity()
       AND EXISTS (
           SELECT 1 FROM public.cx_channel_members member
           WHERE member.channel_id = p_channel_id
             AND member.principal_id = p_principal_id
             AND member.status = 'ACTIVE'
             AND (member.valid_until IS NULL OR member.valid_until > current_timestamp)
       )
       AND public.cx_channel_domain_member(p_channel_id, p_principal_id)
$cx_agent_channel_member$;
REVOKE ALL ON FUNCTION public.cx_agent_channel_member(varchar, varchar) FROM PUBLIC;
