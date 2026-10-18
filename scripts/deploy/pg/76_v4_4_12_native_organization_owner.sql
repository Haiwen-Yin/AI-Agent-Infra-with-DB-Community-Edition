-- Resolve native organization access through the active Human PRIMARY_OWNER.
-- Evaluate scope facts inside the database without granting policy mutation.
CREATE OR REPLACE FUNCTION public.cx_native_knowledge_read(p_id text, p_kind text, p_owner text, p_visibility text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT p_kind<>'KNOWLEDGE' OR (
   EXISTS (SELECT 1 FROM public.cx_knowledge_access_policies k
     WHERE k.entity_id=p_id AND k.status='ACTIVE' AND k.valid_from<=CURRENT_TIMESTAMP
       AND (k.valid_until IS NULL OR k.valid_until>CURRENT_TIMESTAMP)
       AND (k.scope_type='PUBLIC_COMPANY'
         OR (k.scope_type='PRINCIPAL_PRIVATE' AND k.principal_id=public.current_agent_identity())
         OR (k.scope_type IN ('ORGANIZATION_SUBTREE','ORGANIZATION_LEVEL') AND EXISTS (
           SELECT 1 FROM public.cx_organization_members m
           JOIN public.cx_organization_closure c ON c.descendant_id=m.organization_id
           JOIN CX_AGENT_RELATIONSHIPS r ON r.PRINCIPAL_ID=m.PRINCIPAL_ID
              JOIN CX_PRINCIPALS h ON h.PRINCIPAL_ID=r.PRINCIPAL_ID
              JOIN CX_PRINCIPALS a ON a.PRINCIPAL_ID=r.AGENT_ID
              JOIN CX_ORGANIZATIONS mo ON mo.ORGANIZATION_ID=m.ORGANIZATION_ID
              JOIN CX_ORGANIZATIONS ko ON ko.ORGANIZATION_ID=k.ORGANIZATION_ID
              WHERE r.AGENT_ID=public.current_agent_identity() AND m.STATUS='ACTIVE'
                AND r.RELATIONSHIP_ROLE='PRIMARY_OWNER' AND r.STATUS='ACTIVE'
                AND (r.ENDED_AT IS NULL OR r.ENDED_AT>CURRENT_TIMESTAMP)
                AND h.PRINCIPAL_TYPE='HUMAN' AND h.STATUS='ACTIVE' AND a.STATUS='ACTIVE'
                AND mo.STATUS='ACTIVE' AND ko.STATUS='ACTIVE'
                AND mo.VALID_FROM<=CURRENT_TIMESTAMP AND (mo.VALID_UNTIL IS NULL OR mo.VALID_UNTIL>CURRENT_TIMESTAMP)
                AND ko.VALID_FROM<=CURRENT_TIMESTAMP AND (ko.VALID_UNTIL IS NULL OR ko.VALID_UNTIL>CURRENT_TIMESTAMP)
             AND m.valid_from<=CURRENT_TIMESTAMP AND (m.valid_until IS NULL OR m.valid_until>CURRENT_TIMESTAMP)
             AND c.ancestor_id=k.organization_id
             AND (k.scope_type='ORGANIZATION_SUBTREE' OR c.depth<=k.hierarchy_depth)))))
   OR (NOT EXISTS (SELECT 1 FROM public.cx_knowledge_access_policies k WHERE k.entity_id=p_id)
       AND (p_owner=public.current_agent_identity() OR p_visibility='PUBLIC')));
$$;
REVOKE ALL ON FUNCTION public.cx_native_knowledge_read(text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cx_native_knowledge_read(text,text,text,text) TO ai_agent_runtime;
DROP POLICY IF EXISTS cx_knowledge_native_scope ON public.entities;
CREATE POLICY cx_knowledge_native_scope ON public.entities AS RESTRICTIVE FOR SELECT TO ai_agent_runtime
USING (public.cx_native_knowledge_read(entity_id::text,entity_type::text,owned_by_agent::text,visibility::text));
DROP POLICY IF EXISTS cx_knowledge_native_shared ON public.entities;
CREATE POLICY cx_knowledge_native_shared ON public.entities FOR SELECT TO ai_agent_runtime
USING (entity_type='KNOWLEDGE' AND public.current_agent_identity() IS NOT NULL
  AND public.cx_native_knowledge_read(entity_id::text,entity_type::text,owned_by_agent::text,visibility::text));
