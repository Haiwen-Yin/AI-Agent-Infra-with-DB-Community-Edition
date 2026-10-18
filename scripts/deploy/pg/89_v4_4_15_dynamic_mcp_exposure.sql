-- Explicit dynamic MCP exposure; existing tools remain closed by default.
ALTER TABLE TOOL_REGISTRY ADD COLUMN IF NOT EXISTS MCP_EXPOSED CHAR(1) DEFAULT 'N';
UPDATE TOOL_REGISTRY SET MCP_EXPOSED='N' WHERE MCP_EXPOSED IS NULL;
ALTER TABLE TOOL_REGISTRY ALTER COLUMN MCP_EXPOSED SET DEFAULT 'N';
ALTER TABLE TOOL_REGISTRY ALTER COLUMN MCP_EXPOSED SET NOT NULL;
DO $cx89$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='tool_registry'::regclass AND conname='cx415_tool_mcp_flag') THEN
    ALTER TABLE TOOL_REGISTRY ADD CONSTRAINT CX415_TOOL_MCP_FLAG CHECK (MCP_EXPOSED IN ('Y','N'));
  END IF;
END $cx89$;

-- Legacy Agents may maintain unexposed tool metadata. Only the schema owner
-- serving authenticated control-plane operations may change an exposed tool
-- or set its exposure flag. A table-level legacy UPDATE grant cannot bypass it.
CREATE OR REPLACE FUNCTION public.cx89_guard_mcp_tool() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $cx89guard$
DECLARE owner_name name;
BEGIN
  SELECT pg_get_userbyid(relowner) INTO owner_name FROM pg_class WHERE oid=TG_RELID;
  IF session_user<>owner_name THEN
    IF NEW.mcp_exposed='Y' THEN
      RAISE EXCEPTION 'MCP exposure requires control-plane authority' USING ERRCODE='42501';
    END IF;
    IF TG_OP='UPDATE' AND OLD.mcp_exposed='Y' THEN
      RAISE EXCEPTION 'An exposed tool requires control-plane authority' USING ERRCODE='42501';
    END IF;
  END IF;
  RETURN NEW;
END $cx89guard$;
REVOKE ALL ON FUNCTION public.cx89_guard_mcp_tool() FROM PUBLIC;
CREATE OR REPLACE TRIGGER CX415_TOOL_MCP_GUARD BEFORE INSERT OR UPDATE ON TOOL_REGISTRY
FOR EACH ROW EXECUTE FUNCTION public.cx89_guard_mcp_tool();
