-- v4.4.4 additive separation of Admin Agent and Agent Pool shared storage.
ALTER TABLE cx_shared_storage_profiles
  ADD COLUMN IF NOT EXISTS storage_purpose varchar(32) NOT NULL DEFAULT 'ADMIN_RUNTIME';
