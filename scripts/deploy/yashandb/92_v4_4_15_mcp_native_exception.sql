-- YashanDB uses a native named exception; Oracle application-error numbers
-- are not portable. Owner maintenance and unexposed Agent writes remain valid.
DECLARE owner_name VARCHAR2(128);
BEGIN
  SELECT USER INTO owner_name FROM DUAL;
  EXECUTE IMMEDIATE 'CREATE OR REPLACE TRIGGER CX415_TOOL_MCP_GUARD
BEFORE INSERT OR UPDATE OR DELETE ON TOOL_REGISTRY FOR EACH ROW
DECLARE mcp_control_plane_required EXCEPTION;
BEGIN
  IF SYS_CONTEXT(''USERENV'',''SESSION_USER'')<>''' || REPLACE(owner_name,'''','''''') || ''' THEN
    IF (INSERTING OR UPDATING) AND :NEW.MCP_EXPOSED=''Y'' THEN
      RAISE mcp_control_plane_required;
    END IF;
    IF (UPDATING OR DELETING) AND :OLD.MCP_EXPOSED=''Y'' THEN
      RAISE mcp_control_plane_required;
    END IF;
  END IF;
END;';
END;
/
