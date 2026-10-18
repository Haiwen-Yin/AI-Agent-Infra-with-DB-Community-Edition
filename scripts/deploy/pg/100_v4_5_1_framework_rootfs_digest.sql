-- v4.5.1 compatibility repair for framework isolation evidence.
-- Migration 98 originally accepted the digest column at VARCHAR(64). The
-- runtime records an algorithm-qualified value (for example sha256:<hex>),
-- so existing databases must widen the column before an isolated execution.

-- PostgreSQL records trigger column dependencies and refuses to alter a
-- referenced column while the immutable extension trigger exists.  Remove
-- only that dependent trigger inside this migration, widen the column, then
-- restore the exact historical guard before the transaction commits.
DROP TRIGGER IF EXISTS CX86_61CC3DF1F0728A5A ON CX_FRAMEWORK_EXECUTIONS;

ALTER TABLE IF EXISTS CX_FRAMEWORK_EXECUTIONS
  ALTER COLUMN ROOTFS_DIGEST TYPE VARCHAR(128);

CREATE OR REPLACE TRIGGER CX86_61CC3DF1F0728A5A
BEFORE DELETE OR UPDATE OF EXECUTION_ID,ACTOR_ID,SECURITY_DOMAIN_ID,FRAMEWORK_KEY,FRAMEWORK_VERSION,ADAPTER_DIGEST,ROOTFS_DIGEST,INPUT_DIGEST,CREATED_AT
ON CX_FRAMEWORK_EXECUTIONS FOR EACH STATEMENT
EXECUTE FUNCTION cx98_reject_extension_mutation();

REVOKE ALL ON CX_FRAMEWORK_EXECUTIONS FROM PUBLIC, ai_agent_runtime;
