-- v4.3.1 one account, one Human Principal, one organization person.

ALTER TABLE cx_principals
    ADD COLUMN IF NOT EXISTS organization_required char(1) NOT NULL DEFAULT 'Y';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_cx_principal_org_req'
    ) THEN
        ALTER TABLE cx_principals ADD CONSTRAINT ck_cx_principal_org_req
            CHECK (organization_required IN ('Y', 'N'));
    END IF;
END $$;

UPDATE cx_principals p SET organization_required = 'N'
 WHERE EXISTS (
       SELECT 1 FROM cx_human_identities i JOIN cx_user_roles r ON r.principal_id = i.principal_id
        WHERE i.principal_id = p.principal_id AND i.identity_type = 'LOCAL'
          AND i.subject_key = 'admin' AND i.status = 'ACTIVE'
          AND r.role_code = 'SYSTEM_ADMIN' AND r.status = 'ACTIVE' AND r.source = 'BOOTSTRAP_ADMIN'
 );

UPDATE cx_organization_members m
   SET status = 'ENDED', valid_until = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
 WHERE m.status = 'ACTIVE' AND EXISTS (
       SELECT 1 FROM cx_principals p
        WHERE p.principal_id = m.principal_id AND p.organization_required = 'N'
 );

UPDATE cx_organizations o SET responsible_principal_id = NULL, updated_at = CURRENT_TIMESTAMP
 WHERE EXISTS (
       SELECT 1 FROM cx_principals p
        WHERE p.principal_id = o.responsible_principal_id AND p.organization_required = 'N'
 );

CREATE OR REPLACE FUNCTION cx_enforce_org_member_account() RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'ACTIVE' AND NOT EXISTS (
        SELECT 1 FROM cx_principals p
         WHERE p.principal_id = NEW.principal_id AND p.principal_type = 'HUMAN'
           AND p.status = 'ACTIVE' AND p.organization_required = 'Y'
           AND EXISTS (SELECT 1 FROM cx_human_identities i
                        WHERE i.principal_id = p.principal_id AND i.status = 'ACTIVE')
    ) THEN
        RAISE EXCEPTION 'organization person requires one active platform account';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cx_org_member_account ON cx_organization_members;
CREATE TRIGGER trg_cx_org_member_account
BEFORE INSERT OR UPDATE OF principal_id, status ON cx_organization_members
FOR EACH ROW EXECUTE FUNCTION cx_enforce_org_member_account();
