-- v4.4.9: keep local identity explicit across all adapters.
ALTER TABLE IF EXISTS public.system_users DROP CONSTRAINT IF EXISTS ck_su_auth_source;
ALTER TABLE IF EXISTS public.system_users ADD CONSTRAINT ck_su_auth_source CHECK (auth_source IN ('LOCAL','LDAP'));
