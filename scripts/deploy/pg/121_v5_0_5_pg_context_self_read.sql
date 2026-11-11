-- v5.0.5 native own-context reads; no public/shared or write permission.
ALTER TABLE public.workspace_context ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx505_context_self_read ON public.workspace_context;
CREATE POLICY cx505_context_self_read ON public.workspace_context AS PERMISSIVE FOR SELECT TO ai_agent_runtime USING (agent_id = public.current_agent_identity() AND EXISTS (
  SELECT 1 FROM public.cx_principals p
  WHERE p.principal_id = public.current_agent_identity() AND p.status = 'ACTIVE'
));
DROP POLICY IF EXISTS cx505_context_self_bound ON public.workspace_context;
CREATE POLICY cx505_context_self_bound ON public.workspace_context AS RESTRICTIVE FOR SELECT TO ai_agent_runtime USING (agent_id = public.current_agent_identity() AND EXISTS (
  SELECT 1 FROM public.cx_principals p
  WHERE p.principal_id = public.current_agent_identity() AND p.status = 'ACTIVE'
));
