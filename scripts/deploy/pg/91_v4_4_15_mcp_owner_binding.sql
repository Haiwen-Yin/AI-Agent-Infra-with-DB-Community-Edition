-- Keep the discovery view read-only even if a legacy broad grant is repeated.
CREATE OR REPLACE FUNCTION public.cx91_readonly_mcp_view() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $cx91$
BEGIN
  RAISE EXCEPTION 'MCP discovery view is read-only' USING ERRCODE='42501';
END $cx91$;
REVOKE ALL ON FUNCTION public.cx91_readonly_mcp_view() FROM PUBLIC;
CREATE OR REPLACE TRIGGER CX415_MCP_VIEW_READONLY
INSTEAD OF INSERT OR UPDATE OR DELETE ON public.CX_MCP_EXPOSED_TOOLS
FOR EACH ROW EXECUTE FUNCTION public.cx91_readonly_mcp_view();
