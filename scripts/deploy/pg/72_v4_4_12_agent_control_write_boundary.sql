-- Registry/lifecycle writes go through the authenticated platform control plane.
REVOKE INSERT, UPDATE, DELETE ON public.agent_registry, public.cx_principals FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE ON public.agent_registry, public.cx_principals FROM ai_agent_runtime;
