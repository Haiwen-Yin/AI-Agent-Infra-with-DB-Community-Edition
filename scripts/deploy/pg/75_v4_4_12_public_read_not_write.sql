-- Permissive read policies must never authorize another owner's mutations.
DROP POLICY IF EXISTS cx_entity_native_update_owner ON public.entities;
CREATE POLICY cx_entity_native_update_owner ON public.entities AS RESTRICTIVE FOR UPDATE TO ai_agent_runtime
USING (owned_by_agent::text=public.current_agent_identity())
WITH CHECK (owned_by_agent::text=public.current_agent_identity());
DROP POLICY IF EXISTS cx_entity_native_delete_owner ON public.entities;
CREATE POLICY cx_entity_native_delete_owner ON public.entities AS RESTRICTIVE FOR DELETE TO ai_agent_runtime
USING (owned_by_agent::text=public.current_agent_identity());
DROP POLICY IF EXISTS cx_entity_native_insert_owner ON public.entities;
CREATE POLICY cx_entity_native_insert_owner ON public.entities AS RESTRICTIVE FOR INSERT TO ai_agent_runtime
WITH CHECK (owned_by_agent::text=public.current_agent_identity());
