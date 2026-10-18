-- v4.3.0 additive lifecycle, Bridge, notification, Barrier and profile fields.
-- Every field is nullable/defaulted so an interrupted upgrade can be retried.

ALTER TABLE cx_channels ADD COLUMN IF NOT EXISTS lifecycle_reason varchar(2000);
ALTER TABLE cx_channels ADD COLUMN IF NOT EXISTS deletion_after timestamp;
ALTER TABLE cx_channels ADD COLUMN IF NOT EXISTS quarantined_at timestamp;
ALTER TABLE cx_bridges ADD COLUMN IF NOT EXISTS approval_reason varchar(2000);
ALTER TABLE cx_bridges ADD COLUMN IF NOT EXISTS policy_version bigint NOT NULL DEFAULT 1;
ALTER TABLE cx_bridge_transfers ADD COLUMN IF NOT EXISTS idempotency_key varchar(256);
ALTER TABLE cx_bridge_transfers ADD COLUMN IF NOT EXISTS source_classification varchar(32);
ALTER TABLE cx_notifications ADD COLUMN IF NOT EXISTS notification_level varchar(32) NOT NULL DEFAULT 'INFO';
ALTER TABLE cx_notifications ADD COLUMN IF NOT EXISTS acknowledged_by varchar(128);
ALTER TABLE cx_notifications ADD COLUMN IF NOT EXISTS escalated_at timestamp;
ALTER TABLE cx_barriers ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0;
ALTER TABLE cx_barriers ADD COLUMN IF NOT EXISTS max_retries integer NOT NULL DEFAULT 3;
ALTER TABLE cx_barriers ADD COLUMN IF NOT EXISTS last_recovery_action varchar(32);
ALTER TABLE cx_barriers ADD COLUMN IF NOT EXISTS recovery_reason varchar(2000);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cx_bridge_transfer_idemp
    ON cx_bridge_transfers(bridge_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS cx_channel_threads (
    thread_id varchar(128) PRIMARY KEY,
    channel_id varchar(128) NOT NULL,
    parent_thread_id varchar(128),
    thread_type varchar(32) NOT NULL,
    classification varchar(32) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    policy_json text NOT NULL DEFAULT '{}',
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_channel_thread_parent
    ON cx_channel_threads(channel_id, parent_thread_id, status, updated_at);

-- The participant list is an authorization snapshot, not a mutable invitation
-- list.  Keep other policy fields available to the control plane while making
-- this one field immutable after the thread is created.
CREATE OR REPLACE FUNCTION public.cx_channel_thread_participant_snapshot_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_channel_thread_participant_snapshot_guard$
BEGIN
    IF (
        COALESCE(NULLIF(OLD.policy_json, ''), '{}')::jsonb
            -> 'participant_principal_ids'
    ) IS DISTINCT FROM (
        COALESCE(NULLIF(NEW.policy_json, ''), '{}')::jsonb
            -> 'participant_principal_ids'
    ) THEN
        RAISE EXCEPTION 'participant_principal_ids is immutable'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$cx_channel_thread_participant_snapshot_guard$;

DROP TRIGGER IF EXISTS cx_channel_thread_participant_snapshot_guard
    ON public.cx_channel_threads;
CREATE TRIGGER cx_channel_thread_participant_snapshot_guard
    BEFORE UPDATE OF policy_json ON public.cx_channel_threads
    FOR EACH ROW
    EXECUTE FUNCTION public.cx_channel_thread_participant_snapshot_guard();

CREATE TABLE IF NOT EXISTS cx_channel_thread_members (
    thread_member_id varchar(128) PRIMARY KEY,
    thread_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    member_role varchar(32) NOT NULL DEFAULT 'MEMBER',
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    valid_until timestamp,
    joined_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (thread_id, principal_id)
);
CREATE INDEX IF NOT EXISTS idx_cx_channel_thread_member
    ON cx_channel_thread_members(thread_id, principal_id, status, valid_until);

CREATE TABLE IF NOT EXISTS cx_runtime_profile_changes (
    change_id varchar(128) PRIMARY KEY,
    requested_by varchar(128) NOT NULL,
    current_profile varchar(64) NOT NULL,
    target_profile varchar(64) NOT NULL,
    impact_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'PREFLIGHT',
    reason varchar(2000) NOT NULL,
    activated_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);

-- These predicates are declared before the RLS policies that reference them.
CREATE OR REPLACE FUNCTION public.cx_channel_principal_member(p_channel_id varchar, p_principal_id varchar)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_channel_principal_member_prepolicy$
    SELECT EXISTS (
        SELECT 1 FROM public.cx_channel_members caller_member
        WHERE caller_member.channel_id = p_channel_id
          AND caller_member.principal_id = public.current_agent_identity()
          AND caller_member.status = 'ACTIVE'
          AND (caller_member.valid_until IS NULL OR caller_member.valid_until > current_timestamp)
    ) AND EXISTS (
        SELECT 1 FROM public.cx_channel_members target_member
        JOIN public.cx_principals target_principal ON target_principal.principal_id = target_member.principal_id
        WHERE target_member.channel_id = p_channel_id
          AND target_member.principal_id = p_principal_id
          AND target_member.status = 'ACTIVE'
          AND (target_member.valid_until IS NULL OR target_member.valid_until > current_timestamp)
          AND target_principal.status = 'ACTIVE'
    )
$cx_channel_principal_member_prepolicy$;

CREATE OR REPLACE FUNCTION public.cx_channel_principal_type(p_channel_id varchar, p_principal_id varchar)
RETURNS varchar LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_channel_principal_type_prepolicy$
    SELECT target_principal.principal_type
    FROM public.cx_channel_members caller_member
    JOIN public.cx_channel_members target_member ON target_member.channel_id = caller_member.channel_id
    JOIN public.cx_principals target_principal ON target_principal.principal_id = target_member.principal_id
    WHERE caller_member.channel_id = p_channel_id
      AND caller_member.principal_id = public.current_agent_identity()
      AND caller_member.status = 'ACTIVE'
      AND (caller_member.valid_until IS NULL OR caller_member.valid_until > current_timestamp)
      AND target_member.principal_id = p_principal_id
      AND target_member.status = 'ACTIVE'
      AND (target_member.valid_until IS NULL OR target_member.valid_until > current_timestamp)
      AND target_principal.status = 'ACTIVE'
    FETCH FIRST 1 ROW ONLY
$cx_channel_principal_type_prepolicy$;

CREATE OR REPLACE FUNCTION public.cx_channel_thread_member(p_thread_id varchar, p_principal_id varchar)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_channel_thread_member_prepolicy$
    SELECT p_principal_id = public.current_agent_identity()
       AND EXISTS (
           SELECT 1 FROM public.cx_channel_thread_members tm
           JOIN public.cx_channel_threads t ON t.thread_id = tm.thread_id
           WHERE tm.thread_id = p_thread_id
             AND tm.principal_id = p_principal_id
             AND tm.status = 'ACTIVE'
             AND (tm.valid_until IS NULL OR tm.valid_until > current_timestamp)
             AND t.status = 'ACTIVE'
             AND public.cx_agent_channel_member(t.channel_id, public.current_agent_identity())
       )
$cx_channel_thread_member_prepolicy$;

CREATE OR REPLACE FUNCTION public.cx_channel_thread_participant(p_thread_id varchar, p_principal_id varchar)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_channel_thread_participant_prepolicy$
    SELECT public.current_agent_identity() IS NOT NULL
       AND public.current_agent_identity() <> ''
       AND EXISTS (
           SELECT 1 FROM public.cx_channel_threads t
           WHERE t.thread_id = p_thread_id
             AND t.created_by = public.current_agent_identity()
             AND t.status = 'ACTIVE'
             AND t.thread_type IN ('PRIVATE', 'DIRECT')
             AND public.cx_channel_principal_member(t.channel_id, p_principal_id)
             AND jsonb_typeof(
                     COALESCE(NULLIF(t.policy_json, ''), '{}')::jsonb
                         -> 'participant_principal_ids'
                 ) = 'array'
             AND (
                 COALESCE(NULLIF(t.policy_json, ''), '{}')::jsonb
                     -> 'participant_principal_ids'
             ) ? public.current_agent_identity()
             AND (
                 COALESCE(NULLIF(t.policy_json, ''), '{}')::jsonb
                     -> 'participant_principal_ids'
             ) ? p_principal_id
       )
$cx_channel_thread_participant_prepolicy$;

-- Threads are a navigation and execution-context boundary, never an authority
-- boundary. Agents may see and create only threads under a Channel they join.
ALTER TABLE cx_channel_threads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_channel_threads_member ON cx_channel_threads;
CREATE POLICY cx_channel_threads_member ON cx_channel_threads FOR SELECT
    USING (public.cx_agent_channel_member(channel_id, public.current_agent_identity()));
DROP POLICY IF EXISTS cx_channel_threads_agent_insert ON cx_channel_threads;
CREATE POLICY cx_channel_threads_agent_insert ON cx_channel_threads FOR INSERT
    WITH CHECK (created_by = public.current_agent_identity()
        AND public.cx_agent_channel_member(channel_id, public.current_agent_identity()));

ALTER TABLE cx_channel_thread_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_channel_thread_members_member ON cx_channel_thread_members;
CREATE POLICY cx_channel_thread_members_member ON cx_channel_thread_members FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM cx_channel_threads t
        WHERE t.thread_id = cx_channel_thread_members.thread_id
          AND public.cx_agent_channel_member(t.channel_id, public.current_agent_identity())
          AND (t.thread_type NOT IN ('PRIVATE', 'DIRECT')
               OR public.cx_channel_thread_member(cx_channel_thread_members.thread_id, public.current_agent_identity()))
    ));
DROP POLICY IF EXISTS cx_channel_thread_members_agent_insert ON cx_channel_thread_members;
CREATE POLICY cx_channel_thread_members_agent_insert ON cx_channel_thread_members FOR INSERT
    WITH CHECK (public.cx_channel_thread_participant(thread_id, principal_id));

-- Runtime profile changes are human control-plane objects. RLS is enabled
-- without an Agent policy so a NOBYPASSRLS role fails closed.
ALTER TABLE cx_runtime_profile_changes ENABLE ROW LEVEL SECURITY;

DO $cx_agent_thread_grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        EXECUTE 'GRANT SELECT, INSERT ON TABLE public.cx_channel_threads, public.cx_channel_thread_members TO ai_agent_runtime';
        EXECUTE 'REVOKE UPDATE, DELETE ON TABLE public.cx_channel_threads, public.cx_channel_thread_members FROM ai_agent_runtime';
    END IF;
END
$cx_agent_thread_grants$;

-- Repeat the destructive privilege boundary outside the grant block.  This
-- repairs databases created by an earlier v4.3 draft that granted the full
-- table privilege set before the governance step was recorded as applied.
DO $cx_agent_thread_revoke$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON TABLE public.cx_channel_threads, public.cx_channel_thread_members FROM ai_agent_runtime';
    END IF;
END
$cx_agent_thread_revoke$;

REVOKE ALL ON TABLE public.cx_channel_threads, public.cx_channel_thread_members FROM PUBLIC;

-- Agent Channel messages use this bounded fan-out function instead of direct
-- delivery inserts.  It validates the authenticated sender and commits only
-- to active, leased instances of current Channel members.
CREATE OR REPLACE FUNCTION public.cx_enqueue_channel_deliveries(
    p_message_id varchar, p_channel_id varchar, p_body text,
    p_message_type varchar, p_references text, p_classification varchar
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_enqueue_channel_deliveries$
DECLARE
    actor_id text := public.current_agent_identity();
    inserted_count integer;
BEGIN
    IF actor_id IS NULL OR actor_id = '' THEN
        RAISE EXCEPTION 'authenticated Agent identity is required' USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.cx_channel_messages m
        JOIN public.cx_channel_members cm
          ON cm.channel_id = m.channel_id AND cm.principal_id = m.principal_id
        WHERE m.message_id = p_message_id
          AND m.channel_id = p_channel_id
          AND m.principal_id = actor_id
          AND cm.status = 'ACTIVE'
          AND (cm.valid_until IS NULL OR cm.valid_until > current_timestamp)
    ) THEN
        RAISE EXCEPTION 'message sender or Channel membership is invalid' USING ERRCODE = '42501';
    END IF;
    INSERT INTO public.cx_agent_deliveries(
        delivery_id, event_type, channel_id, message_id, agent_id, instance_id,
        payload_json, idempotency_key, status
    )
    SELECT 'DLV_' || md5(random()::text || clock_timestamp()::text || p_message_id || i.instance_id),
           'CHANNEL_MESSAGE', p_channel_id, p_message_id, i.agent_id, i.instance_id,
           jsonb_build_object(
               'message_id', p_message_id, 'channel_id', p_channel_id,
               'body', p_body, 'message_type', p_message_type,
               'references', COALESCE(NULLIF(p_references, '')::jsonb, '{}'::jsonb),
               'classification', p_classification
           )::text,
           'channel:' || p_message_id || ':' || i.instance_id,
           'PENDING'
    FROM public.cx_agent_instances i
    JOIN public.cx_principals p ON p.principal_id = i.agent_id
    JOIN public.cx_channel_members cm
      ON cm.channel_id = i.channel_id AND cm.principal_id = i.agent_id
    WHERE i.channel_id = p_channel_id
      AND i.status = 'ACTIVE'
      AND i.lease_expires_at > current_timestamp
      AND cm.status = 'ACTIVE'
      AND (cm.valid_until IS NULL OR cm.valid_until > current_timestamp)
      AND p.status = 'ACTIVE'
    ON CONFLICT (agent_id, idempotency_key) DO NOTHING;
    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RETURN inserted_count;
END;
$cx_enqueue_channel_deliveries$;

REVOKE ALL ON FUNCTION public.cx_channel_principal_member(varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cx_channel_principal_type(varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cx_channel_thread_member(varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cx_channel_thread_participant(varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cx_channel_thread_participant_snapshot_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cx_enqueue_channel_deliveries(varchar, varchar, text, varchar, text, varchar) FROM PUBLIC;

DO $cx_v43_runtime_grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.cx_channel_principal_member(varchar, varchar) TO ai_agent_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.cx_channel_principal_type(varchar, varchar) TO ai_agent_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.cx_channel_thread_member(varchar, varchar) TO ai_agent_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.cx_channel_thread_participant(varchar, varchar) TO ai_agent_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.cx_enqueue_channel_deliveries(varchar, varchar, text, varchar, text, varchar) TO ai_agent_runtime';
    END IF;
END
$cx_v43_runtime_grants$;

-- Keep role templates aligned with the server-side fallback matrix.  The
-- conditional update makes retries idempotent and avoids version churn.
WITH desired(role_code, display_name, permissions_json, data_scopes_json) AS (
    VALUES
      ('END_USER', 'End User', '["profile.read","profile.update","agents.enroll","agents.read","channels.read","channels.write","tasks.read","workspaces.read","knowledge.read","memory.read","skills.read","specs.read","branches.read","collab.read","loops.read","graphs.read","notifications.read"]', '["OWNED","ASSIGNED"]'),
      ('SYSTEM_ADMIN', 'System Administrator', '["*"]', '["ALL"]'),
      ('SECURITY_ADMIN', 'Security Administrator', '["security.*","sessions.revoke","domains.manage","profile.update","users.identity.link","users.security.manage","users.sessions.read","users.delegations.read","users.delegations.manage","agents.claim","channels.bridge","channels.lifecycle","channels.delete","channels.manage_members","channels.quarantine","memory.review","agents.transfer","agents.offboard","barriers.recover","notifications.manage","barriers.create","channels.actions.decide"]', '["SECURITY_DOMAIN"]'),
      ('AGENT_MANAGER', 'Agent Manager', '["agents.read","agents.enroll","agents.manage","agents.operate","agents.transfer","agents.offboard","channels.read","channels.create","channels.manage_members","channels.lifecycle","barriers.create","channels.actions.decide","users.read","notifications.manage","profile.update"]', '["ORG_SUBTREE"]'),
      ('AUDITOR', 'Auditor', '["audit.read","audit.export","users.read","profile.update"]', '["SECURITY_DOMAIN"]'),
      ('APPROVER', 'Approver', '["approvals.read","approvals.decide","channels.actions.decide","barriers.release","barriers.recover","memory.review","profile.update"]', '["ASSIGNED"]'),
      ('OPERATOR', 'Operator', '["agents.read","agents.operate","channels.write","barriers.arrive","profile.update"]', '["ASSIGNED"]'),
      ('DEVELOPER', 'Developer', '["skills.read","tools.read","graphs.read","barriers.create","profile.update"]', '["OWNED"]'),
      ('USER_ADMIN', 'User Administrator', '["users.read","users.read.all","users.approve","users.roles.manage","users.permissions.manage","users.identity.link","users.security.manage","users.sessions.read","users.delegations.read","users.delegations.manage"]', '["ORG_SUBTREE"]'),
      ('ROLE_ADMIN', 'Role Administrator', '["users.read","users.roles.manage","users.permissions.manage","users.delegations.read","users.delegations.manage"]', '["ORG_SUBTREE"]'),
      ('AGENT', 'Agent', '["channels.read","channels.write","barriers.read","barriers.arrive","actions.propose"]', '["ASSIGNED"]')
)
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
SELECT role_code, display_name, permissions_json, data_scopes_json FROM desired
ON CONFLICT (role_code) DO UPDATE
SET display_name = EXCLUDED.display_name,
    permissions_json = EXCLUDED.permissions_json,
    data_scopes_json = EXCLUDED.data_scopes_json,
    version = cx_role_templates.version + 1,
    updated_at = current_timestamp
WHERE cx_role_templates.display_name IS DISTINCT FROM EXCLUDED.display_name
   OR cx_role_templates.permissions_json IS DISTINCT FROM EXCLUDED.permissions_json
   OR cx_role_templates.data_scopes_json IS DISTINCT FROM EXCLUDED.data_scopes_json;
