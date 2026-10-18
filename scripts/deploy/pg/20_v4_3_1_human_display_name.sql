-- v4.3.1 Human display-name extension.
-- Authentication usernames and immutable Principal IDs remain separate.

ALTER TABLE cx_principals ADD COLUMN IF NOT EXISTS display_name varchar(256);
ALTER TABLE cx_registration_requests ADD COLUMN IF NOT EXISTS display_name varchar(256);
