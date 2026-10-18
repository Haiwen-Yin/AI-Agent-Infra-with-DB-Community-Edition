-- v4.4.10 additive repair: use the established runtime identity and preserve migration 55 checksum.
INSERT INTO cx_platform_capabilities(capability_key,mandatory,enabled) VALUES ('wallboard','N','Y') ON CONFLICT (capability_key) DO NOTHING;
ALTER TABLE cx_model_routing_policies ADD COLUMN IF NOT EXISTS gateway_url varchar(512);
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_route_scope_uq ON cx_model_routing_policies
 (COALESCE(agent_id,'#'),COALESCE(profile_id,'#'));
DROP POLICY IF EXISTS cx_model_usage_runtime ON cx_model_usage;
CREATE POLICY cx_model_usage_runtime ON cx_model_usage
 USING (public.current_agent_identity() IS NULL OR actor_principal_id=public.current_agent_identity() OR agent_id=public.current_agent_identity())
 WITH CHECK (public.current_agent_identity() IS NULL OR actor_principal_id=public.current_agent_identity() OR agent_id=public.current_agent_identity());
DROP POLICY IF EXISTS cx_model_requests_runtime ON cx_model_requests;
CREATE POLICY cx_model_requests_runtime ON cx_model_requests
 USING (public.current_agent_identity() IS NULL OR actor_principal_id=public.current_agent_identity() OR agent_id=public.current_agent_identity())
 WITH CHECK (public.current_agent_identity() IS NULL OR actor_principal_id=public.current_agent_identity() OR agent_id=public.current_agent_identity());
DROP POLICY IF EXISTS cx_model_credentials_owner ON cx_model_gateway_credentials;
CREATE POLICY cx_model_credentials_owner ON cx_model_gateway_credentials
 USING (public.current_agent_identity() IS NULL) WITH CHECK (public.current_agent_identity() IS NULL);
DROP POLICY IF EXISTS cx_model_routing_runtime ON cx_model_routing_policies;
CREATE POLICY cx_model_routing_runtime ON cx_model_routing_policies
 USING (public.current_agent_identity() IS NULL) WITH CHECK (public.current_agent_identity() IS NULL);
UPDATE cx_role_templates SET permissions_json='["audit.read","audit.export","users.read","profile.update","organizations.read","organizations.history.read","organizations.export","wallboard.read","model_usage.read"]'
WHERE role_code='AUDITOR';
