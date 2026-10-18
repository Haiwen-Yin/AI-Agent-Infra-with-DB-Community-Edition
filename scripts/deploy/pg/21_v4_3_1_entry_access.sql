-- v4.3.1 Human entry-access policy and protected bootstrap administrator.

ALTER TABLE cx_principals ADD COLUMN IF NOT EXISTS portal_access char(1) NOT NULL DEFAULT 'Y';
ALTER TABLE cx_principals ADD COLUMN IF NOT EXISTS app_access char(1) NOT NULL DEFAULT 'Y';

UPDATE cx_principals p
   SET portal_access = 'Y', app_access = 'Y'
 WHERE EXISTS (
       SELECT 1 FROM cx_human_identities i
        WHERE i.principal_id = p.principal_id
          AND i.identity_type = 'LOCAL'
          AND i.subject_key = 'admin'
 );

UPDATE cx_user_roles r
   SET source = 'BOOTSTRAP_ADMIN'
 WHERE r.role_code = 'SYSTEM_ADMIN'
   AND r.status = 'ACTIVE'
   AND EXISTS (
       SELECT 1 FROM cx_human_identities i
        WHERE i.principal_id = r.principal_id
          AND i.identity_type = 'LOCAL'
          AND i.subject_key = 'admin'
   );
