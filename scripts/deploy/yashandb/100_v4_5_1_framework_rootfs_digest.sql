-- v4.5.1 compatibility repair for framework isolation evidence.
-- Migration 98 originally accepted the digest column at VARCHAR2(64). The
-- runtime records an algorithm-qualified value (for example sha256:<hex>),
-- so existing databases must widen the column before an isolated execution.

DECLARE
  n NUMBER;
BEGIN
  SELECT COUNT(*) INTO n
    FROM USER_TAB_COLUMNS
   WHERE TABLE_NAME = 'CX_FRAMEWORK_EXECUTIONS'
     AND COLUMN_NAME = 'ROOTFS_DIGEST'
     AND DATA_LENGTH < 128;
  IF n > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE CX_FRAMEWORK_EXECUTIONS MODIFY (ROOTFS_DIGEST VARCHAR2(128))';
  END IF;
END;
/
