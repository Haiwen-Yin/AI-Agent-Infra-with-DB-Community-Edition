-- v4.3.2 digest alignment for Memory adopted before the SHA-256 policy.
-- Kept separate from step 23 so installations with its recorded checksum can
-- receive this idempotent correction through the normal migration ledger.
UPDATE cx_memory_versions
   SET content_digest = encode(sha256(convert_to(coalesce(body_text, ''), 'UTF8')), 'hex')
 WHERE legacy_entity_id IS NOT NULL
   AND version_number = 1;
