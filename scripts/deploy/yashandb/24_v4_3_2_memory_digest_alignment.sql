-- v4.3.2 digest alignment for Memory adopted before the SHA-256 policy.
-- It is a separate journaled correction and can be rerun without changing
-- Family identity, Version identity, body, ownership, or lifecycle state.
UPDATE CX_MEMORY_VERSIONS
   SET CONTENT_DIGEST = RAWTOHEX(DBMS_CRYPTO.HASH(
       UTL_RAW.CAST_TO_RAW(DBMS_LOB.SUBSTR(NVL(BODY_TEXT, TO_CLOB('')), 32767, 1)), 4
   ))
 WHERE LEGACY_ENTITY_ID IS NOT NULL
   AND VERSION_NUMBER = 1;
