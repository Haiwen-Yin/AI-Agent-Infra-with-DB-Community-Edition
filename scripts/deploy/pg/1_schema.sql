--
-- PostgreSQL database dump
--

-- ============================================================
-- Schema owner configuration (adjust if not using default pgsql)
-- ============================================================
\set schema_owner 'pgsql'

\restrict 76Wp7adbaBBB9zy9rLASF86x1AU573WukoerTf6PVwr4lSpRYkaX6XhZf6NLLFa

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP POLICY IF EXISTS wt_agent_isolation ON public.workspace_tasks;
DROP POLICY IF EXISTS ws_agent_isolation ON public.workspaces;
DROP POLICY IF EXISTS wca_aiadmin ON public.workspace_context_audit;
DROP POLICY IF EXISTS wc_agent_isolation ON public.workspace_context;
DROP POLICY IF EXISTS spl_agent_isolation ON public.spec_plan_links;
DROP POLICY IF EXISTS spec_meta_end_user ON public.spec_meta;
DROP POLICY IF EXISTS spec_meta_aiadmin ON public.spec_meta;
DROP POLICY IF EXISTS skm_agent_isolation ON public.skill_meta;
DROP POLICY IF EXISTS sat_end_user ON public.skill_access_token;
DROP POLICY IF EXISTS sat_aiadmin ON public.skill_access_token;
DROP POLICY IF EXISTS ldap_aiadmin ON public.ldap_config;
DROP POLICY IF EXISTS knowledge_meta_end_user ON public.knowledge_meta;
DROP POLICY IF EXISTS knowledge_meta_aiadmin ON public.knowledge_meta;
DROP POLICY IF EXISTS harness_meta_end_user ON public.harness_meta;
DROP POLICY IF EXISTS harness_meta_aiadmin ON public.harness_meta;
DROP POLICY IF EXISTS et_agent_isolation ON public.entity_tags;
DROP POLICY IF EXISTS entities_agent_isolation ON public.entities;
DROP POLICY IF EXISTS edges_agent_isolation ON public.entity_edges;
DROP POLICY IF EXISTS eal_agent_isolation ON public.entity_access_log;
DROP POLICY IF EXISTS eaa_end_user ON public.entity_access_audit;
DROP POLICY IF EXISTS eaa_aiadmin ON public.entity_access_audit;
DROP POLICY IF EXISTS col_agent_isolation ON public.agent_collaboration;
DROP POLICY IF EXISTS cl_aiadmin ON public.compliance_log;
DROP POLICY IF EXISTS cb_agent_isolation ON public.context_branches;
DROP POLICY IF EXISTS bml_agent_isolation ON public.branch_merge_log;
DROP POLICY IF EXISTS as_agent_isolation ON public.agent_session;
DROP POLICY IF EXISTS apl_agent_isolation ON public.agent_permission_log;
DROP POLICY IF EXISTS ac_agent_isolation ON public.agent_credentials;
ALTER TABLE IF EXISTS ONLY public.workspace_tasks DROP CONSTRAINT IF EXISTS fk_wt_workspace;
ALTER TABLE IF EXISTS ONLY public.workspace_context DROP CONSTRAINT IF EXISTS fk_wc_workspace;
ALTER TABLE IF EXISTS ONLY public.workspace_context DROP CONSTRAINT IF EXISTS fk_wc_parent;
ALTER TABLE IF EXISTS ONLY public.workspace_context DROP CONSTRAINT IF EXISTS fk_wc_branch;
ALTER TABLE IF EXISTS ONLY public.workspace_context DROP CONSTRAINT IF EXISTS fk_wc_agent;
ALTER TABLE IF EXISTS public.task_plans DROP CONSTRAINT IF EXISTS fk_tp_branch;
ALTER TABLE IF EXISTS public.task_plans DROP CONSTRAINT IF EXISTS fk_tp_agent;
ALTER TABLE IF EXISTS ONLY public.task_steps DROP CONSTRAINT IF EXISTS fk_step_plan;
ALTER TABLE IF EXISTS public.agent_session DROP CONSTRAINT IF EXISTS fk_session_workspace;
ALTER TABLE IF EXISTS public.agent_session DROP CONSTRAINT IF EXISTS fk_session_branch;
ALTER TABLE IF EXISTS public.agent_session DROP CONSTRAINT IF EXISTS fk_session_agent;
ALTER TABLE IF EXISTS ONLY public.knowledge_meta DROP CONSTRAINT IF EXISTS fk_km_entity;
ALTER TABLE IF EXISTS ONLY public.entity_tags DROP CONSTRAINT IF EXISTS fk_et_tag;
ALTER TABLE IF EXISTS ONLY public.entity_tags DROP CONSTRAINT IF EXISTS fk_et_entity;
ALTER TABLE IF EXISTS public.entities DROP CONSTRAINT IF EXISTS fk_entities_workspace;
ALTER TABLE IF EXISTS ONLY public.entity_edges DROP CONSTRAINT IF EXISTS fk_edge_source;
ALTER TABLE IF EXISTS public.entity_access_log DROP CONSTRAINT IF EXISTS fk_eal_agent;
ALTER TABLE IF EXISTS ONLY public.agent_collaboration DROP CONSTRAINT IF EXISTS fk_col_target;
ALTER TABLE IF EXISTS ONLY public.agent_collaboration DROP CONSTRAINT IF EXISTS fk_col_source;
ALTER TABLE IF EXISTS ONLY public.collab_group_members DROP CONSTRAINT IF EXISTS fk_cgm_workspace;
ALTER TABLE IF EXISTS ONLY public.collab_group_members DROP CONSTRAINT IF EXISTS fk_cgm_group;
ALTER TABLE IF EXISTS ONLY public.collab_group_members DROP CONSTRAINT IF EXISTS fk_cgm_agent;
ALTER TABLE IF EXISTS ONLY public.collab_groups DROP CONSTRAINT IF EXISTS fk_cg_workspace;
ALTER TABLE IF EXISTS ONLY public.collab_groups DROP CONSTRAINT IF EXISTS fk_cg_coordinator;
ALTER TABLE IF EXISTS ONLY public.collab_groups DROP CONSTRAINT IF EXISTS fk_cg_branch;
ALTER TABLE IF EXISTS ONLY public.context_branches DROP CONSTRAINT IF EXISTS fk_cb_workspace;
ALTER TABLE IF EXISTS ONLY public.context_branches DROP CONSTRAINT IF EXISTS fk_cb_parent;
ALTER TABLE IF EXISTS ONLY public.context_branches DROP CONSTRAINT IF EXISTS fk_cb_agent;
ALTER TABLE IF EXISTS ONLY public.branch_merge_log DROP CONSTRAINT IF EXISTS fk_bml_tgt;
ALTER TABLE IF EXISTS ONLY public.branch_merge_log DROP CONSTRAINT IF EXISTS fk_bml_src;
ALTER TABLE IF EXISTS ONLY public.agent_registry DROP CONSTRAINT IF EXISTS fk_ar_created_by;
ALTER TABLE IF EXISTS ONLY public.agent_credentials DROP CONSTRAINT IF EXISTS fk_ac_agent;
DROP TRIGGER IF EXISTS trg_workspaces_updated_at ON public.workspaces;
DROP TRIGGER IF EXISTS trg_task_plans_updated_at ON public.task_plans;
DROP TRIGGER IF EXISTS trg_system_users_updated_at ON public.system_users;
DROP TRIGGER IF EXISTS trg_system_config_updated_at ON public.system_config;
DROP TRIGGER IF EXISTS trg_skill_meta_updated_at ON public.skill_meta;
DROP TRIGGER IF EXISTS trg_entities_search_vector ON public.entities;
DROP TRIGGER IF EXISTS trg_collab_groups_updated_at ON public.collab_groups;
DROP TRIGGER IF EXISTS trg_agent_registry_updated_at ON public.agent_registry;
DROP INDEX IF EXISTS public.idx_ws_status;
DROP INDEX IF EXISTS public.idx_ws_owner;
DROP INDEX IF EXISTS public.idx_ws_alias;
DROP INDEX IF EXISTS public.idx_wca_workspace;
DROP INDEX IF EXISTS public.idx_wca_context;
DROP INDEX IF EXISTS public.idx_wc_workspace;
DROP INDEX IF EXISTS public.idx_wc_visibility;
DROP INDEX IF EXISTS public.idx_wc_type;
DROP INDEX IF EXISTS public.idx_wc_branch;
DROP INDEX IF EXISTS public.idx_wc_agent;
DROP INDEX IF EXISTS public.idx_ttc_step;
DROP INDEX IF EXISTS public.idx_ttc_plan;
DROP INDEX IF EXISTS public.idx_ts_plan;
DROP INDEX IF EXISTS public.idx_tp_branch;
DROP INDEX IF EXISTS public.idx_tp_agent;
DROP INDEX IF EXISTS public.idx_td_target;
DROP INDEX IF EXISTS public.idx_td_source;
DROP INDEX IF EXISTS public.idx_tcs_plan;
DROP INDEX IF EXISTS public.idx_spl_spec;
DROP INDEX IF EXISTS public.idx_spl_plan;
DROP INDEX IF EXISTS public.idx_sm_spec_status;
DROP INDEX IF EXISTS public.idx_sm_scope;
DROP INDEX IF EXISTS public.idx_sm_complexity;
DROP INDEX IF EXISTS public.idx_sm_branch;
DROP INDEX IF EXISTS public.idx_skm_type;
DROP INDEX IF EXISTS public.idx_skm_status;
DROP INDEX IF EXISTS public.idx_skm_name;
DROP INDEX IF EXISTS public.idx_sat_skill;
DROP INDEX IF EXISTS public.idx_sat_hash;
DROP INDEX IF EXISTS public.idx_km_topic;
DROP INDEX IF EXISTS public.idx_km_next_review;
DROP INDEX IF EXISTS public.idx_km_domain;
DROP INDEX IF EXISTS public.idx_km_difficulty;
DROP INDEX IF EXISTS public.idx_hm_exec_mode;
DROP INDEX IF EXISTS public.idx_et_tag;
DROP INDEX IF EXISTS public.idx_ee_embedding;
DROP INDEX IF EXISTS public.idx_edges_type;
DROP INDEX IF EXISTS public.idx_edges_target_type;
DROP INDEX IF EXISTS public.idx_edges_target;
DROP INDEX IF EXISTS public.idx_eaa_entity;
DROP INDEX IF EXISTS public.idx_eaa_accessor;
DROP INDEX IF EXISTS public.idx_col_target;
DROP INDEX IF EXISTS public.idx_col_source;
DROP INDEX IF EXISTS public.idx_cl_event;
DROP INDEX IF EXISTS public.idx_cl_created;
DROP INDEX IF EXISTS public.idx_cgm_group;
DROP INDEX IF EXISTS public.idx_cgm_agent;
DROP INDEX IF EXISTS public.idx_cg_workspace;
DROP INDEX IF EXISTS public.idx_cg_type;
DROP INDEX IF EXISTS public.idx_cg_status;
DROP INDEX IF EXISTS public.idx_cb_workspace;
DROP INDEX IF EXISTS public.idx_cb_type;
DROP INDEX IF EXISTS public.idx_cb_status;
DROP INDEX IF EXISTS public.idx_cb_parent;
DROP INDEX IF EXISTS public.idx_cb_agent;
DROP INDEX IF EXISTS public.idx_bml_tgt;
DROP INDEX IF EXISTS public.idx_bml_src;
DROP INDEX IF EXISTS public.idx_ar_user;
DROP INDEX IF EXISTS public.idx_ar_type;
DROP INDEX IF EXISTS public.idx_ar_status;
DROP INDEX IF EXISTS public.idx_ar_role;
DROP INDEX IF EXISTS public.idx_ar_created_by;
DROP INDEX IF EXISTS public.idx_apl_agent;
DROP INDEX IF EXISTS public.idx_ac_user;
DROP INDEX IF EXISTS public.idx_ac_agent;
DROP INDEX IF EXISTS public.idx_ac_active;
DROP INDEX IF EXISTS public.idx_eal_entity;
DROP INDEX IF EXISTS public.idx_eal_time;
DROP INDEX IF EXISTS public.idx_entities_workspace;
DROP INDEX IF EXISTS public.idx_entities_visibility;
DROP INDEX IF EXISTS public.idx_entities_status;
DROP INDEX IF EXISTS public.idx_entities_search;
DROP INDEX IF EXISTS public.idx_entities_owned_by;
DROP INDEX IF EXISTS public.idx_entities_category;
DROP INDEX IF EXISTS public.idx_as_workspace;
DROP INDEX IF EXISTS public.idx_as_predecessor;
DROP INDEX IF EXISTS public.idx_as_owner;
DROP INDEX IF EXISTS public.idx_as_agent;
ALTER TABLE IF EXISTS ONLY public.workspaces DROP CONSTRAINT IF EXISTS workspaces_pkey;
ALTER TABLE IF EXISTS ONLY public.workspace_context DROP CONSTRAINT IF EXISTS workspace_context_pkey;
ALTER TABLE IF EXISTS ONLY public.workspace_context_audit DROP CONSTRAINT IF EXISTS workspace_context_audit_pkey;
ALTER TABLE IF EXISTS ONLY public.tags DROP CONSTRAINT IF EXISTS uk_tags_name;
ALTER TABLE IF EXISTS ONLY public.system_users DROP CONSTRAINT IF EXISTS uk_su_username;
ALTER TABLE IF EXISTS ONLY public.spec_plan_links DROP CONSTRAINT IF EXISTS uk_spl_link;
ALTER TABLE IF EXISTS ONLY public.collab_group_members DROP CONSTRAINT IF EXISTS uk_cgm_membership;
ALTER TABLE IF EXISTS ONLY public.task_tool_calls DROP CONSTRAINT IF EXISTS task_tool_calls_pkey;
ALTER TABLE IF EXISTS ONLY public.task_steps DROP CONSTRAINT IF EXISTS task_steps_pkey;
ALTER TABLE IF EXISTS ONLY public.task_plans_paused DROP CONSTRAINT IF EXISTS task_plans_paused_pkey;
ALTER TABLE IF EXISTS ONLY public.task_plans_default DROP CONSTRAINT IF EXISTS task_plans_default_pkey;
ALTER TABLE IF EXISTS ONLY public.task_plans_completed DROP CONSTRAINT IF EXISTS task_plans_completed_pkey;
ALTER TABLE IF EXISTS ONLY public.task_plans_cancelled DROP CONSTRAINT IF EXISTS task_plans_cancelled_pkey;
ALTER TABLE IF EXISTS ONLY public.task_plans_active DROP CONSTRAINT IF EXISTS task_plans_active_pkey;
ALTER TABLE IF EXISTS ONLY public.task_dependencies DROP CONSTRAINT IF EXISTS task_dependencies_pkey;
ALTER TABLE IF EXISTS ONLY public.task_context_snapshots DROP CONSTRAINT IF EXISTS task_context_snapshots_pkey;
ALTER TABLE IF EXISTS ONLY public.tags DROP CONSTRAINT IF EXISTS tags_pkey;
ALTER TABLE IF EXISTS ONLY public.system_users DROP CONSTRAINT IF EXISTS system_users_pkey;
ALTER TABLE IF EXISTS ONLY public.system_config DROP CONSTRAINT IF EXISTS system_config_pkey;
ALTER TABLE IF EXISTS ONLY public.spec_plan_links DROP CONSTRAINT IF EXISTS spec_plan_links_pkey;
ALTER TABLE IF EXISTS ONLY public.skill_meta DROP CONSTRAINT IF EXISTS skill_meta_pkey;
ALTER TABLE IF EXISTS ONLY public.skill_access_token DROP CONSTRAINT IF EXISTS skill_access_token_token_hash_key;
ALTER TABLE IF EXISTS ONLY public.skill_access_token DROP CONSTRAINT IF EXISTS skill_access_token_pkey;
ALTER TABLE IF EXISTS ONLY public.workspace_tasks DROP CONSTRAINT IF EXISTS pk_workspace_tasks;
ALTER TABLE IF EXISTS ONLY public.task_plans DROP CONSTRAINT IF EXISTS pk_task_plans;
ALTER TABLE IF EXISTS ONLY public.spec_meta DROP CONSTRAINT IF EXISTS pk_spec_meta;
ALTER TABLE IF EXISTS ONLY public.knowledge_meta DROP CONSTRAINT IF EXISTS pk_knowledge_meta;
ALTER TABLE IF EXISTS ONLY public.harness_meta DROP CONSTRAINT IF EXISTS pk_harness_meta;
ALTER TABLE IF EXISTS ONLY public.entity_tags DROP CONSTRAINT IF EXISTS pk_entity_tags;
ALTER TABLE IF EXISTS ONLY public.entity_embeddings DROP CONSTRAINT IF EXISTS pk_entity_embeddings;
ALTER TABLE IF EXISTS ONLY public.ldap_config DROP CONSTRAINT IF EXISTS ldap_config_pkey;
ALTER TABLE IF EXISTS ONLY public.ldap_config DROP CONSTRAINT IF EXISTS ldap_config_config_name_key;
ALTER TABLE IF EXISTS ONLY public.entity_edges DROP CONSTRAINT IF EXISTS entity_edges_pkey;
ALTER TABLE IF EXISTS ONLY public.entity_access_audit DROP CONSTRAINT IF EXISTS entity_access_audit_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_task_output DROP CONSTRAINT IF EXISTS entities_task_output_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_spec DROP CONSTRAINT IF EXISTS entities_spec_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_skill DROP CONSTRAINT IF EXISTS entities_skill_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_other DROP CONSTRAINT IF EXISTS entities_other_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_memory DROP CONSTRAINT IF EXISTS entities_memory_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_knowledge DROP CONSTRAINT IF EXISTS entities_knowledge_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_harness_template DROP CONSTRAINT IF EXISTS entities_harness_template_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_experience DROP CONSTRAINT IF EXISTS entities_experience_pkey;
ALTER TABLE IF EXISTS ONLY public.entities_default DROP CONSTRAINT IF EXISTS entities_default_pkey;
ALTER TABLE IF EXISTS ONLY public.entities DROP CONSTRAINT IF EXISTS pk_entities;
ALTER TABLE IF EXISTS ONLY public.context_branches DROP CONSTRAINT IF EXISTS context_branches_pkey;
ALTER TABLE IF EXISTS ONLY public.compliance_log DROP CONSTRAINT IF EXISTS compliance_log_pkey;
ALTER TABLE IF EXISTS ONLY public.collab_groups DROP CONSTRAINT IF EXISTS collab_groups_pkey;
ALTER TABLE IF EXISTS ONLY public.collab_group_members DROP CONSTRAINT IF EXISTS collab_group_members_pkey;
ALTER TABLE IF EXISTS ONLY public.branch_merge_log DROP CONSTRAINT IF EXISTS branch_merge_log_pkey;
ALTER TABLE IF EXISTS ONLY public.agent_session_inactive DROP CONSTRAINT IF EXISTS agent_session_inactive_pkey;
ALTER TABLE IF EXISTS ONLY public.agent_session_active DROP CONSTRAINT IF EXISTS agent_session_active_pkey;
ALTER TABLE IF EXISTS ONLY public.agent_session DROP CONSTRAINT IF EXISTS pk_agent_session;
ALTER TABLE IF EXISTS ONLY public.agent_registry DROP CONSTRAINT IF EXISTS agent_registry_pkey;
ALTER TABLE IF EXISTS ONLY public.agent_permission_log DROP CONSTRAINT IF EXISTS agent_permission_log_pkey;
ALTER TABLE IF EXISTS ONLY public.agent_credentials DROP CONSTRAINT IF EXISTS agent_credentials_pkey;
ALTER TABLE IF EXISTS ONLY public.agent_collaboration DROP CONSTRAINT IF EXISTS agent_collaboration_pkey;
DROP TABLE IF EXISTS public.workspace_tasks;
DROP TABLE IF EXISTS public.workspace_context_audit;
DROP VIEW IF EXISTS public.v_memory_entities;
DROP VIEW IF EXISTS public.v_entity_graph;
DROP VIEW IF EXISTS public.v_branch_comparison;
DROP TABLE IF EXISTS public.workspace_context;
DROP VIEW IF EXISTS public.v_active_sessions;
DROP TABLE IF EXISTS public.workspaces;
DROP TABLE IF EXISTS public.task_tool_calls;
DROP TABLE IF EXISTS public.task_steps;
DROP TABLE IF EXISTS public.task_plans_paused;
DROP TABLE IF EXISTS public.task_plans_default;
DROP TABLE IF EXISTS public.task_plans_completed;
DROP TABLE IF EXISTS public.task_plans_cancelled;
DROP TABLE IF EXISTS public.task_plans_active;
DROP TABLE IF EXISTS public.task_plans;
DROP TABLE IF EXISTS public.task_dependencies;
DROP TABLE IF EXISTS public.task_context_snapshots;
DROP TABLE IF EXISTS public.tags;
DROP TABLE IF EXISTS public.system_users;
DROP TABLE IF EXISTS public.system_config;
DROP TABLE IF EXISTS public.spec_plan_links;
DROP TABLE IF EXISTS public.spec_meta;
DROP TABLE IF EXISTS public.skill_meta;
DROP TABLE IF EXISTS public.skill_access_token;
DROP TABLE IF EXISTS public.ldap_config;
DROP TABLE IF EXISTS public.knowledge_meta;
DROP TABLE IF EXISTS public.harness_meta;
DROP TABLE IF EXISTS public.entity_tags;
DROP TABLE IF EXISTS public.entity_embeddings;
DROP TABLE IF EXISTS public.entity_edges;
DROP TABLE IF EXISTS public.entity_access_log_max;
DROP TABLE IF EXISTS public.entity_access_log_202606;
DROP TABLE IF EXISTS public.entity_access_log_202605;
DROP TABLE IF EXISTS public.entity_access_log;
DROP TABLE IF EXISTS public.entity_access_audit;
DROP TABLE IF EXISTS public.entities_task_output;
DROP TABLE IF EXISTS public.entities_spec;
DROP TABLE IF EXISTS public.entities_skill;
DROP TABLE IF EXISTS public.entities_other;
DROP TABLE IF EXISTS public.entities_memory;
DROP TABLE IF EXISTS public.entities_knowledge;
DROP TABLE IF EXISTS public.entities_harness_template;
DROP TABLE IF EXISTS public.entities_experience;
DROP TABLE IF EXISTS public.entities_default;
DROP TABLE IF EXISTS public.entities;
DROP TABLE IF EXISTS public.context_branches;
DROP TABLE IF EXISTS public.compliance_log;
DROP TABLE IF EXISTS public.collab_groups;
DROP TABLE IF EXISTS public.collab_group_members;
DROP TABLE IF EXISTS public.branch_merge_log;
DROP TABLE IF EXISTS public.agent_session_inactive;
DROP TABLE IF EXISTS public.agent_session_active;
DROP TABLE IF EXISTS public.agent_session;
DROP TABLE IF EXISTS public.agent_registry;
DROP TABLE IF EXISTS public.agent_permission_log;
DROP TABLE IF EXISTS public.agent_credentials;
DROP TABLE IF EXISTS public.agent_collaboration;
DROP FUNCTION IF EXISTS public.workspace_manager_create(p_workspace_name character varying, p_workspace_type character varying, p_isolation_mode character varying, p_owner_user_id character varying, p_current_agent_id character varying, p_metadata jsonb);
DROP FUNCTION IF EXISTS public.workspace_manager_add_context(p_workspace_id bigint, p_agent_id character varying, p_context_type character varying, p_context_data jsonb, p_session_id bigint, p_parent_context_id bigint, p_branch_id bigint, p_visibility character varying);
DROP FUNCTION IF EXISTS public.update_updated_at_column();
DROP FUNCTION IF EXISTS public.spec_manager_link_plan(p_spec_id bigint, p_plan_id bigint, p_link_type character varying, p_link_strength numeric);
DROP FUNCTION IF EXISTS public.spec_manager_create(p_title character varying, p_content text, p_acceptance_criteria jsonb, p_spec_constraints jsonb, p_spec_scope character varying, p_complexity character varying, p_owned_by_agent character varying, p_workspace_id bigint, p_branch_id bigint);
DROP FUNCTION IF EXISTS public.session_cleanup_expired();
DROP FUNCTION IF EXISTS public.session_cleanup_dormant_agents();
DROP FUNCTION IF EXISTS public.memory_fusion_search(p_query text, p_entity_type character varying, p_limit integer);
DROP FUNCTION IF EXISTS public.memory_fusion_retrieve(p_entity_id bigint);
DROP FUNCTION IF EXISTS public.memory_fusion_create(p_entity_type character varying, p_title character varying, p_content text, p_summary character varying, p_category character varying, p_visibility character varying, p_importance numeric, p_owned_by_agent character varying, p_source_agent character varying, p_workspace_id bigint, p_branch_id bigint);
DROP FUNCTION IF EXISTS public.knowledge_api_validate(p_entity_id bigint, p_status character varying);
DROP FUNCTION IF EXISTS public.knowledge_api_schedule_review(p_entity_id bigint, p_interval_days integer);
DROP FUNCTION IF EXISTS public.knowledge_api_create(p_title character varying, p_content text, p_domain character varying, p_topic character varying, p_difficulty character varying, p_source_type character varying, p_confidence numeric, p_owned_by_agent character varying, p_workspace_id bigint);
DROP FUNCTION IF EXISTS public.entities_search_vector_update();
DROP FUNCTION IF EXISTS public.db_crypto_rotate_key(p_old_key text, p_new_key text);
DROP FUNCTION IF EXISTS public.db_crypto_encrypt(p_plaintext text, p_key text);
DROP FUNCTION IF EXISTS public.db_crypto_decrypt(p_ciphertext text, p_key text);
DROP FUNCTION IF EXISTS public.collab_group_manager_create(p_group_name character varying, p_group_type character varying, p_description text, p_workspace_id bigint, p_coordinator_agent_id character varying, p_sharing_policy character varying);
DROP FUNCTION IF EXISTS public.collab_group_manager_add_member(p_group_id bigint, p_agent_id character varying, p_role character varying);
DROP FUNCTION IF EXISTS public.agent_perm_grant(p_agent_id character varying, p_action character varying, p_target_type character varying, p_target_id character varying, p_details jsonb);
DROP FUNCTION IF EXISTS public.agent_perm_check(p_agent_id character varying, p_action character varying, p_target_type character varying, p_target_id character varying);
-- The prepared PostgreSQL target already enables required extensions in
-- public. Dropping the schema would also drop or block pgvector/AGE and makes
-- a clean Bootstrap Deployment Agent installation fail before any platform
-- object is created.
--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS public;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: agent_perm_check(character varying, character varying, character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.agent_perm_check(p_agent_id character varying, p_action character varying, p_target_type character varying, p_target_id character varying) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(*) INTO v_count FROM AGENT_PERMISSION_LOG
    WHERE agent_id = p_agent_id AND action = 'GRANT'
      AND target_type = p_target_type AND target_id = p_target_id;
    RETURN v_count > 0;
END;
$$;


--
-- Name: agent_perm_grant(character varying, character varying, character varying, character varying, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.agent_perm_grant(p_agent_id character varying, p_action character varying, p_target_type character varying, p_target_id character varying, p_details jsonb DEFAULT NULL::jsonb) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_log_id BIGINT;
BEGIN
    INSERT INTO AGENT_PERMISSION_LOG (agent_id, action, target_type, target_id, details)
    VALUES (p_agent_id, p_action, p_target_type, p_target_id, p_details)
    RETURNING log_id INTO v_log_id;
    RETURN v_log_id;
END;
$$;


--
-- Name: collab_group_manager_add_member(bigint, character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.collab_group_manager_add_member(p_group_id bigint, p_agent_id character varying, p_role character varying DEFAULT 'MEMBER'::character varying) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_member_id BIGINT;
BEGIN
    INSERT INTO COLLAB_GROUP_MEMBERS (group_id, agent_id, role)
    VALUES (p_group_id, p_agent_id, p_role)
    RETURNING member_id INTO v_member_id;
    RETURN v_member_id;
END;
$$;


--
-- Name: collab_group_manager_create(character varying, character varying, text, bigint, character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.collab_group_manager_create(p_group_name character varying, p_group_type character varying DEFAULT 'PROJECT'::character varying, p_description text DEFAULT NULL::text, p_workspace_id bigint DEFAULT NULL::bigint, p_coordinator_agent_id character varying DEFAULT NULL::character varying, p_sharing_policy character varying DEFAULT 'OPEN'::character varying) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_group_id BIGINT;
BEGIN
    INSERT INTO COLLAB_GROUPS (group_name, group_type, description, workspace_id,
        coordinator_agent_id, sharing_policy)
    VALUES (p_group_name, p_group_type, p_description, p_workspace_id,
        p_coordinator_agent_id, p_sharing_policy)
    RETURNING group_id INTO v_group_id;
    RETURN v_group_id;
END;
$$;


--
-- Name: db_crypto_decrypt(text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.db_crypto_decrypt(p_ciphertext text, p_key text DEFAULT NULL::text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_key TEXT;
    v_iv BYTEA;
    v_encrypted BYTEA;
BEGIN
    IF p_key IS NULL THEN
        SELECT config_value INTO v_key FROM system_config WHERE config_key = 'credential_encryption_key';
    ELSE
        v_key := p_key;
    END IF;
    v_iv := decode(substring(p_ciphertext, 1, 32), 'hex');
    v_encrypted := decode(substring(p_ciphertext, 33), 'hex');
    RETURN convert_from(decrypt_iv(v_encrypted, v_key::bytea, v_iv, 'aes'), 'UTF8');
END;
$$;


--
-- Name: db_crypto_encrypt(text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.db_crypto_encrypt(p_plaintext text, p_key text DEFAULT NULL::text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_key TEXT;
    v_iv BYTEA;
BEGIN
    IF p_key IS NULL THEN
        SELECT config_value INTO v_key FROM system_config WHERE config_key = 'credential_encryption_key';
    ELSE
        v_key := p_key;
    END IF;
    v_iv := gen_random_bytes(16);
    RETURN encode(v_iv || encrypt_iv(p_plaintext::bytea, v_key::bytea, v_iv, 'aes'), 'hex');
END;
$$;


--
-- Name: db_crypto_rotate_key(text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.db_crypto_rotate_key(p_old_key text, p_new_key text) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_count INT := 0;
    v_rec RECORD;
    v_decrypted TEXT;
BEGIN
    FOR v_rec IN SELECT credential_id, credential_value FROM agent_credentials WHERE is_active = TRUE LOOP
        v_decrypted := db_crypto_decrypt(v_rec.credential_value, p_old_key);
        UPDATE agent_credentials SET credential_value = db_crypto_encrypt(v_decrypted, p_new_key)
        WHERE credential_id = v_rec.credential_id;
        v_count := v_count + 1;
    END LOOP;
    UPDATE system_config SET config_value = p_new_key WHERE config_key = 'credential_encryption_key';
    RETURN v_count;
END;
$$;


--
-- Name: entities_search_vector_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.entities_search_vector_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.summary, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'C');
    RETURN NEW;
END;
$$;


--
-- Name: knowledge_api_create(character varying, text, character varying, character varying, character varying, character varying, numeric, character varying, bigint); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.knowledge_api_create(p_title character varying, p_content text, p_domain character varying DEFAULT NULL::character varying, p_topic character varying DEFAULT NULL::character varying, p_difficulty character varying DEFAULT 'INTERMEDIATE'::character varying, p_source_type character varying DEFAULT NULL::character varying, p_confidence numeric DEFAULT NULL::numeric, p_owned_by_agent character varying DEFAULT NULL::character varying, p_workspace_id bigint DEFAULT NULL::bigint) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_entity_id BIGINT;
BEGIN
    INSERT INTO ENTITIES (entity_type, title, content, visibility, importance, owned_by_agent, workspace_id)
    VALUES ('KNOWLEDGE', p_title, p_content, 'SHARED', 7, p_owned_by_agent, p_workspace_id)
    RETURNING entity_id INTO v_entity_id;
    INSERT INTO KNOWLEDGE_META (entity_id, domain, topic, difficulty, source_type, confidence)
    VALUES (v_entity_id, p_domain, p_topic, p_difficulty, p_source_type, p_confidence);
    RETURN v_entity_id;
END;
$$;


--
-- Name: knowledge_api_schedule_review(bigint, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.knowledge_api_schedule_review(p_entity_id bigint, p_interval_days integer DEFAULT 30) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE KNOWLEDGE_META SET next_review = CURRENT_TIMESTAMP + (p_interval_days || ' days')::INTERVAL
    WHERE entity_id = p_entity_id;
END;
$$;


--
-- Name: knowledge_api_validate(bigint, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.knowledge_api_validate(p_entity_id bigint, p_status character varying DEFAULT 'VALIDATED'::character varying) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE KNOWLEDGE_META SET validation_status = p_status,
        review_count = review_count + 1,
        last_reviewed = CURRENT_TIMESTAMP
    WHERE entity_id = p_entity_id;
END;
$$;


--
-- Name: memory_fusion_create(character varying, character varying, text, character varying, character varying, character varying, numeric, character varying, character varying, bigint, bigint); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.memory_fusion_create(p_entity_type character varying, p_title character varying, p_content text, p_summary character varying DEFAULT NULL::character varying, p_category character varying DEFAULT NULL::character varying, p_visibility character varying DEFAULT 'SHARED'::character varying, p_importance numeric DEFAULT 5, p_owned_by_agent character varying DEFAULT NULL::character varying, p_source_agent character varying DEFAULT NULL::character varying, p_workspace_id bigint DEFAULT NULL::bigint, p_branch_id bigint DEFAULT NULL::bigint) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_entity_id BIGINT;
BEGIN
    INSERT INTO ENTITIES (entity_type, title, content, summary, category, visibility, importance,
        owned_by_agent, source_agent, workspace_id, branch_id)
    VALUES (p_entity_type, p_title, p_content, p_summary, p_category, p_visibility, p_importance,
        p_owned_by_agent, p_source_agent, p_workspace_id, p_branch_id)
    RETURNING entity_id INTO v_entity_id;
    RETURN v_entity_id;
END;
$$;


--
-- Name: memory_fusion_retrieve(bigint); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.memory_fusion_retrieve(p_entity_id bigint) RETURNS TABLE(entity_id bigint, entity_type character varying, title character varying, content text, summary character varying, category character varying, status character varying, importance numeric, owned_by_agent character varying, visibility character varying, workspace_id bigint, retrieval_count integer, created_at timestamp without time zone, updated_at timestamp without time zone)
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE ENTITIES SET retrieval_count = retrieval_count + 1 WHERE entity_id = p_entity_id;
    RETURN QUERY SELECT e.entity_id, e.entity_type, e.title, e.content, e.summary, e.category,
        e.status, e.importance, e.owned_by_agent, e.visibility, e.workspace_id,
        e.retrieval_count, e.created_at, e.updated_at
    FROM ENTITIES e WHERE e.entity_id = p_entity_id;
    RETURN;
END;
$$;


--
-- Name: memory_fusion_search(text, character varying, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.memory_fusion_search(p_query text, p_entity_type character varying DEFAULT NULL::character varying, p_limit integer DEFAULT 20) RETURNS TABLE(entity_id bigint, entity_type character varying, title character varying, summary character varying, rank real)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT e.entity_id, e.entity_type, e.title, e.summary,
        ts_rank(e.search_vector, plainto_tsquery('english', p_query)) AS rank
    FROM ENTITIES e
    WHERE e.search_vector @@ plainto_tsquery('english', p_query)
      AND (p_entity_type IS NULL OR e.entity_type = p_entity_type)
      AND e.status = 'ACTIVE'
    ORDER BY rank DESC
    LIMIT p_limit;
END;
$$;


--
-- Name: session_cleanup_dormant_agents(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.session_cleanup_dormant_agents() RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_timeout_min INT;
    v_count INT;
BEGIN
    SELECT config_value::INT INTO v_timeout_min FROM SYSTEM_CONFIG WHERE config_key = 'dormant_timeout_min';
    UPDATE AGENT_REGISTRY SET status = 'DORMANT'
    WHERE status = 'ACTIVE'
      AND last_active_at < CURRENT_TIMESTAMP - (v_timeout_min || ' minutes')::INTERVAL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;


--
-- Name: session_cleanup_expired(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.session_cleanup_expired() RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_timeout_min INT;
    v_count INT;
BEGIN
    SELECT config_value::INT INTO v_timeout_min FROM SYSTEM_CONFIG WHERE config_key = 'session_timeout_min';
    UPDATE AGENT_SESSION SET is_active = FALSE
    WHERE is_active = TRUE
      AND last_active_at < CURRENT_TIMESTAMP - (v_timeout_min || ' minutes')::INTERVAL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;


--
-- Name: spec_manager_create(character varying, text, jsonb, jsonb, character varying, character varying, character varying, bigint, bigint); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.spec_manager_create(p_title character varying, p_content text, p_acceptance_criteria jsonb DEFAULT NULL::jsonb, p_spec_constraints jsonb DEFAULT NULL::jsonb, p_spec_scope character varying DEFAULT NULL::character varying, p_complexity character varying DEFAULT 'MEDIUM'::character varying, p_owned_by_agent character varying DEFAULT NULL::character varying, p_workspace_id bigint DEFAULT NULL::bigint, p_branch_id bigint DEFAULT NULL::bigint) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_entity_id BIGINT;
BEGIN
    INSERT INTO ENTITIES (entity_type, title, content, visibility, importance, owned_by_agent, workspace_id)
    VALUES ('SPEC', p_title, p_content, 'SHARED', 8, p_owned_by_agent, p_workspace_id)
    RETURNING entity_id INTO v_entity_id;
    INSERT INTO SPEC_META (entity_id, acceptance_criteria, spec_constraints, spec_scope, complexity, branch_id)
    VALUES (v_entity_id, p_acceptance_criteria, p_spec_constraints, p_spec_scope, p_complexity, p_branch_id);
    RETURN v_entity_id;
END;
$$;


--
-- Name: spec_manager_link_plan(bigint, bigint, character varying, numeric); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.spec_manager_link_plan(p_spec_id bigint, p_plan_id bigint, p_link_type character varying DEFAULT 'DRIVES'::character varying, p_link_strength numeric DEFAULT 1.0) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_link_id BIGINT;
BEGIN
    INSERT INTO SPEC_PLAN_LINKS (spec_id, plan_id, link_type, link_strength)
    VALUES (p_spec_id, p_plan_id, p_link_type, p_link_strength)
    RETURNING link_id INTO v_link_id;
    RETURN v_link_id;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: workspace_manager_add_context(bigint, character varying, character varying, jsonb, bigint, bigint, bigint, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.workspace_manager_add_context(p_workspace_id bigint, p_agent_id character varying, p_context_type character varying, p_context_data jsonb, p_session_id bigint DEFAULT NULL::bigint, p_parent_context_id bigint DEFAULT NULL::bigint, p_branch_id bigint DEFAULT NULL::bigint, p_visibility character varying DEFAULT 'SHARED'::character varying) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_context_id BIGINT;
BEGIN
    INSERT INTO WORKSPACE_CONTEXT (workspace_id, agent_id, context_type, context_data,
        session_id, parent_context_id, branch_id, visibility)
    VALUES (p_workspace_id, p_agent_id, p_context_type, p_context_data,
        p_session_id, p_parent_context_id, p_branch_id, p_visibility)
    RETURNING context_id INTO v_context_id;
    RETURN v_context_id;
END;
$$;


--
-- Name: workspace_manager_create(character varying, character varying, character varying, character varying, character varying, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.workspace_manager_create(p_workspace_name character varying, p_workspace_type character varying DEFAULT 'CONVERSATION'::character varying, p_isolation_mode character varying DEFAULT 'SHARED'::character varying, p_owner_user_id character varying DEFAULT NULL::character varying, p_current_agent_id character varying DEFAULT NULL::character varying, p_metadata jsonb DEFAULT NULL::jsonb) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_workspace_id BIGINT;
BEGIN
    INSERT INTO WORKSPACES (workspace_name, workspace_type, isolation_mode, owner_user_id,
        current_agent_id, metadata)
    VALUES (p_workspace_name, p_workspace_type, p_isolation_mode, p_owner_user_id,
        p_current_agent_id, p_metadata)
    RETURNING workspace_id INTO v_workspace_id;
    RETURN v_workspace_id;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_collaboration; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_collaboration (
    collab_id bigint NOT NULL,
    source_agent_id character varying(64) NOT NULL,
    target_agent_id character varying(64) NOT NULL,
    col_type character varying(64) NOT NULL,
    entity_id bigint,
    context jsonb,
    strength numeric(5,4) DEFAULT 1.0000 NOT NULL,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_col_strength CHECK (((strength >= (0)::numeric) AND (strength <= (1)::numeric)))
);


--
-- Name: agent_collaboration_collab_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.agent_collaboration ALTER COLUMN collab_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.agent_collaboration_collab_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: agent_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_credentials (
    credential_id bigint NOT NULL,
    agent_id character varying(64) NOT NULL,
    user_id character varying(64) NOT NULL,
    credential_type character varying(32) NOT NULL,
    credential_value text NOT NULL,
    scope jsonb NOT NULL,
    expires_at timestamp without time zone,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_ac_active CHECK ((is_active = ANY (ARRAY[true, false]))),
    CONSTRAINT ck_ac_type CHECK (((credential_type)::text = ANY (ARRAY[('ACCESS_TOKEN'::character varying)::text, ('SESSION_KEY'::character varying)::text, ('PASSWORD_HASH'::character varying)::text])))
);


--
-- Name: agent_credentials_credential_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.agent_credentials ALTER COLUMN credential_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.agent_credentials_credential_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: agent_permission_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_permission_log (
    log_id bigint NOT NULL,
    agent_id character varying(64) NOT NULL,
    action character varying(32) NOT NULL,
    target_type character varying(64) NOT NULL,
    target_id character varying(64) NOT NULL,
    details jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_apl_action CHECK (((action)::text = ANY (ARRAY[('GRANT'::character varying)::text, ('REVOKE'::character varying)::text, ('DENY'::character varying)::text])))
);


--
-- Name: agent_permission_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.agent_permission_log ALTER COLUMN log_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.agent_permission_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: agent_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_registry (
    agent_id character varying(64) NOT NULL,
    agent_name character varying(256) NOT NULL,
    agent_type character varying(64),
    capabilities jsonb,
    config jsonb,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_by_agent_id character varying(64),
    agent_role character varying(32) DEFAULT 'WORKER'::character varying NOT NULL,
    current_user_id character varying(64),
    portal_node_id character varying(128),
    pool_config jsonb,
    last_active_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    description text,
    wm_entity_id bigint,
    last_seen_at timestamp without time zone,
    CONSTRAINT ck_ar_role CHECK (((agent_role)::text = ANY (ARRAY[('WORKER'::character varying)::text, ('COORDINATOR'::character varying)::text, ('SYSTEM'::character varying)::text]))),
    CONSTRAINT ck_ar_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('INACTIVE'::character varying)::text, ('SUSPENDED'::character varying)::text, ('DECOMMISSIONED'::character varying)::text, ('DORMANT'::character varying)::text, ('POOL'::character varying)::text])))
);

CREATE INDEX idx_ar_portal_node ON public.agent_registry(portal_node_id, status);


--
-- Name: agent_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_session (
    session_id bigint NOT NULL,
    agent_id character varying(64) NOT NULL,
    owner_user_id character varying(64),
    workspace_id bigint,
    predecessor_session_id bigint,
    branch_id bigint,
    is_active boolean DEFAULT true NOT NULL,
    context jsonb,
    last_active_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_as_is_active CHECK ((is_active = ANY (ARRAY[true, false])))
)
PARTITION BY LIST (is_active);


--
-- Name: agent_session_active; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_session_active (
    session_id bigint CONSTRAINT agent_session_session_id_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT agent_session_agent_id_not_null NOT NULL,
    owner_user_id character varying(64),
    workspace_id bigint,
    predecessor_session_id bigint,
    branch_id bigint,
    is_active boolean DEFAULT true CONSTRAINT agent_session_is_active_not_null NOT NULL,
    context jsonb,
    last_active_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT agent_session_created_at_not_null NOT NULL,
    CONSTRAINT ck_as_is_active CHECK ((is_active = ANY (ARRAY[true, false])))
);


--
-- Name: agent_session_inactive; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_session_inactive (
    session_id bigint CONSTRAINT agent_session_session_id_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT agent_session_agent_id_not_null NOT NULL,
    owner_user_id character varying(64),
    workspace_id bigint,
    predecessor_session_id bigint,
    branch_id bigint,
    is_active boolean DEFAULT true CONSTRAINT agent_session_is_active_not_null NOT NULL,
    context jsonb,
    last_active_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT agent_session_created_at_not_null NOT NULL,
    CONSTRAINT ck_as_is_active CHECK ((is_active = ANY (ARRAY[true, false])))
);


--
-- Name: agent_session_session_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.agent_session ALTER COLUMN session_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.agent_session_session_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: branch_merge_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.branch_merge_log (
    log_id bigint NOT NULL,
    source_branch_id bigint NOT NULL,
    target_branch_id bigint NOT NULL,
    merge_status character varying(32) DEFAULT 'PENDING'::character varying NOT NULL,
    conflicts_json jsonb,
    merged_at timestamp without time zone,
    merged_by_agent character varying(64),
    CONSTRAINT ck_bml_status CHECK (((merge_status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('SUCCESS'::character varying)::text, ('PARTIAL'::character varying)::text, ('CONFLICT'::character varying)::text, ('ABORTED'::character varying)::text])))
);


--
-- Name: branch_merge_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.branch_merge_log ALTER COLUMN log_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.branch_merge_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: collab_group_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collab_group_members (
    member_id bigint NOT NULL,
    group_id bigint NOT NULL,
    agent_id character varying(64) NOT NULL,
    role character varying(32) DEFAULT 'MEMBER'::character varying NOT NULL,
    personal_workspace_id bigint,
    branch_id bigint,
    joined_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    CONSTRAINT ck_cgm_role CHECK (((role)::text = ANY (ARRAY[('LEAD'::character varying)::text, ('MEMBER'::character varying)::text, ('OBSERVER'::character varying)::text, ('CONTRIBUTOR'::character varying)::text]))),
    CONSTRAINT ck_cgm_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('LEFT'::character varying)::text, ('REMOVED'::character varying)::text])))
);


--
-- Name: collab_group_members_member_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.collab_group_members ALTER COLUMN member_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.collab_group_members_member_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: collab_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collab_groups (
    group_id bigint NOT NULL,
    group_name character varying(256) NOT NULL,
    group_type character varying(32) DEFAULT 'PROJECT'::character varying NOT NULL,
    description text,
    workspace_id bigint,
    coordinator_agent_id character varying(64),
    sharing_policy character varying(32) DEFAULT 'OPEN'::character varying NOT NULL,
    branch_id bigint,
    spec_id bigint,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_cg_policy CHECK (((sharing_policy)::text = ANY (ARRAY[('OPEN'::character varying)::text, ('MODERATED'::character varying)::text, ('RESTRICTED'::character varying)::text]))),
    CONSTRAINT ck_cg_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('PAUSED'::character varying)::text, ('ARCHIVED'::character varying)::text]))),
    CONSTRAINT ck_cg_type CHECK (((group_type)::text = ANY (ARRAY[('PROJECT'::character varying)::text, ('TEAM'::character varying)::text, ('AD_HOC'::character varying)::text, ('PIPELINE'::character varying)::text])))
);


--
-- Name: collab_groups_group_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.collab_groups ALTER COLUMN group_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.collab_groups_group_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: compliance_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.compliance_log (
    log_id bigint NOT NULL,
    event_type character varying(64) NOT NULL,
    severity character varying(16) DEFAULT 'INFO'::character varying NOT NULL,
    actor_id character varying(64),
    actor_type character varying(32) DEFAULT 'SYSTEM'::character varying,
    target_type character varying(64),
    target_id character varying(128),
    description text,
    metadata jsonb,
    policy_violation boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_cl_severity CHECK (((severity)::text = ANY ((ARRAY['INFO'::character varying, 'WARNING'::character varying, 'ERROR'::character varying, 'CRITICAL'::character varying])::text[])))
);


--
-- Name: compliance_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.compliance_log ALTER COLUMN log_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.compliance_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: context_branches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.context_branches (
    branch_id bigint NOT NULL,
    workspace_id bigint NOT NULL,
    parent_branch_id bigint,
    branch_name character varying(256) NOT NULL,
    branch_type character varying(32) DEFAULT 'FORK'::character varying NOT NULL,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    source_context_id bigint,
    agent_id character varying(64),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    merged_at timestamp without time zone,
    abandoned_at timestamp without time zone,
    description text,
    is_lesson boolean DEFAULT false NOT NULL,
    lesson_tags jsonb,
    CONSTRAINT ck_cb_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('MERGED'::character varying)::text, ('ABANDONED'::character varying)::text, ('PAUSED'::character varying)::text]))),
    CONSTRAINT ck_cb_type CHECK (((branch_type)::text = ANY (ARRAY[('EXPLORATION'::character varying)::text, ('ROLLBACK'::character varying)::text, ('HANDOFF'::character varying)::text, ('PARALLEL'::character varying)::text, ('FORK'::character varying)::text])))
);


--
-- Name: context_branches_branch_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.context_branches ALTER COLUMN branch_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.context_branches_branch_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities (
    entity_id bigint NOT NULL,
    entity_type character varying(32) NOT NULL,
    title character varying(512) NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    importance numeric(3,1) DEFAULT 5 NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
)
PARTITION BY LIST (entity_type);


--
-- Name: entities_default; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_default (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_entity_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.entities ALTER COLUMN entity_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.entities_entity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: entities_experience; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_experience (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_harness_template; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_harness_template (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_knowledge; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_knowledge (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_memory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_memory (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_other; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_other (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_skill; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_skill (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_spec; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_spec (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entities_task_output; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities_task_output (
    entity_id bigint CONSTRAINT entities_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entities_entity_type_not_null NOT NULL,
    title character varying(512) CONSTRAINT entities_title_not_null NOT NULL,
    content text,
    summary character varying(2000),
    category character varying(64),
    status character varying(32) DEFAULT 'ACTIVE'::character varying CONSTRAINT entities_status_not_null NOT NULL,
    importance numeric(3,1) DEFAULT 5 CONSTRAINT entities_importance_not_null NOT NULL,
    owned_by_agent character varying(64),
    source_agent character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying CONSTRAINT entities_visibility_not_null NOT NULL,
    workspace_id bigint,
    branch_id bigint,
    retrieval_count integer DEFAULT 0 CONSTRAINT entities_retrieval_count_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entities_updated_at_not_null NOT NULL,
    expires_at timestamp without time zone,
    search_vector tsvector,
    CONSTRAINT ck_entities_importance CHECK (((importance >= (1)::numeric) AND (importance <= (10)::numeric))),
    CONSTRAINT ck_entities_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text, ('DELETED'::character varying)::text, ('DRAFT'::character varying)::text]))),
    CONSTRAINT ck_entities_type CHECK (((entity_type)::text = ANY (ARRAY[('MEMORY'::character varying)::text, ('KNOWLEDGE'::character varying)::text, ('TASK_OUTPUT'::character varying)::text, ('EXPERIENCE'::character varying)::text, ('HARNESS_TEMPLATE'::character varying)::text, ('SPEC'::character varying)::text, ('SKILL'::character varying)::text, ('OTHER'::character varying)::text]))),
    CONSTRAINT ck_entities_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: entity_access_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_access_audit (
    audit_id bigint NOT NULL,
    entity_id bigint NOT NULL,
    entity_type character varying(32) NOT NULL,
    accessor_id character varying(64) NOT NULL,
    accessor_type character varying(32) DEFAULT 'AGENT'::character varying NOT NULL,
    access_type character varying(32) NOT NULL,
    access_result character varying(16) DEFAULT 'GRANTED'::character varying NOT NULL,
    access_context jsonb,
    ip_address character varying(45),
    user_agent character varying(512),
    accessed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: entity_access_audit_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.entity_access_audit ALTER COLUMN audit_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.entity_access_audit_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: entity_access_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_access_log (
    log_id bigint NOT NULL,
    entity_id bigint NOT NULL,
    entity_type character varying(32) NOT NULL,
    agent_id character varying(64) NOT NULL,
    access_type character varying(32) NOT NULL,
    session_id bigint,
    context jsonb,
    access_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_eal_access_type CHECK (((access_type)::text = ANY (ARRAY[('READ'::character varying)::text, ('WRITE'::character varying)::text, ('DELETE'::character varying)::text, ('SEARCH'::character varying)::text, ('EMBED'::character varying)::text])))
)
PARTITION BY RANGE (access_time);


--
-- Name: entity_access_log_202605; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_access_log_202605 (
    log_id bigint CONSTRAINT entity_access_log_log_id_not_null NOT NULL,
    entity_id bigint CONSTRAINT entity_access_log_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entity_access_log_entity_type_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT entity_access_log_agent_id_not_null NOT NULL,
    access_type character varying(32) CONSTRAINT entity_access_log_access_type_not_null NOT NULL,
    session_id bigint,
    context jsonb,
    access_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entity_access_log_access_time_not_null NOT NULL,
    CONSTRAINT ck_eal_access_type CHECK (((access_type)::text = ANY (ARRAY[('READ'::character varying)::text, ('WRITE'::character varying)::text, ('DELETE'::character varying)::text, ('SEARCH'::character varying)::text, ('EMBED'::character varying)::text])))
);


--
-- Name: entity_access_log_202606; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_access_log_202606 (
    log_id bigint CONSTRAINT entity_access_log_log_id_not_null NOT NULL,
    entity_id bigint CONSTRAINT entity_access_log_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entity_access_log_entity_type_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT entity_access_log_agent_id_not_null NOT NULL,
    access_type character varying(32) CONSTRAINT entity_access_log_access_type_not_null NOT NULL,
    session_id bigint,
    context jsonb,
    access_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entity_access_log_access_time_not_null NOT NULL,
    CONSTRAINT ck_eal_access_type CHECK (((access_type)::text = ANY (ARRAY[('READ'::character varying)::text, ('WRITE'::character varying)::text, ('DELETE'::character varying)::text, ('SEARCH'::character varying)::text, ('EMBED'::character varying)::text])))
);


--
-- Name: entity_access_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.entity_access_log ALTER COLUMN log_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.entity_access_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: entity_access_log_max; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_access_log_max (
    log_id bigint CONSTRAINT entity_access_log_log_id_not_null NOT NULL,
    entity_id bigint CONSTRAINT entity_access_log_entity_id_not_null NOT NULL,
    entity_type character varying(32) CONSTRAINT entity_access_log_entity_type_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT entity_access_log_agent_id_not_null NOT NULL,
    access_type character varying(32) CONSTRAINT entity_access_log_access_type_not_null NOT NULL,
    session_id bigint,
    context jsonb,
    access_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT entity_access_log_access_time_not_null NOT NULL,
    CONSTRAINT ck_eal_access_type CHECK (((access_type)::text = ANY (ARRAY[('READ'::character varying)::text, ('WRITE'::character varying)::text, ('DELETE'::character varying)::text, ('SEARCH'::character varying)::text, ('EMBED'::character varying)::text])))
);


--
-- Name: entity_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_edges (
    edge_id bigint NOT NULL,
    source_id bigint NOT NULL,
    source_type character varying(32) NOT NULL,
    target_id bigint NOT NULL,
    target_type character varying(32),
    edge_type character varying(64) NOT NULL,
    strength numeric(5,4) DEFAULT 1.0000 NOT NULL,
    confidence numeric(5,4) DEFAULT 1.0000 NOT NULL,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_edge_confidence CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric))),
    CONSTRAINT ck_edge_strength CHECK (((strength >= (0)::numeric) AND (strength <= (1)::numeric)))
);


--
-- Name: entity_edges_edge_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.entity_edges ALTER COLUMN edge_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.entity_edges_edge_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: entity_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_embeddings (
    entity_id bigint NOT NULL,
    entity_type character varying(32) NOT NULL,
    embedding public.vector(1024) NOT NULL,
    embedding_model character varying(128),
    embedding_dim integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: entity_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_tags (
    entity_id bigint NOT NULL,
    entity_type character varying(32) NOT NULL,
    tag_id bigint NOT NULL
);


--
-- Name: harness_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.harness_meta (
    entity_id bigint NOT NULL,
    entity_type character varying(32) DEFAULT 'HARNESS_TEMPLATE'::character varying NOT NULL,
    template_version character varying(32) NOT NULL,
    input_schema jsonb,
    output_schema jsonb,
    execution_mode character varying(32) DEFAULT 'SEQUENTIAL'::character varying NOT NULL,
    CONSTRAINT ck_hm_entity_type CHECK (((entity_type)::text = 'HARNESS_TEMPLATE'::text)),
    CONSTRAINT ck_hm_exec_mode CHECK (((execution_mode)::text = ANY (ARRAY[('SEQUENTIAL'::character varying)::text, ('PARALLEL'::character varying)::text, ('CONDITIONAL'::character varying)::text])))
);


--
-- Name: knowledge_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_meta (
    entity_id bigint NOT NULL,
    entity_type character varying(32) DEFAULT 'KNOWLEDGE'::character varying NOT NULL,
    domain character varying(128),
    topic character varying(256),
    difficulty character varying(16) DEFAULT 'INTERMEDIATE'::character varying NOT NULL,
    review_count integer DEFAULT 0 NOT NULL,
    last_reviewed timestamp without time zone,
    next_review timestamp without time zone,
    CONSTRAINT ck_km_difficulty CHECK (((difficulty)::text = ANY (ARRAY[('BEGINNER'::character varying)::text, ('INTERMEDIATE'::character varying)::text, ('ADVANCED'::character varying)::text, ('EXPERT'::character varying)::text]))),
    CONSTRAINT ck_km_entity_type CHECK (((entity_type)::text = 'KNOWLEDGE'::text))
);


--
-- Name: ldap_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ldap_config (
    config_id bigint NOT NULL,
    config_name character varying(128) NOT NULL,
    server_url character varying(512) NOT NULL,
    bind_dn character varying(512),
    bind_password text,
    search_base character varying(512) NOT NULL,
    search_filter character varying(512) NOT NULL,
    group_base character varying(512),
    group_filter character varying(512),
    use_ssl boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    port integer DEFAULT 636 NOT NULL,
    sync_interval_min integer DEFAULT 60 NOT NULL,
    group_role_mapping jsonb,
    last_sync_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ldap_config_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.ldap_config ALTER COLUMN config_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.ldap_config_config_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: skill_access_token; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skill_access_token (
    token_id bigint NOT NULL,
    skill_id bigint NOT NULL,
    token_hash character varying(128) NOT NULL,
    requested_by character varying(64) NOT NULL,
    granted_by character varying(64),
    token_type character varying(32) DEFAULT 'ACCESS'::character varying NOT NULL,
    expires_at timestamp without time zone,
    consumed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_sat_type CHECK (((token_type)::text = ANY ((ARRAY['ACCESS'::character varying, 'DOWNLOAD'::character varying, 'VIEW'::character varying])::text[])))
);


--
-- Name: skill_access_token_token_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.skill_access_token ALTER COLUMN token_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.skill_access_token_token_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: skill_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skill_meta (
    skill_id bigint NOT NULL,
    skill_name character varying(256) NOT NULL,
    skill_version character varying(32),
    description text,
    skill_type character varying(32) DEFAULT 'TOOL'::character varying NOT NULL,
    category character varying(64),
    visibility character varying(16) DEFAULT 'SHARED'::character varying NOT NULL,
    owned_by_agent character varying(64),
    input_schema jsonb,
    output_schema jsonb,
    dependencies jsonb,
    resource_path character varying(2048),
    download_count integer DEFAULT 0 NOT NULL,
    rating numeric(3,2),
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone,
    CONSTRAINT ck_skm_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('DEPRECATED'::character varying)::text, ('DISABLED'::character varying)::text]))),
    CONSTRAINT ck_skm_type CHECK (((skill_type)::text = ANY (ARRAY[('TOOL'::character varying)::text, ('TEMPLATE'::character varying)::text, ('WORKFLOW'::character varying)::text, ('CUSTOM'::character varying)::text]))),
    CONSTRAINT ck_skm_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: skill_meta_skill_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.skill_meta ALTER COLUMN skill_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.skill_meta_skill_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: spec_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spec_meta (
    entity_id bigint NOT NULL,
    entity_type character varying(32) DEFAULT 'SPEC'::character varying NOT NULL,
    spec_version integer DEFAULT 1 NOT NULL,
    spec_status character varying(32) DEFAULT 'DRAFT'::character varying NOT NULL,
    acceptance_criteria jsonb,
    spec_constraints jsonb,
    spec_scope character varying(64),
    complexity character varying(16) DEFAULT 'MEDIUM'::character varying NOT NULL,
    branch_id bigint,
    parent_spec_id bigint,
    CONSTRAINT ck_sm_complexity CHECK (((complexity)::text = ANY (ARRAY[('LOW'::character varying)::text, ('MEDIUM'::character varying)::text, ('HIGH'::character varying)::text, ('CRITICAL'::character varying)::text]))),
    CONSTRAINT ck_sm_entity_type CHECK (((entity_type)::text = 'SPEC'::text)),
    CONSTRAINT ck_sm_spec_status CHECK (((spec_status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('REVIEWED'::character varying)::text, ('APPROVED'::character varying)::text, ('IMPLEMENTED'::character varying)::text, ('DEPRECATED'::character varying)::text])))
);


--
-- Name: spec_plan_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spec_plan_links (
    link_id bigint NOT NULL,
    spec_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    link_type character varying(32) NOT NULL,
    link_strength numeric(5,4) DEFAULT 1.0000 NOT NULL,
    CONSTRAINT ck_spl_strength CHECK (((link_strength >= (0)::numeric) AND (link_strength <= (1)::numeric))),
    CONSTRAINT ck_spl_type CHECK (((link_type)::text = ANY (ARRAY[('DRIVES'::character varying)::text, ('VALIDATES'::character varying)::text, ('CONSTRAINS'::character varying)::text, ('EXTENDS'::character varying)::text])))
);


--
-- Name: spec_plan_links_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.spec_plan_links ALTER COLUMN link_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.spec_plan_links_link_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: system_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_config (
    config_key character varying(128) NOT NULL,
    config_value text NOT NULL,
    description text,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: system_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_users (
    user_id bigint NOT NULL,
    username character varying(128) NOT NULL,
    password_hash text,
    salt character varying(128),
    role character varying(64) DEFAULT 'USER'::character varying NOT NULL,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    auth_source character varying(16) DEFAULT 'LOCAL'::character varying NOT NULL,
    ldap_dn character varying(512),
    last_ldap_sync timestamp without time zone,
    last_login timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_su_auth_source CHECK (((auth_source)::text = ANY (ARRAY[('LOCAL'::character varying)::text, ('LDAP'::character varying)::text]))),
    CONSTRAINT ck_su_role CHECK (((role)::text = ANY (ARRAY[('ADMIN'::character varying)::text, ('USER'::character varying)::text, ('SERVICE'::character varying)::text]))),
    CONSTRAINT ck_su_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('INACTIVE'::character varying)::text, ('LOCKED'::character varying)::text])))
);


--
-- Name: system_users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.system_users ALTER COLUMN user_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.system_users_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tags (
    tag_id bigint NOT NULL,
    tag_name character varying(128) NOT NULL,
    tag_group character varying(64),
    usage_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: tags_tag_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.tags ALTER COLUMN tag_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.tags_tag_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: task_context_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_context_snapshots (
    snapshot_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    snapshot_type character varying(64) DEFAULT 'AUTO'::character varying NOT NULL,
    context_data jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: task_context_snapshots_snapshot_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.task_context_snapshots ALTER COLUMN snapshot_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.task_context_snapshots_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: task_dependencies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_dependencies (
    dep_id bigint NOT NULL,
    source_plan_id bigint NOT NULL,
    target_plan_id bigint NOT NULL,
    dep_type character varying(64) DEFAULT 'HARD'::character varying NOT NULL,
    CONSTRAINT ck_dep_type CHECK (((dep_type)::text = ANY (ARRAY[('HARD'::character varying)::text, ('SOFT'::character varying)::text, ('TRIGGERS'::character varying)::text, ('RELATES_TO'::character varying)::text])))
);


--
-- Name: task_dependencies_dep_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.task_dependencies ALTER COLUMN dep_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.task_dependencies_dep_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: task_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_plans (
    plan_id bigint NOT NULL,
    agent_id character varying(64) NOT NULL,
    goal text NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    priority integer DEFAULT 5 NOT NULL,
    strategy character varying(64),
    result_summary text,
    branch_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_tp_priority CHECK (((priority >= 1) AND (priority <= 10))),
    CONSTRAINT ck_tp_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('BLOCKED'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
)
PARTITION BY LIST (status);


--
-- Name: task_plans_active; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_plans_active (
    plan_id bigint CONSTRAINT task_plans_plan_id_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT task_plans_agent_id_not_null NOT NULL,
    goal text CONSTRAINT task_plans_goal_not_null NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying CONSTRAINT task_plans_status_not_null NOT NULL,
    priority integer DEFAULT 5 CONSTRAINT task_plans_priority_not_null NOT NULL,
    strategy character varying(64),
    result_summary text,
    branch_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_updated_at_not_null NOT NULL,
    CONSTRAINT ck_tp_priority CHECK (((priority >= 1) AND (priority <= 10))),
    CONSTRAINT ck_tp_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('BLOCKED'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
);


--
-- Name: task_plans_cancelled; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_plans_cancelled (
    plan_id bigint CONSTRAINT task_plans_plan_id_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT task_plans_agent_id_not_null NOT NULL,
    goal text CONSTRAINT task_plans_goal_not_null NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying CONSTRAINT task_plans_status_not_null NOT NULL,
    priority integer DEFAULT 5 CONSTRAINT task_plans_priority_not_null NOT NULL,
    strategy character varying(64),
    result_summary text,
    branch_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_updated_at_not_null NOT NULL,
    CONSTRAINT ck_tp_priority CHECK (((priority >= 1) AND (priority <= 10))),
    CONSTRAINT ck_tp_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('BLOCKED'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
);


--
-- Name: task_plans_completed; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_plans_completed (
    plan_id bigint CONSTRAINT task_plans_plan_id_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT task_plans_agent_id_not_null NOT NULL,
    goal text CONSTRAINT task_plans_goal_not_null NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying CONSTRAINT task_plans_status_not_null NOT NULL,
    priority integer DEFAULT 5 CONSTRAINT task_plans_priority_not_null NOT NULL,
    strategy character varying(64),
    result_summary text,
    branch_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_updated_at_not_null NOT NULL,
    CONSTRAINT ck_tp_priority CHECK (((priority >= 1) AND (priority <= 10))),
    CONSTRAINT ck_tp_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('BLOCKED'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
);


--
-- Name: task_plans_default; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_plans_default (
    plan_id bigint CONSTRAINT task_plans_plan_id_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT task_plans_agent_id_not_null NOT NULL,
    goal text CONSTRAINT task_plans_goal_not_null NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying CONSTRAINT task_plans_status_not_null NOT NULL,
    priority integer DEFAULT 5 CONSTRAINT task_plans_priority_not_null NOT NULL,
    strategy character varying(64),
    result_summary text,
    branch_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_updated_at_not_null NOT NULL,
    CONSTRAINT ck_tp_priority CHECK (((priority >= 1) AND (priority <= 10))),
    CONSTRAINT ck_tp_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('BLOCKED'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
);


--
-- Name: task_plans_paused; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_plans_paused (
    plan_id bigint CONSTRAINT task_plans_plan_id_not_null NOT NULL,
    agent_id character varying(64) CONSTRAINT task_plans_agent_id_not_null NOT NULL,
    goal text CONSTRAINT task_plans_goal_not_null NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying CONSTRAINT task_plans_status_not_null NOT NULL,
    priority integer DEFAULT 5 CONSTRAINT task_plans_priority_not_null NOT NULL,
    strategy character varying(64),
    result_summary text,
    branch_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT task_plans_updated_at_not_null NOT NULL,
    CONSTRAINT ck_tp_priority CHECK (((priority >= 1) AND (priority <= 10))),
    CONSTRAINT ck_tp_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('BLOCKED'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
);


--
-- Name: task_plans_plan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.task_plans ALTER COLUMN plan_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.task_plans_plan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: task_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_steps (
    step_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    plan_status character varying(30) NOT NULL,
    step_order integer NOT NULL,
    description text NOT NULL,
    tool_name character varying(128),
    tool_input jsonb,
    tool_output jsonb,
    loop_id bigint,
    step_completion_type character varying(20) DEFAULT 'MANUAL' NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_ts_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('BLOCKED'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('SKIPPED'::character varying)::text, ('WAITING_LOOP'::character varying)::text]))),
    CONSTRAINT ck_ts_completion CHECK (((step_completion_type)::text = ANY (ARRAY[('MANUAL'::character varying)::text, ('LOOP'::character varying)::text, ('SPEC'::character varying)::text])))
);


--
-- Name: task_steps_step_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.task_steps ALTER COLUMN step_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.task_steps_step_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: task_tool_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_tool_calls (
    call_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    step_id bigint,
    tool_name character varying(128) NOT NULL,
    tool_input jsonb,
    tool_output jsonb,
    status character varying(30),
    duration_ms integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_ttc_status CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('TIMEOUT'::character varying)::text])))
);


--
-- Name: task_tool_calls_call_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.task_tool_calls ALTER COLUMN call_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.task_tool_calls_call_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workspaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspaces (
    workspace_id bigint NOT NULL,
    workspace_name character varying(256) NOT NULL,
    workspace_type character varying(32) DEFAULT 'CONVERSATION'::character varying NOT NULL,
    workspace_alias character varying(256),
    isolation_mode character varying(16) DEFAULT 'SHARED'::character varying NOT NULL,
    owner_user_id character varying(64),
    current_agent_id character varying(64),
    current_session_id bigint,
    branch_id bigint,
    summary text,
    metadata jsonb,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_ws_isolation CHECK (((isolation_mode)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('ISOLATED'::character varying)::text]))),
    CONSTRAINT ck_ws_status CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('PAUSED'::character varying)::text, ('COMPLETED'::character varying)::text, ('ABANDONED'::character varying)::text]))),
    CONSTRAINT ck_ws_type CHECK (((workspace_type)::text = ANY (ARRAY[('CONVERSATION'::character varying)::text, ('PROJECT'::character varying)::text, ('TASK_CHAIN'::character varying)::text, ('AUTONOMOUS'::character varying)::text, ('COLLAB_GROUP'::character varying)::text, ('PERSONAL_IN_GROUP'::character varying)::text])))
);


--
-- Name: v_active_sessions; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_active_sessions AS
 SELECT s.session_id,
    s.agent_id,
    s.owner_user_id,
    s.workspace_id,
    s.predecessor_session_id,
    s.branch_id,
    s.context,
    s.last_active_at,
    s.created_at,
    ar.agent_name,
    ar.agent_type,
    ar.agent_role,
    w.workspace_name,
    w.workspace_type
   FROM ((public.agent_session s
     JOIN public.agent_registry ar ON (((ar.agent_id)::text = (s.agent_id)::text)))
     LEFT JOIN public.workspaces w ON ((w.workspace_id = s.workspace_id)))
  WHERE (s.is_active = true);


--
-- Name: workspace_context; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_context (
    context_id bigint NOT NULL,
    workspace_id bigint NOT NULL,
    agent_id character varying(64) NOT NULL,
    session_id bigint,
    context_type character varying(32) NOT NULL,
    context_data jsonb NOT NULL,
    parent_context_id bigint,
    branch_id bigint,
    visibility character varying(20) DEFAULT 'SHARED'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_wc_type CHECK (((context_type)::text = ANY (ARRAY[('CHECKPOINT'::character varying)::text, ('HANDOFF'::character varying)::text, ('SUMMARY'::character varying)::text, ('ERROR_STATE'::character varying)::text, ('AUTO_SAVE'::character varying)::text, ('CHAT_MESSAGE'::character varying)::text, ('BRANCH_POINT'::character varying)::text]))),
    CONSTRAINT ck_ws_ctx_visibility CHECK (((visibility)::text = ANY (ARRAY[('PRIVATE'::character varying)::text, ('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))
);


--
-- Name: v_branch_comparison; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_branch_comparison AS
 SELECT b1.branch_id AS branch_a,
    b2.branch_id AS branch_b,
    b1.source_context_id AS common_ancestor,
    b1.workspace_id,
    ( SELECT count(*) AS count
           FROM public.workspace_context wc
          WHERE (wc.branch_id = b1.branch_id)) AS ctx_count_a,
    ( SELECT count(*) AS count
           FROM public.workspace_context wc
          WHERE (wc.branch_id = b2.branch_id)) AS ctx_count_b,
    b1.agent_id AS agent_a,
    b2.agent_id AS agent_b,
    b1.branch_type AS type_a,
    b2.branch_type AS type_b,
    b1.status AS status_a,
    b2.status AS status_b
   FROM (public.context_branches b1
     JOIN public.context_branches b2 ON (((b1.workspace_id = b2.workspace_id) AND (b1.source_context_id = b2.source_context_id) AND (b1.branch_id < b2.branch_id))));


--
-- Name: v_entity_graph; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_entity_graph AS
 SELECT eg.edge_id,
    eg.source_id,
    eg.source_type,
    eg.target_id,
    eg.target_type,
    eg.edge_type,
    eg.strength,
    eg.confidence,
    eg.metadata,
    eg.created_at,
    se.title AS source_title,
    se.category AS source_category,
    te.title AS target_title,
    te.category AS target_category
   FROM ((public.entity_edges eg
     JOIN public.entities se ON (((se.entity_id = eg.source_id) AND ((se.entity_type)::text = (eg.source_type)::text))))
     JOIN public.entities te ON ((te.entity_id = eg.target_id)));


--
-- Name: v_memory_entities; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_memory_entities AS
 SELECT entity_id,
    entity_type,
    title,
    content,
    summary,
    category,
    status,
    importance,
    owned_by_agent,
    source_agent,
    visibility,
    workspace_id,
    branch_id,
    retrieval_count,
    created_at,
    updated_at,
    expires_at
   FROM public.entities e
  WHERE ((entity_type)::text = 'MEMORY'::text);


--
-- Name: workspace_context_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_context_audit (
    audit_id bigint NOT NULL,
    context_id bigint NOT NULL,
    workspace_id bigint NOT NULL,
    action_type character varying(32) NOT NULL,
    old_value jsonb,
    new_value jsonb,
    changed_by character varying(64),
    changed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_wca_action CHECK (((action_type)::text = ANY ((ARRAY['INSERT'::character varying, 'UPDATE'::character varying, 'DELETE'::character varying, 'SAVE'::character varying, 'RESTORE'::character varying, 'FORK'::character varying, 'MERGE'::character varying])::text[])))
);


--
-- Name: workspace_context_audit_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.workspace_context_audit ALTER COLUMN audit_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.workspace_context_audit_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workspace_context_context_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.workspace_context ALTER COLUMN context_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.workspace_context_context_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workspace_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_tasks (
    workspace_id bigint NOT NULL,
    plan_id bigint NOT NULL
);


--
-- Name: workspaces_workspace_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.workspaces ALTER COLUMN workspace_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.workspaces_workspace_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: agent_session_active; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_session ATTACH PARTITION public.agent_session_active FOR VALUES IN (true);


--
-- Name: agent_session_inactive; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_session ATTACH PARTITION public.agent_session_inactive FOR VALUES IN (false);


--
-- Name: entities_default; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_default DEFAULT;


--
-- Name: entities_experience; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_experience FOR VALUES IN ('EXPERIENCE');


--
-- Name: entities_harness_template; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_harness_template FOR VALUES IN ('HARNESS_TEMPLATE');


--
-- Name: entities_knowledge; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_knowledge FOR VALUES IN ('KNOWLEDGE');


--
-- Name: entities_memory; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_memory FOR VALUES IN ('MEMORY');


--
-- Name: entities_other; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_other FOR VALUES IN ('OTHER');


--
-- Name: entities_skill; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_skill FOR VALUES IN ('SKILL');


--
-- Name: entities_spec; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_spec FOR VALUES IN ('SPEC');


--
-- Name: entities_task_output; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ATTACH PARTITION public.entities_task_output FOR VALUES IN ('TASK_OUTPUT');


--
-- Name: entity_access_log_202605; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_access_log ATTACH PARTITION public.entity_access_log_202605 FOR VALUES FROM (MINVALUE) TO ('2026-06-01 00:00:00');


--
-- Name: entity_access_log_202606; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_access_log ATTACH PARTITION public.entity_access_log_202606 FOR VALUES FROM ('2026-06-01 00:00:00') TO ('2026-07-01 00:00:00');


--
-- Name: entity_access_log_max; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_access_log ATTACH PARTITION public.entity_access_log_max FOR VALUES FROM ('2026-07-01 00:00:00') TO (MAXVALUE);


--
-- Name: task_plans_active; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans ATTACH PARTITION public.task_plans_active FOR VALUES IN ('ACTIVE');


--
-- Name: task_plans_cancelled; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans ATTACH PARTITION public.task_plans_cancelled FOR VALUES IN ('CANCELLED');


--
-- Name: task_plans_completed; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans ATTACH PARTITION public.task_plans_completed FOR VALUES IN ('COMPLETED');


--
-- Name: task_plans_default; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans ATTACH PARTITION public.task_plans_default DEFAULT;


--
-- Name: task_plans_paused; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans ATTACH PARTITION public.task_plans_paused FOR VALUES IN ('PAUSED');


--
-- Data for Name: agent_collaboration; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agent_collaboration (collab_id, source_agent_id, target_agent_id, col_type, entity_id, context, strength, status, created_at) FROM stdin;
\.


--
-- Data for Name: agent_credentials; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agent_credentials (credential_id, agent_id, user_id, credential_type, credential_value, scope, expires_at, is_active, created_at) FROM stdin;
\.


--
-- Data for Name: agent_permission_log; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agent_permission_log (log_id, agent_id, action, target_type, target_id, details, created_at) FROM stdin;
\.


--
-- Data for Name: agent_registry; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agent_registry (agent_id, agent_name, agent_type, capabilities, config, status, created_by_agent_id, agent_role, current_user_id, pool_config, last_active_at, created_at, updated_at, description, wm_entity_id, last_seen_at) FROM stdin;
pg-collab-lead-1781622078	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:20.142276	2026-06-16 11:01:20.142276	\N	\N	\N
pg-collab-member-1781622078	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:20.145579	2026-06-16 11:01:20.145579	\N	\N	\N
pg-collab-observer-1781622078	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:20.148858	2026-06-16 11:01:20.148858	\N	\N	\N
pg-collab-lead-1781624408	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:40:09.942451	2026-06-16 11:40:09.942451	\N	\N	\N
pg-collab-member-1781624408	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:40:09.945604	2026-06-16 11:40:09.945604	\N	\N	\N
pg-ws-agent-1781622078	PG WS Test Agent 1	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:21.346244	2026-06-16 11:01:21.346244	\N	\N	\N
pg-collab-observer-1781624408	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:40:09.949864	2026-06-16 11:40:09.949864	\N	\N	\N
pg-collab-lead-1781623468	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:24:29.944813	2026-06-16 11:24:29.944813	\N	\N	\N
pg-collab-member-1781623468	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:24:29.947737	2026-06-16 11:24:29.947737	\N	\N	\N
pg-collab-observer-1781623468	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:24:29.950789	2026-06-16 11:24:29.950789	\N	\N	\N
pg-ws-agent-1781624408	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:40:11.232689	2026-06-16 11:40:11.255528	\N	\N	2026-06-16 11:40:11.255528
pg-ws-agent2-1781624408	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:40:11.258333	2026-06-16 11:40:11.258333	\N	\N	\N
pg-collab-lead-1781624636	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:43:57.91324	2026-06-16 11:43:57.91324	\N	\N	\N
pg-collab-member-1781624636	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:43:57.916429	2026-06-16 11:43:57.916429	\N	\N	\N
pg-collab-lead-1781622060	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:01.80325	2026-06-16 11:01:01.80325	\N	\N	\N
pg-collab-member-1781622060	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:01.806741	2026-06-16 11:01:01.806741	\N	\N	\N
pg-collab-observer-1781622060	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:01.809813	2026-06-16 11:01:01.809813	\N	\N	\N
pg-collab-observer-1781624636	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:43:57.919077	2026-06-16 11:43:57.919077	\N	\N	\N
pg-spec-agent-1781626161	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:09:24.513931	2026-06-16 12:09:24.513931	\N	\N	\N
pg-ws-agent-1781622060	PG WS Test Agent 1	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:03.278106	2026-06-16 11:01:03.278106	\N	\N	\N
pg-collab-lead-1781623308	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:21:50.041111	2026-06-16 11:21:50.041111	\N	\N	\N
pg-collab-member-1781623308	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:21:50.043828	2026-06-16 11:21:50.043828	\N	\N	\N
pg-ws-agent-1781623468	PG WS Test Agent 1	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:24:31.177152	2026-06-16 11:24:31.177152	\N	\N	\N
pg-ws-agent2-1781623468	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:24:31.19855	2026-06-16 11:24:31.19855	\N	\N	\N
pg-collab-observer-1781623308	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:21:50.046188	2026-06-16 11:21:50.046188	\N	\N	\N
pg-spec-agent-1781624636	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:43:59.229089	2026-06-16 11:43:59.229089	\N	\N	\N
pg-ws-agent-1781624171	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:36:14.293933	2026-06-16 11:36:14.317265	\N	\N	2026-06-16 11:36:14.317265
pg-ws-agent-1781624636	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:43:59.341243	2026-06-16 11:43:59.364696	\N	\N	2026-06-16 11:43:59.364696
pg-ws-agent2-1781624636	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:43:59.367345	2026-06-16 11:43:59.367345	\N	\N	\N
pg-spec-agent-1781624646	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:44:06.654491	2026-06-16 11:44:06.654491	\N	\N	\N
pg-ws-agent-1781623308	PG WS Test Agent 1	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:21:51.155283	2026-06-16 11:21:51.155283	\N	\N	\N
pg-ws-agent2-1781623308	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:21:51.177497	2026-06-16 11:21:51.177497	\N	\N	\N
pg-spec-agent-1781624736	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:45:36.657458	2026-06-16 11:45:36.657458	\N	\N	\N
pg-spec-agent-1781624754	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:45:54.662563	2026-06-16 11:45:54.662563	\N	\N	\N
pg-ws-agent-1781623917	PG WS Test Agent 1	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:32:00.224376	2026-06-16 11:32:00.224376	\N	\N	\N
pg-ws-agent2-1781623917	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:32:00.245892	2026-06-16 11:32:00.245892	\N	\N	\N
pg-ws-agent2-1781624117	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:35:17.65655	2026-06-16 11:35:17.65655	\N	\N	\N
pg-spec-agent-1781624762	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:02.619111	2026-06-16 11:46:02.619111	\N	\N	\N
pg-ws-agent2-1781624171	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:36:14.320179	2026-06-16 11:36:14.320179	\N	\N	\N
pg-spec-agent-1781624795	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:35.664817	2026-06-16 11:46:35.664817	\N	\N	\N
pg-collab-lead-1781624801	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:42.87801	2026-06-16 11:46:42.87801	\N	\N	\N
pg-collab-member-1781624801	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:42.882013	2026-06-16 11:46:42.882013	\N	\N	\N
pg-collab-observer-1781624801	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:42.884878	2026-06-16 11:46:42.884878	\N	\N	\N
pg-collab-lead-1781623917	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:31:58.932875	2026-06-16 11:31:58.932875	\N	\N	\N
pg-collab-member-1781623917	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:31:58.935931	2026-06-16 11:31:58.935931	\N	\N	\N
pg-collab-observer-1781623917	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:31:58.938748	2026-06-16 11:31:58.938748	\N	\N	\N
pg-ws-agent-1781624271	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:37:54.31636	2026-06-16 11:37:54.338826	\N	\N	2026-06-16 11:37:54.338826
pg-ws-agent2-1781624271	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:37:54.341662	2026-06-16 11:37:54.341662	\N	\N	\N
pg-spec-agent-1781624801	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:44.191801	2026-06-16 11:46:44.191801	\N	\N	\N
pg-ws-agent-1781624801	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:44.295088	2026-06-16 11:46:44.316494	\N	\N	2026-06-16 11:46:44.316494
pg-ws-agent2-1781624801	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:46:44.319336	2026-06-16 11:46:44.319336	\N	\N	\N
pg-collab-lead-1781624171	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:36:12.95522	2026-06-16 11:36:12.95522	\N	\N	\N
pg-collab-member-1781624171	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:36:12.958342	2026-06-16 11:36:12.958342	\N	\N	\N
pg-collab-observer-1781624171	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:36:12.962629	2026-06-16 11:36:12.962629	\N	\N	\N
pg-collab-lead-1781624271	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:37:52.952309	2026-06-16 11:37:52.952309	\N	\N	\N
pg-collab-member-1781624271	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:37:52.955701	2026-06-16 11:37:52.955701	\N	\N	\N
pg-collab-observer-1781624271	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:37:52.959024	2026-06-16 11:37:52.959024	\N	\N	\N
admin-test-agent	Admin Test Agent	BUSINESS	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 09:58:29.642031	2026-06-16 12:10:40.212724	Test agent for admin registration	\N	2026-06-16 12:10:40.212724
pg-ws-agent-1781626161	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:09:24.613225	2026-06-16 12:09:24.63733	\N	\N	2026-06-16 12:09:24.63733
pg-ws-agent2-1781626161	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:09:24.640686	2026-06-16 12:09:24.640686	\N	\N	\N
full-flow-agent	Full Flow Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 09:58:29.659382	2026-06-16 12:10:40.234912	\N	\N	2026-06-16 12:10:40.234912
pgtest-agent-1	PG Test Agent 1781626239	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:01:01.723913	2026-06-16 12:10:40.758614	Updated PG test agent	\N	2026-06-16 12:10:40.750204
recovery-test-agent	Recovery Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 09:58:30.070461	2026-06-16 12:10:40.705736	\N	\N	2026-06-16 11:10:40.682128
rc-return-test-agent	RC Return Test	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 09:58:57.202669	2026-06-16 12:10:40.739386	\N	\N	2026-06-16 12:10:40.739386
pg-collab-lead-1781625015	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:50:16.923364	2026-06-16 11:50:16.923364	\N	\N	\N
pg-collab-member-1781625015	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:50:16.926621	2026-06-16 11:50:16.926621	\N	\N	\N
pg-collab-observer-1781625015	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:50:16.92944	2026-06-16 11:50:16.92944	\N	\N	\N
pg-collab-lead-1781626239	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:40.896338	2026-06-16 12:10:40.896338	\N	\N	\N
pg-collab-member-1781626239	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:40.901671	2026-06-16 12:10:40.901671	\N	\N	\N
pg-spec-agent-1781625015	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:50:18.242326	2026-06-16 11:50:18.242326	\N	\N	\N
pg-ws-agent-1781625015	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:50:18.343642	2026-06-16 11:50:18.365237	\N	\N	2026-06-16 11:50:18.365237
pg-ws-agent2-1781625015	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 11:50:18.368251	2026-06-16 11:50:18.368251	\N	\N	\N
pg-collab-lead-1781626199	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:00.907936	2026-06-16 12:10:00.907936	\N	\N	\N
pg-collab-member-1781626199	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:00.911247	2026-06-16 12:10:00.911247	\N	\N	\N
pg-collab-observer-1781626199	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:00.91441	2026-06-16 12:10:00.91441	\N	\N	\N
pg-collab-lead-1781626045	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:26.903806	2026-06-16 12:07:26.903806	\N	\N	\N
pg-collab-member-1781626045	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:26.906368	2026-06-16 12:07:26.906368	\N	\N	\N
pg-collab-observer-1781626045	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:26.910584	2026-06-16 12:07:26.910584	\N	\N	\N
pg-collab-lead-1781625634	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:35.936	2026-06-16 12:00:35.936	\N	\N	\N
pg-collab-member-1781625634	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:35.939092	2026-06-16 12:00:35.939092	\N	\N	\N
pg-collab-observer-1781625634	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:35.942215	2026-06-16 12:00:35.942215	\N	\N	\N
pg-ws-agent-1781626199	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:02.641575	2026-06-16 12:10:02.665143	\N	\N	2026-06-16 12:10:02.665143
pg-spec-agent-1781626199	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:02.534861	2026-06-16 12:10:02.534861	\N	\N	\N
pg-ws-agent2-1781626199	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:02.669643	2026-06-16 12:10:02.669643	\N	\N	\N
pg-spec-agent-1781625758	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:02:41.446992	2026-06-16 12:02:41.446992	\N	\N	\N
pg-ws-agent-1781625758	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:02:41.546985	2026-06-16 12:02:41.569606	\N	\N	2026-06-16 12:02:41.569606
pg-spec-agent-1781625634	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:37.448938	2026-06-16 12:00:37.448938	\N	\N	\N
pg-ws-agent-1781625634	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:37.554664	2026-06-16 12:00:37.578123	\N	\N	2026-06-16 12:00:37.578123
pg-ws-agent2-1781625634	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:37.581098	2026-06-16 12:00:37.581098	\N	\N	\N
pg-ws-agent2-1781625758	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:02:41.573328	2026-06-16 12:02:41.573328	\N	\N	\N
pgtest-pool-agent	PG Pool Agent 1781626239	test	\N	{"pool_config": {"auto_wake": false, "skills_tags": ["python", "sql", "postgresql"], "max_idle_minutes": 60}}	POOL	\N	WORKER	\N	\N	2026-06-16 12:10:40.807653	2026-06-16 11:01:01.770662	2026-06-16 12:10:40.817568	\N	\N	2026-06-16 12:10:40.78875
pg-collab-observer-1781626239	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:40.904609	2026-06-16 12:10:40.904609	\N	\N	\N
pg-collab-lead-1781625958	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:05:59.924546	2026-06-16 12:05:59.924546	\N	\N	\N
pg-collab-member-1781625958	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:05:59.927442	2026-06-16 12:05:59.927442	\N	\N	\N
pg-collab-observer-1781625958	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:05:59.931062	2026-06-16 12:05:59.931062	\N	\N	\N
skill-token-agent-pgsktok	PG Skill Token Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:37.243761	2026-06-16 12:10:42.430153	\N	\N	2026-06-16 12:10:42.430153
pg-spec-agent-1781626239	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:42.507048	2026-06-16 12:10:42.507048	\N	\N	\N
pg-ws-agent-1781626239	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:42.610941	2026-06-16 12:10:42.634109	\N	\N	2026-06-16 12:10:42.634109
pg-ws-agent2-1781626239	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:10:42.638041	2026-06-16 12:10:42.638041	\N	\N	\N
pg-collab-lead-1781626104	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:25.908601	2026-06-16 12:08:25.908601	\N	\N	\N
pg-collab-member-1781626104	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:25.912189	2026-06-16 12:08:25.912189	\N	\N	\N
pg-collab-observer-1781626104	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:25.915218	2026-06-16 12:08:25.915218	\N	\N	\N
pg-collab-lead-1781625758	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:02:39.913565	2026-06-16 12:02:39.913565	\N	\N	\N
pg-collab-member-1781625758	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:02:39.916723	2026-06-16 12:02:39.916723	\N	\N	\N
pg-collab-observer-1781625758	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:02:39.919703	2026-06-16 12:02:39.919703	\N	\N	\N
pg-spec-agent-1781625958	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:06:01.597211	2026-06-16 12:06:01.597211	\N	\N	\N
pg-ws-agent-1781625958	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:06:01.703199	2026-06-16 12:06:01.726448	\N	\N	2026-06-16 12:06:01.726448
pg-ws-agent2-1781625958	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:06:01.73012	2026-06-16 12:06:01.73012	\N	\N	\N
pg-spec-agent-1781626045	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:28.490514	2026-06-16 12:07:28.490514	\N	\N	\N
audit-agent-pgaud	PG Audit Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:00:35.893932	2026-06-16 12:04:16.626574	\N	\N	2026-06-16 12:04:16.626574
pg-ws-agent-1781626045	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:28.590117	2026-06-16 12:07:28.611382	\N	\N	2026-06-16 12:07:28.611382
pg-ws-agent2-1781626045	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:28.615147	2026-06-16 12:07:28.615147	\N	\N	\N
pg-collab-lead-1781626077	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:58.972758	2026-06-16 12:07:58.972758	\N	\N	\N
pg-collab-member-1781626077	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:58.976029	2026-06-16 12:07:58.976029	\N	\N	\N
pg-collab-observer-1781626077	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:07:58.97941	2026-06-16 12:07:58.97941	\N	\N	\N
pg-spec-agent-1781626077	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:00.605972	2026-06-16 12:08:00.605972	\N	\N	\N
pg-ws-agent-1781626077	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:00.709498	2026-06-16 12:08:00.734265	\N	\N	2026-06-16 12:08:00.734265
pg-ws-agent2-1781626077	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:00.738631	2026-06-16 12:08:00.738631	\N	\N	\N
pg-collab-lead-1781626115	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:36.946871	2026-06-16 12:08:36.946871	\N	\N	\N
pg-collab-member-1781626115	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:36.951316	2026-06-16 12:08:36.951316	\N	\N	\N
pg-collab-observer-1781626115	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:36.954521	2026-06-16 12:08:36.954521	\N	\N	\N
pg-spec-agent-1781626104	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:27.52342	2026-06-16 12:08:27.52342	\N	\N	\N
pg-ws-agent-1781626104	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:27.623844	2026-06-16 12:08:27.649469	\N	\N	2026-06-16 12:08:27.649469
pg-ws-agent2-1781626104	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:27.652253	2026-06-16 12:08:27.652253	\N	\N	\N
pg-collab-lead-1781626161	Collab Lead	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:09:22.910166	2026-06-16 12:09:22.910166	\N	\N	\N
pg-collab-member-1781626161	Collab Member	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:09:22.913416	2026-06-16 12:09:22.913416	\N	\N	\N
pg-spec-agent-1781626115	PG Spec Test Agent	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:38.555688	2026-06-16 12:08:38.555688	\N	\N	\N
pg-collab-observer-1781626161	Collab Observer	test	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:09:22.918138	2026-06-16 12:09:22.918138	\N	\N	\N
pg-ws-agent-1781626115	PG WS Test Agent	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:38.659041	2026-06-16 12:08:38.681032	\N	\N	2026-06-16 12:08:38.681032
pg-ws-agent2-1781626115	PG WS Test Agent 2	\N	\N	\N	ACTIVE	\N	WORKER	\N	\N	\N	2026-06-16 12:08:38.683942	2026-06-16 12:08:38.683942	\N	\N	\N
\.


--
-- Data for Name: agent_session_active; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agent_session_active (session_id, agent_id, owner_user_id, workspace_id, predecessor_session_id, branch_id, is_active, context, last_active_at, created_at) FROM stdin;
2	pg-ws-agent-1781623468	admin	10	\N	\N	t	\N	\N	2026-06-16 11:24:31.201544
3	pg-ws-agent2-1781623468	admin	10	2	1	t	{"reason": "pg test handoff"}	\N	2026-06-16 11:24:31.222242
4	pg-ws-agent-1781623917	admin	15	\N	\N	t	\N	\N	2026-06-16 11:32:00.248277
5	pg-ws-agent2-1781623917	admin	15	4	2	t	{"reason": "pg test handoff"}	\N	2026-06-16 11:32:00.264721
7	pg-ws-agent-1781624171	admin	21	\N	\N	t	\N	\N	2026-06-16 11:36:14.324547
8	pg-ws-agent2-1781624171	admin	21	7	3	t	{"reason": "pg test handoff"}	\N	2026-06-16 11:36:14.34368
9	pg-ws-agent-1781624271	admin	26	\N	\N	t	\N	\N	2026-06-16 11:37:54.345329
10	pg-ws-agent2-1781624271	admin	26	9	4	t	{"reason": "pg test handoff"}	\N	2026-06-16 11:37:54.363203
11	pg-ws-agent-1781624408	admin	31	\N	\N	t	\N	\N	2026-06-16 11:40:11.261753
12	pg-ws-agent2-1781624408	admin	31	11	5	t	{"reason": "pg test handoff"}	\N	2026-06-16 11:40:11.278684
13	pg-ws-agent-1781624636	admin	36	\N	\N	t	\N	\N	2026-06-16 11:43:59.370986
14	pg-ws-agent2-1781624636	admin	36	13	6	t	{"reason": "pg test handoff"}	\N	2026-06-16 11:43:59.388255
15	pg-ws-agent-1781624801	admin	41	\N	\N	t	\N	\N	2026-06-16 11:46:44.323309
16	pg-ws-agent2-1781624801	admin	41	15	7	t	{"reason": "pg test handoff"}	\N	2026-06-16 11:46:44.341784
17	pg-ws-agent-1781625015	admin	46	\N	\N	t	\N	\N	2026-06-16 11:50:18.37197
18	pg-ws-agent-1781625634	admin	51	\N	\N	t	\N	\N	2026-06-16 12:00:37.584266
19	pg-ws-agent2-1781625634	admin	51	18	8	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:00:37.605354
20	pg-ws-agent-1781625758	admin	56	\N	\N	t	\N	\N	2026-06-16 12:02:41.576486
21	pg-ws-agent2-1781625758	admin	56	20	9	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:02:41.595604
22	pg-ws-agent-1781625958	admin	62	\N	\N	t	\N	\N	2026-06-16 12:06:01.734097
23	pg-ws-agent2-1781625958	admin	62	22	10	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:06:01.7513
24	pg-ws-agent-1781626045	admin	68	\N	\N	t	\N	\N	2026-06-16 12:07:28.617929
25	pg-ws-agent2-1781626045	admin	68	24	11	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:07:28.635289
26	pg-ws-agent-1781626077	admin	74	\N	\N	t	\N	\N	2026-06-16 12:08:00.742221
27	pg-ws-agent2-1781626077	admin	74	26	12	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:08:00.760512
28	pg-ws-agent-1781626104	admin	81	\N	\N	t	\N	\N	2026-06-16 12:08:27.655048
29	pg-ws-agent2-1781626104	admin	81	28	13	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:08:27.673771
30	pg-ws-agent-1781626115	admin	87	\N	\N	t	\N	\N	2026-06-16 12:08:38.687592
31	pg-ws-agent2-1781626115	admin	87	30	14	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:08:38.705058
32	pg-ws-agent-1781626161	admin	93	\N	\N	t	\N	\N	2026-06-16 12:09:24.643896
33	pg-ws-agent2-1781626161	admin	93	32	15	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:09:24.661825
34	pg-ws-agent-1781626199	admin	99	\N	\N	t	\N	\N	2026-06-16 12:10:02.672685
35	pg-ws-agent2-1781626199	admin	99	34	16	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:10:02.690728
36	pg-ws-agent-1781626239	admin	105	\N	\N	t	\N	\N	2026-06-16 12:10:42.641011
37	pg-ws-agent2-1781626239	admin	105	36	17	t	{"reason": "pg test handoff"}	\N	2026-06-16 12:10:42.658782
\.


--
-- Data for Name: agent_session_inactive; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agent_session_inactive (session_id, agent_id, owner_user_id, workspace_id, predecessor_session_id, branch_id, is_active, context, last_active_at, created_at) FROM stdin;
\.


--
-- Data for Name: branch_merge_log; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.branch_merge_log (log_id, source_branch_id, target_branch_id, merge_status, conflicts_json, merged_at, merged_by_agent) FROM stdin;
\.


--
-- Data for Name: collab_group_members; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collab_group_members (member_id, group_id, agent_id, role, personal_workspace_id, branch_id, joined_at, status) FROM stdin;
1	1	pg-collab-lead-1781623308	LEAD	2	\N	2026-06-16 11:21:50.073149	ACTIVE
2	1	pg-collab-member-1781623308	CONTRIBUTOR	3	\N	2026-06-16 11:21:50.078851	ACTIVE
3	1	pg-collab-observer-1781623308	OBSERVER	\N	\N	2026-06-16 11:21:50.081264	LEFT
4	2	pg-collab-lead-1781623468	LEAD	7	\N	2026-06-16 11:24:29.979019	ACTIVE
5	2	pg-collab-member-1781623468	CONTRIBUTOR	8	\N	2026-06-16 11:24:29.986274	ACTIVE
6	2	pg-collab-observer-1781623468	OBSERVER	\N	\N	2026-06-16 11:24:29.990731	LEFT
7	3	pg-collab-lead-1781623917	LEAD	12	\N	2026-06-16 11:31:58.969234	ACTIVE
8	3	pg-collab-member-1781623917	CONTRIBUTOR	13	\N	2026-06-16 11:31:58.976582	ACTIVE
9	3	pg-collab-observer-1781623917	OBSERVER	\N	\N	2026-06-16 11:31:58.980394	LEFT
10	4	pg-collab-lead-1781624171	LEAD	18	\N	2026-06-16 11:36:12.994533	ACTIVE
11	4	pg-collab-member-1781624171	CONTRIBUTOR	19	\N	2026-06-16 11:36:13.000596	ACTIVE
12	4	pg-collab-observer-1781624171	OBSERVER	\N	\N	2026-06-16 11:36:13.003597	LEFT
13	5	pg-collab-lead-1781624271	LEAD	23	\N	2026-06-16 11:37:52.99558	ACTIVE
14	5	pg-collab-member-1781624271	CONTRIBUTOR	24	\N	2026-06-16 11:37:53.002873	ACTIVE
15	5	pg-collab-observer-1781624271	OBSERVER	\N	\N	2026-06-16 11:37:53.025899	LEFT
16	6	pg-collab-lead-1781624408	LEAD	28	\N	2026-06-16 11:40:09.988275	ACTIVE
17	6	pg-collab-member-1781624408	CONTRIBUTOR	29	\N	2026-06-16 11:40:09.994482	ACTIVE
18	6	pg-collab-observer-1781624408	OBSERVER	\N	\N	2026-06-16 11:40:09.998775	LEFT
19	7	pg-collab-lead-1781624636	LEAD	33	\N	2026-06-16 11:43:57.950131	ACTIVE
20	7	pg-collab-member-1781624636	CONTRIBUTOR	34	\N	2026-06-16 11:43:57.957387	ACTIVE
21	7	pg-collab-observer-1781624636	OBSERVER	\N	\N	2026-06-16 11:43:57.960072	LEFT
22	8	pg-collab-lead-1781624801	LEAD	38	\N	2026-06-16 11:46:42.91565	ACTIVE
23	8	pg-collab-member-1781624801	CONTRIBUTOR	39	\N	2026-06-16 11:46:42.921622	ACTIVE
24	8	pg-collab-observer-1781624801	OBSERVER	\N	\N	2026-06-16 11:46:42.924905	LEFT
25	9	pg-collab-lead-1781625015	LEAD	43	\N	2026-06-16 11:50:16.961707	ACTIVE
26	9	pg-collab-member-1781625015	CONTRIBUTOR	44	\N	2026-06-16 11:50:16.971587	ACTIVE
27	9	pg-collab-observer-1781625015	OBSERVER	\N	\N	2026-06-16 11:50:16.975215	LEFT
28	10	pg-collab-lead-1781625634	LEAD	48	\N	2026-06-16 12:00:35.974337	ACTIVE
29	10	pg-collab-member-1781625634	CONTRIBUTOR	49	\N	2026-06-16 12:00:35.981724	ACTIVE
30	10	pg-collab-observer-1781625634	OBSERVER	\N	\N	2026-06-16 12:00:35.984699	LEFT
31	11	pg-collab-lead-1781625758	LEAD	53	\N	2026-06-16 12:02:39.949904	ACTIVE
32	11	pg-collab-member-1781625758	CONTRIBUTOR	54	\N	2026-06-16 12:02:39.956587	ACTIVE
33	11	pg-collab-observer-1781625758	OBSERVER	\N	\N	2026-06-16 12:02:39.959824	LEFT
34	12	pg-collab-lead-1781625958	LEAD	59	\N	2026-06-16 12:05:59.962719	ACTIVE
35	12	pg-collab-member-1781625958	CONTRIBUTOR	60	\N	2026-06-16 12:05:59.969256	ACTIVE
36	12	pg-collab-observer-1781625958	OBSERVER	\N	\N	2026-06-16 12:05:59.972328	LEFT
37	13	pg-collab-lead-1781626045	LEAD	65	\N	2026-06-16 12:07:26.940992	ACTIVE
38	13	pg-collab-member-1781626045	CONTRIBUTOR	66	\N	2026-06-16 12:07:26.946928	ACTIVE
39	13	pg-collab-observer-1781626045	OBSERVER	\N	\N	2026-06-16 12:07:26.949874	LEFT
40	14	pg-collab-lead-1781626077	LEAD	71	\N	2026-06-16 12:07:59.013266	ACTIVE
41	14	pg-collab-member-1781626077	CONTRIBUTOR	72	\N	2026-06-16 12:07:59.022004	ACTIVE
42	14	pg-collab-observer-1781626077	OBSERVER	\N	\N	2026-06-16 12:07:59.025427	LEFT
43	15	pg-collab-lead-1781626104	LEAD	78	\N	2026-06-16 12:08:25.94859	ACTIVE
44	15	pg-collab-member-1781626104	CONTRIBUTOR	79	\N	2026-06-16 12:08:25.957237	ACTIVE
45	15	pg-collab-observer-1781626104	OBSERVER	\N	\N	2026-06-16 12:08:25.960339	LEFT
46	16	pg-collab-lead-1781626115	LEAD	84	\N	2026-06-16 12:08:36.988022	ACTIVE
47	16	pg-collab-member-1781626115	CONTRIBUTOR	85	\N	2026-06-16 12:08:36.994744	ACTIVE
48	16	pg-collab-observer-1781626115	OBSERVER	\N	\N	2026-06-16 12:08:36.997862	LEFT
49	17	pg-collab-lead-1781626161	LEAD	90	\N	2026-06-16 12:09:22.950793	ACTIVE
50	17	pg-collab-member-1781626161	CONTRIBUTOR	91	\N	2026-06-16 12:09:22.957532	ACTIVE
51	17	pg-collab-observer-1781626161	OBSERVER	\N	\N	2026-06-16 12:09:22.960654	LEFT
52	18	pg-collab-lead-1781626199	LEAD	96	\N	2026-06-16 12:10:00.946778	ACTIVE
53	18	pg-collab-member-1781626199	CONTRIBUTOR	97	\N	2026-06-16 12:10:00.953372	ACTIVE
54	18	pg-collab-observer-1781626199	OBSERVER	\N	\N	2026-06-16 12:10:00.956417	LEFT
55	19	pg-collab-lead-1781626239	LEAD	102	\N	2026-06-16 12:10:40.93453	ACTIVE
56	19	pg-collab-member-1781626239	CONTRIBUTOR	103	\N	2026-06-16 12:10:40.940525	ACTIVE
57	19	pg-collab-observer-1781626239	OBSERVER	\N	\N	2026-06-16 12:10:40.94359	LEFT
\.


--
-- Data for Name: collab_groups; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collab_groups (group_id, group_name, group_type, description, workspace_id, coordinator_agent_id, sharing_policy, branch_id, spec_id, status, metadata, created_at, updated_at) FROM stdin;
1	PG Test Collab Group 1781623308	PROJECT	Updated PG collab description	1	pg-collab-lead-1781623308	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:21:50.052387	2026-06-16 11:21:50.099454
2	PG Test Collab Group 1781623468	PROJECT	Updated PG collab description	6	pg-collab-lead-1781623468	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:24:29.957821	2026-06-16 11:24:30.010026
3	PG Test Collab Group 1781623917	PROJECT	Updated PG collab description	11	pg-collab-lead-1781623917	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:31:58.94602	2026-06-16 11:31:59.005406
4	PG Test Collab Group 1781624171	PROJECT	Updated PG collab description	17	pg-collab-lead-1781624171	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:36:12.969356	2026-06-16 11:36:13.028372
5	PG Test Collab Group 1781624271	PROJECT	Updated PG collab description	22	pg-collab-lead-1781624271	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:37:52.966225	2026-06-16 11:37:53.078242
6	PG Test Collab Group 1781624408	PROJECT	Updated PG collab description	27	pg-collab-lead-1781624408	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:40:09.957583	2026-06-16 11:40:10.023867
7	PG Test Collab Group 1781624636	PROJECT	Updated PG collab description	32	pg-collab-lead-1781624636	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:43:57.926052	2026-06-16 11:43:57.983686
8	PG Test Collab Group 1781624801	PROJECT	Updated PG collab description	37	pg-collab-lead-1781624801	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:46:42.891334	2026-06-16 11:46:42.950959
9	PG Test Collab Group 1781625015	PROJECT	Updated PG collab description	42	pg-collab-lead-1781625015	OPEN	\N	\N	ACTIVE	\N	2026-06-16 11:50:16.936589	2026-06-16 11:50:17.000823
10	PG Test Collab Group 1781625634	PROJECT	Updated PG collab description	47	pg-collab-lead-1781625634	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:00:35.949469	2026-06-16 12:00:36.009185
17	PG Test Collab Group 1781626161	PROJECT	Updated PG collab description	89	pg-collab-lead-1781626161	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:09:22.924327	2026-06-16 12:09:22.985047
11	PG Test Collab Group 1781625758	PROJECT	Updated PG collab description	52	pg-collab-lead-1781625758	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:02:39.926295	2026-06-16 12:02:39.982052
12	PG Test Collab Group 1781625958	PROJECT	Updated PG collab description	58	pg-collab-lead-1781625958	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:05:59.937359	2026-06-16 12:05:59.998378
13	PG Test Collab Group 1781626045	PROJECT	Updated PG collab description	64	pg-collab-lead-1781626045	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:07:26.916281	2026-06-16 12:07:26.972853
14	PG Test Collab Group 1781626077	PROJECT	Updated PG collab description	70	pg-collab-lead-1781626077	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:07:58.986636	2026-06-16 12:07:59.051274
18	PG Test Collab Group 1781626199	PROJECT	Updated PG collab description	95	pg-collab-lead-1781626199	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:10:00.921884	2026-06-16 12:10:00.980829
15	PG Test Collab Group 1781626104	PROJECT	Updated PG collab description	77	pg-collab-lead-1781626104	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:08:25.922369	2026-06-16 12:08:25.983468
16	PG Test Collab Group 1781626115	PROJECT	Updated PG collab description	83	pg-collab-lead-1781626115	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:08:36.961302	2026-06-16 12:08:37.026176
19	PG Test Collab Group 1781626239	PROJECT	Updated PG collab description	101	pg-collab-lead-1781626239	OPEN	\N	\N	ACTIVE	\N	2026-06-16 12:10:40.910792	2026-06-16 12:10:40.967751
\.


--
-- Data for Name: compliance_log; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.compliance_log (log_id, event_type, severity, actor_id, actor_type, target_type, target_id, description, metadata, policy_violation, created_at) FROM stdin;
\.


--
-- Data for Name: context_branches; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.context_branches (branch_id, workspace_id, parent_branch_id, branch_name, branch_type, status, source_context_id, agent_id, created_at, merged_at, abandoned_at, description, is_lesson, lesson_tags) FROM stdin;
1	10	\N	handoff-to-pg-ws-agent2-1781623468	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781623468	2026-06-16 11:24:31.216361	\N	\N	Handoff from pg-ws-agent-1781623468 to pg-ws-agent2-1781623468	f	\N
2	15	\N	handoff-to-pg-ws-agent2-1781623917	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781623917	2026-06-16 11:32:00.260606	\N	\N	Handoff from pg-ws-agent-1781623917 to pg-ws-agent2-1781623917	f	\N
3	21	\N	handoff-to-pg-ws-agent2-1781624171	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781624171	2026-06-16 11:36:14.338087	\N	\N	Handoff from pg-ws-agent-1781624171 to pg-ws-agent2-1781624171	f	\N
4	26	\N	handoff-to-pg-ws-agent2-1781624271	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781624271	2026-06-16 11:37:54.358698	\N	\N	Handoff from pg-ws-agent-1781624271 to pg-ws-agent2-1781624271	f	\N
5	31	\N	handoff-to-pg-ws-agent2-1781624408	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781624408	2026-06-16 11:40:11.273901	\N	\N	Handoff from pg-ws-agent-1781624408 to pg-ws-agent2-1781624408	f	\N
6	36	\N	handoff-to-pg-ws-agent2-1781624636	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781624636	2026-06-16 11:43:59.383712	\N	\N	Handoff from pg-ws-agent-1781624636 to pg-ws-agent2-1781624636	f	\N
7	41	\N	handoff-to-pg-ws-agent2-1781624801	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781624801	2026-06-16 11:46:44.337666	\N	\N	Handoff from pg-ws-agent-1781624801 to pg-ws-agent2-1781624801	f	\N
8	51	\N	handoff-to-pg-ws-agent2-1781625634	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781625634	2026-06-16 12:00:37.600562	\N	\N	Handoff from pg-ws-agent-1781625634 to pg-ws-agent2-1781625634	f	\N
9	56	\N	handoff-to-pg-ws-agent2-1781625758	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781625758	2026-06-16 12:02:41.59066	\N	\N	Handoff from pg-ws-agent-1781625758 to pg-ws-agent2-1781625758	f	\N
10	62	\N	handoff-to-pg-ws-agent2-1781625958	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781625958	2026-06-16 12:06:01.747446	\N	\N	Handoff from pg-ws-agent-1781625958 to pg-ws-agent2-1781625958	f	\N
11	68	\N	handoff-to-pg-ws-agent2-1781626045	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781626045	2026-06-16 12:07:28.631749	\N	\N	Handoff from pg-ws-agent-1781626045 to pg-ws-agent2-1781626045	f	\N
12	74	\N	handoff-to-pg-ws-agent2-1781626077	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781626077	2026-06-16 12:08:00.756877	\N	\N	Handoff from pg-ws-agent-1781626077 to pg-ws-agent2-1781626077	f	\N
13	81	\N	handoff-to-pg-ws-agent2-1781626104	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781626104	2026-06-16 12:08:27.668491	\N	\N	Handoff from pg-ws-agent-1781626104 to pg-ws-agent2-1781626104	f	\N
14	87	\N	handoff-to-pg-ws-agent2-1781626115	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781626115	2026-06-16 12:08:38.70067	\N	\N	Handoff from pg-ws-agent-1781626115 to pg-ws-agent2-1781626115	f	\N
15	93	\N	handoff-to-pg-ws-agent2-1781626161	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781626161	2026-06-16 12:09:24.658024	\N	\N	Handoff from pg-ws-agent-1781626161 to pg-ws-agent2-1781626161	f	\N
16	99	\N	handoff-to-pg-ws-agent2-1781626199	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781626199	2026-06-16 12:10:02.686435	\N	\N	Handoff from pg-ws-agent-1781626199 to pg-ws-agent2-1781626199	f	\N
17	105	\N	handoff-to-pg-ws-agent2-1781626239	HANDOFF	ACTIVE	\N	pg-ws-agent2-1781626239	2026-06-16 12:10:42.654612	\N	\N	Handoff from pg-ws-agent-1781626239 to pg-ws-agent2-1781626239	f	\N
\.


--
-- Data for Name: entities_default; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_default (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
\.


--
-- Data for Name: entities_experience; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_experience (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
\.


--
-- Data for Name: entities_harness_template; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_harness_template (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
9	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:24:30.960977	2026-06-16 11:24:30.972126	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
14	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:31:59.955285	2026-06-16 11:31:59.967556	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
17	HARNESS_TEMPLATE	PG Test Harness 1781624100	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:35:00.651687	2026-06-16 11:35:00.651687	\N	'1781624100':4A 'analyz':17C 'domain':16C 'har':3A,8B 'input':18C 'pg':1A,6B 'role':13C 'special':14C 'templat':9B 'test':2A,7B
21	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:36:14.026957	2026-06-16 11:36:14.038659	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
23	HARNESS_TEMPLATE	PG Test Harness 1781624181	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:36:21.62818	2026-06-16 11:36:21.62818	\N	'1781624181':4A 'analyz':17C 'domain':16C 'har':3A,8B 'input':18C 'pg':1A,6B 'role':13C 'special':14C 'templat':9B 'test':2A,7B
28	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:37:54.053696	2026-06-16 11:37:54.065065	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
30	HARNESS_TEMPLATE	test harness	\N	test	test	ACTIVE	5.0	\N	\N	SHARED	\N	\N	0	2026-06-16 11:38:37.542701	2026-06-16 11:38:37.542701	\N	'har':2A 'test':1A,3B
36	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:40:10.976981	2026-06-16 11:40:10.988713	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
41	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:43:58.927127	2026-06-16 11:43:58.93794	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
56	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:46:43.923334	2026-06-16 11:46:43.935503	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
63	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:50:17.955732	2026-06-16 11:50:17.967481	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
70	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:00:36.98193	2026-06-16 12:00:36.994347	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
77	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:02:40.923849	2026-06-16 12:02:40.936339	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
85	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:06:00.944968	2026-06-16 12:06:00.955834	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
93	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:07:27.917847	2026-06-16 12:07:27.930208	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
101	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:08:00.008996	2026-06-16 12:08:00.021383	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
110	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:08:26.932507	2026-06-16 12:08:26.945868	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
118	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:08:37.976556	2026-06-16 12:08:37.989577	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
126	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:09:23.922216	2026-06-16 12:09:23.935417	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
134	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:10:01.932714	2026-06-16 12:10:01.944615	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
142	HARNESS_TEMPLATE	Updated PG Harness	You are a {role} specializing in {domain}. Analyze: {input}	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:10:41.915238	2026-06-16 12:10:41.926461	\N	'analyz':16C 'domain':15C 'har':3A,7B 'input':17C 'pg':2A,5B 'role':12C 'special':13C 'templat':8B 'test':6B 'updat':1A
\.


--
-- Data for Name: entities_knowledge; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_knowledge (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
\.


--
-- Data for Name: entities_memory; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_memory (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
6	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:24:30.016679	2026-06-16 11:24:30.016679	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
7	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:24:30.889216	2026-06-16 11:24:30.889216	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
8	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:24:30.892839	2026-06-16 11:24:30.892839	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
11	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:31:59.014942	2026-06-16 11:31:59.014942	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
12	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:31:59.877635	2026-06-16 11:31:59.877635	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
13	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:31:59.88094	2026-06-16 11:31:59.88094	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
16	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:34:03.652174	2026-06-16 11:34:03.652174	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
18	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:36:13.035604	2026-06-16 11:36:13.035604	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
19	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:36:13.951626	2026-06-16 11:36:13.951626	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
20	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:36:13.9555	2026-06-16 11:36:13.9555	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
24	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	SHARED	\N	\N	0	2026-06-16 11:37:10.644219	2026-06-16 11:37:10.644219	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
25	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:37:53.087122	2026-06-16 11:37:53.087122	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
26	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:37:53.982896	2026-06-16 11:37:53.982896	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
27	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:37:53.987192	2026-06-16 11:37:53.987192	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
31	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:39:50.62022	2026-06-16 11:39:50.62022	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
32	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:39:50.627469	2026-06-16 11:39:50.627469	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
33	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:40:10.033099	2026-06-16 11:40:10.033099	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
34	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:40:10.9099	2026-06-16 11:40:10.9099	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
35	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:40:10.913149	2026-06-16 11:40:10.913149	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
38	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:43:57.992829	2026-06-16 11:43:57.992829	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
39	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:43:58.859477	2026-06-16 11:43:58.859477	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
40	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:43:58.863089	2026-06-16 11:43:58.863089	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
53	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:46:42.958241	2026-06-16 11:46:42.958241	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
54	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:46:43.846308	2026-06-16 11:46:43.846308	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
55	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:46:43.850005	2026-06-16 11:46:43.850005	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
60	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 11:50:17.008593	2026-06-16 11:50:17.008593	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
61	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:50:17.884691	2026-06-16 11:50:17.884691	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
62	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 11:50:17.888676	2026-06-16 11:50:17.888676	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
67	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:00:36.017838	2026-06-16 12:00:36.017838	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
68	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:00:36.90737	2026-06-16 12:00:36.90737	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
69	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:00:36.910915	2026-06-16 12:00:36.910915	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
74	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:02:39.990793	2026-06-16 12:02:39.990793	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
75	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:02:40.859651	2026-06-16 12:02:40.859651	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
76	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:02:40.862826	2026-06-16 12:02:40.862826	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
82	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:06:00.006288	2026-06-16 12:06:00.006288	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
83	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:06:00.87498	2026-06-16 12:06:00.87498	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
84	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:06:00.878641	2026-06-16 12:06:00.878641	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
90	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:07:26.981477	2026-06-16 12:07:26.981477	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
91	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:07:27.84257	2026-06-16 12:07:27.84257	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
92	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:07:27.846656	2026-06-16 12:07:27.846656	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
98	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:07:59.059558	2026-06-16 12:07:59.059558	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
99	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:07:59.933312	2026-06-16 12:07:59.933312	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
100	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:07:59.936389	2026-06-16 12:07:59.936389	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
107	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:08:25.990918	2026-06-16 12:08:25.990918	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
108	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:08:26.862357	2026-06-16 12:08:26.862357	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
109	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:08:26.865606	2026-06-16 12:08:26.865606	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
115	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:08:37.034721	2026-06-16 12:08:37.034721	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
116	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:08:37.911531	2026-06-16 12:08:37.911531	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
117	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:08:37.91435	2026-06-16 12:08:37.91435	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
123	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:09:22.993128	2026-06-16 12:09:22.993128	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
124	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:09:23.848962	2026-06-16 12:09:23.848962	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
125	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:09:23.852596	2026-06-16 12:09:23.852596	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
131	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:10:00.989934	2026-06-16 12:10:00.989934	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
132	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:10:01.858734	2026-06-16 12:10:01.858734	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
133	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:10:01.862119	2026-06-16 12:10:01.862119	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
139	MEMORY	Shared Memory PG	content for sharing	\N	test-collab-pg	ACTIVE	5.0	\N	\N	PRIVATE	\N	\N	0	2026-06-16 12:10:40.977549	2026-06-16 12:10:40.977549	\N	'content':4C 'memori':2A 'pg':3A 'share':1A,6C
140	MEMORY	Graph Edge Test A	content a	\N	graph-test-pg	ACTIVE	8.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:10:41.840238	2026-06-16 12:10:41.840238	\N	'content':4C 'edg':2A 'graph':1A 'test':3A
141	MEMORY	Graph Edge Test B	content b	\N	graph-test-pg	ACTIVE	6.0	graph-tester-pg	\N	PRIVATE	\N	\N	0	2026-06-16 12:10:41.843272	2026-06-16 12:10:41.843272	\N	'b':4A,6C 'content':5C 'edg':2A 'graph':1A 'test':3A
\.


--
-- Data for Name: entities_other; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_other (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
\.


--
-- Data for Name: entities_skill; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_skill (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
\.


--
-- Data for Name: entities_spec; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_spec (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
45	SPEC	test spec	test content	\N	test	ACTIVE	5.0	\N	\N	SHARED	\N	\N	0	2026-06-16 11:44:57.527618	2026-06-16 11:44:57.527618	\N	'content':4C 'spec':2A 'test':1A,3C
46	SPEC	updated spec	test	\N	test	ACTIVE	5.0	\N	\N	SHARED	\N	\N	0	2026-06-16 11:45:26.516789	2026-06-16 11:45:26.535615	\N	'spec':2A 'test':3C 'updat':1A
48	SPEC	Derived PG Spec 1781624736	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781624736	\N	SHARED	\N	\N	0	2026-06-16 11:45:36.683578	2026-06-16 11:45:36.683578	\N	'1781624736':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
50	SPEC	Derived PG Spec 1781624754	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781624754	\N	SHARED	\N	\N	0	2026-06-16 11:45:54.709913	2026-06-16 11:45:54.709913	\N	'1781624754':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
52	SPEC	Derived PG Spec 1781624795	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781624795	\N	SHARED	\N	\N	0	2026-06-16 11:46:35.699257	2026-06-16 11:46:35.699257	\N	'1781624795':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
59	SPEC	Derived PG Spec 1781624801	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781624801	\N	SHARED	\N	\N	0	2026-06-16 11:46:44.220793	2026-06-16 11:46:44.220793	\N	'1781624801':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
66	SPEC	Derived PG Spec 1781625015	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781625015	\N	SHARED	\N	\N	0	2026-06-16 11:50:18.271694	2026-06-16 11:50:18.271694	\N	'1781625015':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
73	SPEC	Derived PG Spec 1781625634	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781625634	\N	SHARED	\N	\N	0	2026-06-16 12:00:37.478316	2026-06-16 12:00:37.478316	\N	'1781625634':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
80	SPEC	Derived PG Spec 1781625758	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781625758	\N	SHARED	\N	\N	0	2026-06-16 12:02:41.474041	2026-06-16 12:02:41.474041	\N	'1781625758':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
88	SPEC	Derived PG Spec 1781625958	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781625958	\N	SHARED	\N	\N	0	2026-06-16 12:06:01.626689	2026-06-16 12:06:01.626689	\N	'1781625958':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
96	SPEC	Derived PG Spec 1781626045	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781626045	\N	SHARED	\N	\N	0	2026-06-16 12:07:28.516851	2026-06-16 12:07:28.516851	\N	'1781626045':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
104	SPEC	Derived PG Spec 1781626077	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781626077	\N	SHARED	\N	\N	0	2026-06-16 12:08:00.635548	2026-06-16 12:08:00.635548	\N	'1781626077':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
113	SPEC	Derived PG Spec 1781626104	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781626104	\N	SHARED	\N	\N	0	2026-06-16 12:08:27.550728	2026-06-16 12:08:27.550728	\N	'1781626104':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
121	SPEC	Derived PG Spec 1781626115	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781626115	\N	SHARED	\N	\N	0	2026-06-16 12:08:38.583154	2026-06-16 12:08:38.583154	\N	'1781626115':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
129	SPEC	Derived PG Spec 1781626161	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781626161	\N	SHARED	\N	\N	0	2026-06-16 12:09:24.541265	2026-06-16 12:09:24.541265	\N	'1781626161':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
137	SPEC	Derived PG Spec 1781626199	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781626199	\N	SHARED	\N	\N	0	2026-06-16 12:10:02.563068	2026-06-16 12:10:02.563068	\N	'1781626199':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
145	SPEC	Derived PG Spec 1781626239	Process all items with low error rate	A PG test specification	test-spec	ACTIVE	8.0	pg-spec-agent-1781626239	\N	SHARED	\N	\N	0	2026-06-16 12:10:42.536885	2026-06-16 12:10:42.536885	\N	'1781626239':4A 'deriv':1A 'error':14C 'item':11C 'low':13C 'pg':2A,6B 'process':9C 'rate':15C 'spec':3A 'specif':8B 'test':7B
\.


--
-- Data for Name: entities_task_output; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entities_task_output (entity_id, entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, branch_id, retrieval_count, created_at, updated_at, expires_at, search_vector) FROM stdin;
10	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:24:30.98268	2026-06-16 11:24:30.98268	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
15	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:31:59.981543	2026-06-16 11:31:59.981543	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
22	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:36:14.055794	2026-06-16 11:36:14.055794	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
29	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:37:54.078193	2026-06-16 11:37:54.078193	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
37	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:40:11.001587	2026-06-16 11:40:11.001587	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
42	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:43:58.953036	2026-06-16 11:43:58.953036	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
57	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:46:43.949639	2026-06-16 11:46:43.949639	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
64	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 11:50:17.9825	2026-06-16 11:50:17.9825	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
71	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:00:37.008613	2026-06-16 12:00:37.008613	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
78	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:02:40.950351	2026-06-16 12:02:40.950351	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
86	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:06:00.970613	2026-06-16 12:06:00.970613	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
94	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:07:27.94481	2026-06-16 12:07:27.94481	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
102	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:08:00.038527	2026-06-16 12:08:00.038527	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
111	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:08:26.961562	2026-06-16 12:08:26.961562	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
119	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:08:38.005517	2026-06-16 12:08:38.005517	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
127	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:09:23.950435	2026-06-16 12:09:23.950435	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
135	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:10:01.961218	2026-06-16 12:10:01.961218	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
143	TASK_OUTPUT	Instance of Updated PG Harness	You are a Engineer specializing in testing. Analyze: sample PG data	A PG test harness template	test-harness-pg	ACTIVE	7.0	test-agent-pg	test-agent-pg	SHARED	\N	\N	0	2026-06-16 12:10:41.942465	2026-06-16 12:10:41.942465	\N	'analyz':18C 'data':21C 'engin':14C 'har':5A,9B 'instanc':1A 'pg':4A,7B,20C 'sampl':19C 'special':15C 'templat':10B 'test':8B,17C 'updat':3A
\.


--
-- Data for Name: entity_access_audit; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entity_access_audit (audit_id, entity_id, entity_type, accessor_id, accessor_type, access_type, access_result, access_context, ip_address, user_agent, accessed_at) FROM stdin;
\.


--
-- Data for Name: entity_access_log_202605; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entity_access_log_202605 (log_id, entity_id, entity_type, agent_id, access_type, session_id, context, access_time) FROM stdin;
\.


--
-- Data for Name: entity_access_log_202606; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entity_access_log_202606 (log_id, entity_id, entity_type, agent_id, access_type, session_id, context, access_time) FROM stdin;
\.


--
-- Data for Name: entity_access_log_max; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entity_access_log_max (log_id, entity_id, entity_type, agent_id, access_type, session_id, context, access_time) FROM stdin;
\.


--
-- Data for Name: entity_edges; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entity_edges (edge_id, source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at) FROM stdin;
2	7	MEMORY	8	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:24:30.933601
3	10	TASK_OUTPUT	9	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:24:30.988084
5	12	MEMORY	13	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:31:59.921577
6	15	TASK_OUTPUT	14	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:31:59.985085
8	19	MEMORY	20	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:36:13.994611
9	22	TASK_OUTPUT	21	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:36:14.059607
11	26	MEMORY	27	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:37:54.022531
12	29	TASK_OUTPUT	28	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:37:54.082451
14	31	MEMORY	32	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:39:50.666913
16	34	MEMORY	35	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:40:10.946413
17	37	TASK_OUTPUT	36	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:40:11.004659
19	39	MEMORY	40	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:43:58.895123
20	42	TASK_OUTPUT	41	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:43:58.957474
21	48	SPEC	47	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 11:45:36.690658
22	50	SPEC	49	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 11:45:54.717455
23	52	SPEC	51	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 11:46:35.705959
25	54	MEMORY	55	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:46:43.887181
26	57	TASK_OUTPUT	56	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:46:43.953461
27	59	SPEC	58	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 11:46:44.227375
29	61	MEMORY	62	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 11:50:17.92239
30	64	TASK_OUTPUT	63	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 11:50:17.985621
31	66	SPEC	65	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 11:50:18.278824
33	68	MEMORY	69	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:00:36.946307
34	71	TASK_OUTPUT	70	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:00:37.013123
35	73	SPEC	72	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:00:37.484332
37	75	MEMORY	76	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:02:40.892948
38	78	TASK_OUTPUT	77	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:02:40.953102
39	80	SPEC	79	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:02:41.480649
41	83	MEMORY	84	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:06:00.912036
42	86	TASK_OUTPUT	85	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:06:00.974943
43	88	SPEC	87	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:06:01.632901
45	91	MEMORY	92	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:07:27.881989
46	94	TASK_OUTPUT	93	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:07:27.94824
47	96	SPEC	95	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:07:28.523578
49	99	MEMORY	100	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:07:59.973337
50	102	TASK_OUTPUT	101	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:08:00.042136
51	104	SPEC	103	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:08:00.641721
53	108	MEMORY	109	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:08:26.900581
54	111	TASK_OUTPUT	110	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:08:26.964689
55	113	SPEC	112	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:08:27.556792
57	116	MEMORY	117	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:08:37.943484
58	119	TASK_OUTPUT	118	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:08:38.008818
59	121	SPEC	120	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:08:38.588833
61	124	MEMORY	125	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:09:23.88652
62	127	TASK_OUTPUT	126	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:09:23.954057
63	129	SPEC	128	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:09:24.54854
65	132	MEMORY	133	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:10:01.896259
66	135	TASK_OUTPUT	134	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:10:01.964543
67	137	SPEC	136	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:10:02.569571
69	140	MEMORY	141	\N	RELATED_TO	0.7000	0.8000	\N	2026-06-16 12:10:41.879064
70	143	TASK_OUTPUT	142	\N	USES_HARNESS	1.0000	1.0000	\N	2026-06-16 12:10:41.946647
71	145	SPEC	144	\N	DERIVES_FROM	1.0000	1.0000	\N	2026-06-16 12:10:42.544558
\.


--
-- Data for Name: entity_embeddings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entity_embeddings (entity_id, entity_type, embedding, embedding_model, embedding_dim, created_at) FROM stdin;
\.


--
-- Data for Name: entity_tags; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entity_tags (entity_id, entity_type, tag_id) FROM stdin;
\.


--
-- Data for Name: harness_meta; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.harness_meta (entity_id, entity_type, template_version, input_schema, output_schema, execution_mode) FROM stdin;
9	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
14	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
17	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
21	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
23	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
28	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
30	HARNESS_TEMPLATE	1	\N	\N	SEQUENTIAL
36	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
41	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
56	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
63	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
70	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
77	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
85	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
93	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
101	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
110	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
118	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
126	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
134	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
142	HARNESS_TEMPLATE	1	{"type": "object", "required": ["role", "domain"], "properties": {"role": {"type": "string", "default": "Analyst"}, "input": {"type": "string", "default": ""}, "domain": {"type": "string", "default": "general"}}}	{"type": "object", "properties": {"result": {"type": "string"}, "confidence": {"type": "number"}}}	SEQUENTIAL
\.


--
-- Data for Name: knowledge_meta; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.knowledge_meta (entity_id, entity_type, domain, topic, difficulty, review_count, last_reviewed, next_review) FROM stdin;
\.


--
-- Data for Name: ldap_config; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.ldap_config (config_id, config_name, server_url, bind_dn, bind_password, search_base, search_filter, group_base, group_filter, use_ssl, is_active, port, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: skill_access_token; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.skill_access_token (token_id, skill_id, token_hash, requested_by, granted_by, token_type, expires_at, consumed_at, created_at) FROM stdin;
\.


--
-- Data for Name: skill_meta; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.skill_meta (skill_id, skill_name, skill_version, description, skill_type, category, visibility, owned_by_agent, input_schema, output_schema, dependencies, resource_path, download_count, rating, status, created_at, updated_at) FROM stdin;
52	test_skill	1.0	test desc	TOOL	test	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:27:33.308564	\N
55	autocommit_test	1.0.0	\N	CUSTOM	test	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:31:21.56726	\N
56	PG Skill Test 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.06519	\N
57	PG Get Skill Test 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.070673	\N
58	PG Update Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.078052	\N
59	PG Delete Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:32:00.084362	2026-06-16 11:32:00.0909
60	PG List Skill 1 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.097629	\N
61	PG List Skill 2 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.100703	\N
62	PG Searchable Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.108469	\N
63	PG Valid Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.11555	\N
64	PG Deprecate Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.1257	\N
65	PG Resource Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/65/test.py	0	\N	ACTIVE	2026-06-16 11:32:00.149853	2026-06-16 11:32:00.163667
66	PG Discover Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:00.169119	\N
67	PG Dep Skill 1781623917	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 11:32:00.176332	\N
68	PG Skill Test 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.642748	\N
69	PG Get Skill Test 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.650389	\N
70	PG Update Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.666963	\N
107	PG Skill Test 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.081699	\N
71	PG Delete Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:32:07.681409	2026-06-16 11:32:07.687437
72	PG List Skill 1 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.696563	\N
73	PG List Skill 2 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.699748	\N
74	PG Searchable Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.707077	\N
75	PG Valid Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.716184	\N
76	PG Deprecate Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.724961	\N
77	PG Resource Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/77/test.py	0	\N	ACTIVE	2026-06-16 11:32:07.759992	2026-06-16 11:32:07.768299
78	PG Discover Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:32:07.772333	\N
79	PG Dep Skill 1781623927	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 11:32:07.780103	\N
80	key_test	1.0.0	\N	CUSTOM	\N	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:33:43.552833	\N
81	PG Skill Test 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.138919	\N
82	PG Get Skill Test 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.143011	\N
83	pg_updated_skill_1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.150261	2026-06-16 11:36:14.154491
98	PG Delete Skill 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:37:54.183148	2026-06-16 11:37:54.190366
84	PG Delete Skill 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:36:14.162424	2026-06-16 11:36:14.169235
85	PG List Skill 1 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.17601	\N
86	PG List Skill 2 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.178984	\N
87	PG Searchable Skill 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.184959	\N
88	PG Valid Skill 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.191775	\N
89	PG Deprecate Skill 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:36:14.201483	2026-06-16 11:36:14.204698
90	PG Resource Skill 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/90/test.py	0	\N	ACTIVE	2026-06-16 11:36:14.229858	2026-06-16 11:36:14.237479
91	PG Discover Skill 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:14.241131	\N
92	PG Dep Skill 1781624171	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 11:36:14.248574	\N
93	PG List Skill 1 1781624201	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:41.645654	\N
94	PG List Skill 2 1781624201	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:36:41.652108	\N
95	PG Skill Test 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.162236	\N
96	PG Get Skill Test 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.166503	\N
97	pg_updated_skill_1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.172985	2026-06-16 11:37:54.176897
99	PG List Skill 1 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.197354	\N
100	PG List Skill 2 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.200395	\N
101	PG Searchable Skill 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.20836	\N
102	PG Valid Skill 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.215505	\N
103	PG Deprecate Skill 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:37:54.225643	2026-06-16 11:37:54.228629
104	PG Resource Skill 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/104/test.py	0	\N	ACTIVE	2026-06-16 11:37:54.255287	2026-06-16 11:37:54.263005
105	PG Discover Skill 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:37:54.266724	\N
106	PG Dep Skill 1781624271	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 11:37:54.273858	\N
108	PG Get Skill Test 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.08626	\N
109	pg_updated_skill_1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.093748	2026-06-16 11:40:11.096231
111	PG List Skill 1 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.115483	\N
110	PG Delete Skill 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:40:11.101982	2026-06-16 11:40:11.10947
112	PG List Skill 2 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.118026	\N
113	PG Searchable Skill 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.125643	\N
114	PG Valid Skill 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.132391	\N
115	PG Deprecate Skill 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:40:11.142784	2026-06-16 11:40:11.146114
116	PG Resource Skill 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/116/test.py	0	\N	ACTIVE	2026-06-16 11:40:11.170205	2026-06-16 11:40:11.177449
117	PG Discover Skill 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:40:11.181082	\N
118	PG Dep Skill 1781624408	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 11:40:11.188114	\N
119	PG Skill Test 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.034954	\N
120	PG Get Skill Test 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.0396	\N
121	pg_updated_skill_1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.046353	2026-06-16 11:43:59.049293
122	PG Delete Skill 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:43:59.057409	2026-06-16 11:43:59.063186
123	PG List Skill 1 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.071448	\N
124	PG List Skill 2 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.074256	\N
125	PG Searchable Skill 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.081833	\N
126	PG Valid Skill 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.089562	\N
127	PG Deprecate Skill 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:43:59.100851	2026-06-16 11:43:59.104005
128	PG Resource Skill 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/128/test.py	0	\N	ACTIVE	2026-06-16 11:43:59.131389	2026-06-16 11:43:59.14394
129	PG Discover Skill 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:43:59.148502	\N
130	PG Dep Skill 1781624636	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 11:43:59.157491	\N
131	PG Skill Test 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.03332	\N
132	PG Get Skill Test 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.038377	\N
133	pg_updated_skill_1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.044757	2026-06-16 11:46:44.047251
134	PG Delete Skill 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:46:44.053232	2026-06-16 11:46:44.060073
135	PG List Skill 1 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.066349	\N
136	PG List Skill 2 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.06983	\N
137	PG Searchable Skill 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.077972	\N
138	PG Valid Skill 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.084982	\N
139	PG Deprecate Skill 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 11:46:44.096984	2026-06-16 11:46:44.100365
140	PG Resource Skill 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/140/test.py	0	\N	ACTIVE	2026-06-16 11:46:44.125905	2026-06-16 11:46:44.13443
141	PG Discover Skill 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 11:46:44.138617	\N
142	PG Dep Skill 1781624801	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 11:46:44.145465	\N
143	PG Skill Test 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.123103	\N
144	PG Get Skill Test 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.127956	\N
145	pg_updated_skill_1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.134257	2026-06-16 12:00:37.138279
168	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.659043	\N
146	PG Delete Skill 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:00:37.144339	2026-06-16 12:00:37.150304
147	PG List Skill 1 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.156669	\N
148	PG List Skill 2 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.159504	\N
149	PG Searchable Skill 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.166236	\N
150	PG Valid Skill 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.173787	\N
151	PG Deprecate Skill 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:00:37.18118	2026-06-16 12:00:37.185111
152	PG Resource Skill 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/152/test.py	0	\N	ACTIVE	2026-06-16 12:00:37.208232	2026-06-16 12:00:37.215601
153	PG Discover Skill 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.21866	\N
154	PG Dep Skill 1781625634	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:00:37.224706	\N
155	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.247359	\N
156	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.269736	\N
157	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.285945	\N
158	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.302024	\N
159	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.318012	\N
160	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.334365	\N
161	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.352871	\N
162	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.367672	\N
163	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:37.403753	\N
164	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:00:44.568561	\N
165	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.572	\N
166	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.606591	\N
167	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.633359	\N
169	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.688578	\N
170	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.722791	\N
171	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.741102	\N
172	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.758135	\N
173	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:01:12.799478	\N
174	PG Skill Test 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.060556	\N
175	PG Get Skill Test 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.065781	\N
176	pg_updated_skill_1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.072406	2026-06-16 12:02:41.075443
177	PG Delete Skill 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:02:41.0825	2026-06-16 12:02:41.088111
178	PG List Skill 1 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.09476	\N
179	PG List Skill 2 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.098014	\N
180	PG Searchable Skill 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.104229	\N
181	PG Valid Skill 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.110932	\N
182	PG Deprecate Skill 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:02:41.120265	2026-06-16 12:02:41.122793
183	PG Resource Skill 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/183/test.py	0	\N	ACTIVE	2026-06-16 12:02:41.146328	2026-06-16 12:02:41.152541
184	PG Discover Skill 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.156219	\N
185	PG Dep Skill 1781625758	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:02:41.164092	\N
186	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.180913	\N
187	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.210389	\N
188	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.236294	\N
189	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.259181	\N
190	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.282353	\N
191	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.3131	\N
192	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.327045	\N
193	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.341721	\N
194	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:02:41.377117	\N
195	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.582478	\N
196	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.622875	\N
197	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.660163	\N
198	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.688847	\N
199	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.720426	\N
200	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.753516	\N
201	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.772262	\N
202	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.789302	\N
203	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:03:53.83286	\N
204	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.642113	\N
205	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.679306	\N
206	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.706371	\N
207	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.732171	\N
208	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.759658	\N
209	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.798067	\N
210	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.81517	\N
211	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.83291	\N
212	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:04:16.876226	\N
213	PG Skill Test 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.114681	\N
214	PG Get Skill Test 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.120207	\N
215	pg_updated_skill_1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.127707	2026-06-16 12:06:01.130934
228	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.331744	\N
216	PG Delete Skill 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:06:01.138951	2026-06-16 12:06:01.144774
217	PG List Skill 1 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.152685	\N
218	PG List Skill 2 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.155659	\N
219	PG Searchable Skill 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.163903	\N
220	PG Valid Skill 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.172124	\N
221	PG Deprecate Skill 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:06:01.182242	2026-06-16 12:06:01.186283
222	PG Resource Skill 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/222/test.py	0	\N	ACTIVE	2026-06-16 12:06:01.210879	2026-06-16 12:06:01.217944
223	PG Discover Skill 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.221464	\N
224	PG Dep Skill 1781625958	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:06:01.229437	\N
225	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.248249	\N
226	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.27989	\N
227	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.309095	\N
229	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.36019	\N
230	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.397535	\N
231	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.416044	\N
232	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.478796	\N
233	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:06:01.522874	\N
234	PG Skill Test 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.085538	\N
235	PG Get Skill Test 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.09062	\N
236	pg_updated_skill_1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.098635	2026-06-16 12:07:28.101743
238	PG List Skill 1 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.123306	\N
237	PG Delete Skill 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:07:28.10865	2026-06-16 12:07:28.116876
239	PG List Skill 2 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.127444	\N
240	PG Searchable Skill 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.135057	\N
241	PG Valid Skill 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.142975	\N
242	PG Deprecate Skill 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:07:28.152124	2026-06-16 12:07:28.155262
243	PG Resource Skill 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/243/test.py	0	\N	ACTIVE	2026-06-16 12:07:28.180906	2026-06-16 12:07:28.188905
244	PG Discover Skill 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.193224	\N
245	PG Dep Skill 1781626045	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:07:28.199906	\N
246	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.218353	\N
247	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.246339	\N
248	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.271512	\N
249	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.293813	\N
250	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.317021	\N
251	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.345018	\N
252	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.359703	\N
253	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.374995	\N
254	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:07:28.419266	\N
255	PG Skill Test 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.189452	\N
256	PG Get Skill Test 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.19388	\N
257	pg_updated_skill_1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.20163	2026-06-16 12:08:00.205959
287	PG Dep Skill 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:08:27.220203	\N
258	PG Delete Skill 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:08:00.213771	2026-06-16 12:08:00.221457
259	PG List Skill 1 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.228532	\N
260	PG List Skill 2 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.231443	\N
261	PG Searchable Skill 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.240548	\N
262	PG Valid Skill 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.247906	\N
263	PG Deprecate Skill 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:08:00.257822	2026-06-16 12:08:00.260518
264	PG Resource Skill 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/264/test.py	0	\N	ACTIVE	2026-06-16 12:08:00.284829	2026-06-16 12:08:00.29375
265	PG Discover Skill 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.298772	\N
266	PG Dep Skill 1781626077	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:08:00.306082	\N
267	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.326577	\N
268	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.359335	\N
269	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.387753	\N
270	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.411441	\N
271	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.434243	\N
272	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.464074	\N
273	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.480956	\N
274	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.49607	\N
275	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:00.53525	\N
276	PG Skill Test 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.108684	\N
277	PG Get Skill Test 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.113214	\N
278	pg_updated_skill_1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.119341	2026-06-16 12:08:27.12228
288	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.238276	\N
279	PG Delete Skill 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:08:27.130481	2026-06-16 12:08:27.136511
280	PG List Skill 1 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.14455	\N
281	PG List Skill 2 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.147758	\N
282	PG Searchable Skill 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.154872	\N
283	PG Valid Skill 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.163296	\N
284	PG Deprecate Skill 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:08:27.173845	2026-06-16 12:08:27.176695
285	PG Resource Skill 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/285/test.py	0	\N	ACTIVE	2026-06-16 12:08:27.2011	2026-06-16 12:08:27.208858
286	PG Discover Skill 1781626104	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.21251	\N
289	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.269456	\N
290	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.295162	\N
291	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.317424	\N
292	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.343075	\N
293	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.374336	\N
294	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.390401	\N
295	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.410893	\N
296	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:27.453196	\N
297	PG Skill Test 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.147106	\N
298	PG Get Skill Test 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.151454	\N
299	pg_updated_skill_1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.158884	2026-06-16 12:08:38.162102
301	PG List Skill 1 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.182873	\N
300	PG Delete Skill 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:08:38.169442	2026-06-16 12:08:38.176411
302	PG List Skill 2 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.18681	\N
303	PG Searchable Skill 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.19392	\N
304	PG Valid Skill 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.203083	\N
305	PG Deprecate Skill 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:08:38.213307	2026-06-16 12:08:38.216349
306	PG Resource Skill 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/306/test.py	0	\N	ACTIVE	2026-06-16 12:08:38.241221	2026-06-16 12:08:38.249135
307	PG Discover Skill 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.253917	\N
308	PG Dep Skill 1781626115	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:08:38.260973	\N
309	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.279754	\N
310	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.309665	\N
311	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.336065	\N
312	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.360464	\N
313	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.386024	\N
314	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.418463	\N
315	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.437028	\N
316	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.454299	\N
317	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:08:38.491109	\N
318	PG Skill Test 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.093469	\N
319	PG Get Skill Test 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.098432	\N
320	pg_updated_skill_1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.10499	2026-06-16 12:09:24.107785
348	PG Resource Skill 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/348/test.py	0	\N	ACTIVE	2026-06-16 12:10:02.198964	2026-06-16 12:10:02.206891
321	PG Delete Skill 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:09:24.114699	2026-06-16 12:09:24.121194
322	PG List Skill 1 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.127632	\N
323	PG List Skill 2 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.130586	\N
324	PG Searchable Skill 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.138972	\N
325	PG Valid Skill 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.146579	\N
326	PG Deprecate Skill 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:09:24.15738	2026-06-16 12:09:24.160512
327	PG Resource Skill 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/327/test.py	0	\N	ACTIVE	2026-06-16 12:09:24.185137	2026-06-16 12:09:24.192527
328	PG Discover Skill 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.196199	\N
329	PG Dep Skill 1781626161	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:09:24.20485	\N
330	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.224099	\N
331	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.259476	\N
332	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.285609	\N
333	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.308326	\N
334	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.334236	\N
335	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.36743	\N
336	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.384015	\N
337	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.400637	\N
338	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:09:24.44242	\N
339	PG Skill Test 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.102839	\N
340	PG Get Skill Test 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.108117	\N
341	pg_updated_skill_1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.11517	2026-06-16 12:10:02.118488
349	PG Discover Skill 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.210606	\N
342	PG Delete Skill 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:10:02.12656	2026-06-16 12:10:02.132782
343	PG List Skill 1 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.140882	\N
344	PG List Skill 2 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.143946	\N
345	PG Searchable Skill 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.15132	\N
346	PG Valid Skill 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.159529	\N
347	PG Deprecate Skill 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:10:02.171462	2026-06-16 12:10:02.174712
350	PG Dep Skill 1781626199	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:10:02.218843	\N
351	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.238317	\N
352	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.269874	\N
353	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.297411	\N
354	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.323518	\N
355	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.351012	\N
356	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.386049	\N
357	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.403171	\N
358	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.420857	\N
359	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:02.461727	\N
360	PG Skill Test 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.085424	\N
361	PG Get Skill Test 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.089817	\N
362	pg_updated_skill_1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.096654	2026-06-16 12:10:42.100783
363	PG Delete Skill 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:10:42.107832	2026-06-16 12:10:42.114523
364	PG List Skill 1 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.122531	\N
365	PG List Skill 2 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.125871	\N
366	PG Searchable Skill 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.134357	\N
367	PG Valid Skill 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.142665	\N
368	PG Deprecate Skill 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	DEPRECATED	2026-06-16 12:10:42.15264	2026-06-16 12:10:42.156111
369	PG Resource Skill 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	skill_resources/369/test.py	0	\N	ACTIVE	2026-06-16 12:10:42.179298	2026-06-16 12:10:42.186449
370	PG Discover Skill 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.191781	\N
371	PG Dep Skill 1781626239	1.0.0	\N	CUSTOM	test-pg	SHARED	\N	\N	\N	[99999990, 99999991]	\N	0	\N	ACTIVE	2026-06-16 12:10:42.200027	\N
372	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.219552	\N
373	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.252063	\N
374	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.27904	\N
375	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.302503	\N
376	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.327423	\N
377	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.359363	\N
378	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.374606	\N
379	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.391009	\N
380	PG Token Skill pgsktok	1.0.0	\N	CUSTOM	test-pg-token	SHARED	\N	\N	\N	\N	\N	0	\N	ACTIVE	2026-06-16 12:10:42.433366	\N
\.


--
-- Data for Name: spec_meta; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.spec_meta (entity_id, entity_type, spec_version, spec_status, acceptance_criteria, spec_constraints, spec_scope, complexity, branch_id, parent_spec_id) FROM stdin;
45	SPEC	1	DRAFT	\N	\N	\N	MEDIUM	\N	\N
46	SPEC	1	DRAFT	\N	\N	\N	MEDIUM	\N	\N
48	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	47
50	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	49
52	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	51
59	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	58
66	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	65
73	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	72
80	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	79
88	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	87
96	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	95
104	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	103
113	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	112
121	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	120
129	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	128
137	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	136
145	SPEC	1	DRAFT	["All items processed", "Error rate < 1%", "Throughput > 100/s"]	{"min_accuracy": 0.99, "max_latency_ms": 500}	processing	HIGH	\N	144
\.


--
-- Data for Name: spec_plan_links; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.spec_plan_links (link_id, spec_id, plan_id, link_type, link_strength) FROM stdin;
\.


--
-- Data for Name: system_config; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.system_config (config_key, config_value, description, updated_at) FROM stdin;
admin.registration_token	AT_3e19b18c0d0f3f70f3dda4407658cd9c983c1a6a55477a83acc7664f4d84ffec	Admin token for Agent registration (encrypted)	2026-06-16 12:10:42.225687
license_type	ENTERPRISE	\N	2026-06-16 11:49:28.707937
dl_token.3b66a8f395b277a5c091734603d29e6a3d32ba6b8bdfcc4a1ed8d00710b686cb	173|skill-token-agent-pgsktok|1781625672	\N	2026-06-16 12:01:12.81881
dl_token.1eb4d5306cd020555509ed65c4d237fff89f47af9cb2cdb5e30d89e96ffd8e32	193|skill-token-agent-pgsktok|1781624561	\N	2026-06-16 12:02:41.3541
dl_token.84ebb7f05934aa3cff3e1608d92be5fdb7cf0e232b1475ae699ecaf2cbf934c0	160|skill-token-agent-pgsktok|1781625637	\N	2026-06-16 12:00:37.33833
dl_token.53c65eabc160210898721b9cdd0fc5fb3599a9a164046f591dbb897df855da4e	161|skill-token-agent-pgsktok|1781625637	\N	2026-06-16 12:00:37.356055
dl_token.b50c438dc717d55a943b8a01870adc60549144080ce06f0bf25e82ba44138862	193|skill-token-agent-pgsktok|1781624561	\N	2026-06-16 12:02:41.360359
dl_token.94eaaf1832fba4a96a07876cf14aa033248c4118776d449c47ca151b8c940e2b	162|skill-token-agent-pgsktok|1781624437	\N	2026-06-16 12:00:37.379638
dl_token.fa51b7de736dd4b1877b01cd0d68794bcbcdd5b7abdf2c5d4466b6777540f185	162|skill-token-agent-pgsktok|1781624437	\N	2026-06-16 12:00:37.385255
dl_token.4d4ac1d5ee934e7059875d07346032fe9462b7f806b9039a781fcd7704960cc5	194|skill-token-agent-pgsktok|1781625761	\N	2026-06-16 12:02:41.397599
dl_token.2ae4b8ff51c3c0efd3a1a3e3d1ce48871183b8d57a997a744b27edad10b1f4ef	337|skill-token-agent-pgsktok|1781624964	\N	2026-06-16 12:09:24.41252
dl_token.922dca440b4c3b85eb4d48c94dc3b623e9e5f2f0b2a438b151c1225fcc30f610	335|skill-token-agent-pgsktok|1781626164	\N	2026-06-16 12:09:24.371226
dl_token.796714867808c2ddc80d97e0e5936af121760532c76ef7a082d86d45db2b99f8	336|skill-token-agent-pgsktok|1781626164	\N	2026-06-16 12:09:24.388041
dl_token.658962ae4096c1885f43b828c556664357a334b12a67753c8db47c0de45e3b6b	337|skill-token-agent-pgsktok|1781624964	\N	2026-06-16 12:09:24.420285
dl_token.41e415a63731759a60cb555b8fb7d9d8562bf16bba7497087537087a04b5da51	170|skill-token-agent-pgsktok|1781625672	\N	2026-06-16 12:01:12.72638
dl_token.2537a7f37e2db5bf5774de6b6ac658bbbeaf29de65bcae49c87bb6b26efe93c1	171|skill-token-agent-pgsktok|1781625672	\N	2026-06-16 12:01:12.744348
dl_token.b4682ce82f182fcbacc5660470cdaca025a9943ba7206fdf7417203f581c7fe0	172|skill-token-agent-pgsktok|1781624472	\N	2026-06-16 12:01:12.772173
dl_token.92368c6661a90a9bc6910e28995e575457321d89fcd270d1f61f82b31ea2bcdc	172|skill-token-agent-pgsktok|1781624472	\N	2026-06-16 12:01:12.778679
dl_token.c50c96fa8bac830a06dcc8315110c306d14c8de974e18a1eae8906c6b94ce114	338|skill-token-agent-pgsktok|1781626164	\N	2026-06-16 12:09:24.461873
recovery_codes.recovery-test-agent	[{"hash": "a9642e9a2ae21891eccf028a663c16bc57a1eac38c024433ffed1cd9666f90d9", "used": true}, {"hash": "2b027f4e48fba61228aec99f9bce9d1d0ff6ff65e2f7a3f27e4f9f46dccd0aeb", "used": true}, {"hash": "014683c0939686627f424505d4d5b31f6508a4575c309264af46d7bfe17faae1", "used": true}, {"hash": "78b28552cf205dd9acfae75495ebe71d915198b94ed310f962773031e6a54eaf", "used": false}, {"hash": "cbb3d33e8185e6b472aecf23033cddfbd248f75c90e0eb867028c04127c2472e", "used": false}, {"hash": "51afd24df315fd66470bb820b58aa99041ee2d866d59261b48ee61a6f8b7a3b9", "used": false}, {"hash": "8fb93e907f7e08ae4f411f2a4884da9ca4d6321fe9ae0b4452571dc73a570136", "used": false}, {"hash": "403593cc99098d76c34161ae37d862cbdc94e7145df23b987e308a8aa74a972e", "used": false}]	Recovery codes for agent recovery-test-agent	2026-06-16 12:10:40.69685
recovery_codes.rc-return-test-agent	[{"hash": "3c6b7e2748d5aa4099f8ab0dba72f197e47c1df9f3d03a95cef380b0b541e050", "used": false}, {"hash": "e71a40828faf2836b01cfe35109d90ef7c0a9cd69e75e8e173590c0f9071dbd4", "used": false}, {"hash": "233664edca92c420793b386023c12a0209f29269de748cdbe2f272b21b4f4013", "used": false}, {"hash": "1506802726a0ef35bc5bc01bba4322498f2014fe3f720e0a4246c577fa07e80c", "used": false}, {"hash": "91837bb3f0d21a20a2fe8943f8e224d5781f5d4e55ce1f7ea0e72a47c4129713", "used": false}, {"hash": "f5038b6b3e0e915105df01be65e868e06a66ea1c958b3be1d2b41557196a85e1", "used": false}, {"hash": "6f2489bf0cf5bfd1da00df2a9792e6acf28cb214166ab8803d24590d92bc1691", "used": false}, {"hash": "32bb784c5b8e73ff634881a22a583dad0b6905985d4a7c738aa2739ad94bf705", "used": false}]	Recovery codes for agent rc-return-test-agent	2026-06-16 12:10:40.745765
dl_token.63f433ecd43c05cf13bde528fa5049e1961725d66b4722c62b3b8466675571c9	191|skill-token-agent-pgsktok|1781625761	\N	2026-06-16 12:02:41.316565
dl_token.8f0914ad544802c75d0e5b44068b62d9fb4c29daec03f8e2492da436e8fed157	192|skill-token-agent-pgsktok|1781625761	\N	2026-06-16 12:02:41.330491
dl_token.bbd8f7c51e3e5056c78fff0a21594b58cb9ddbcb4b7c7c18c353cef3219fcf8d	377|skill-token-agent-pgsktok|1781626242	\N	2026-06-16 12:10:42.362656
dl_token.f85603fdd241b8e1ed88ff008d6275fc588c545330e76ad5207b436c3031f4ee	378|skill-token-agent-pgsktok|1781626242	\N	2026-06-16 12:10:42.377742
dl_token.7824ba8166785b15b6a93c24b52dc507ef48b6ddcdcebd6c764bb20b80ff61bc	200|skill-token-agent-pgsktok|1781625833	\N	2026-06-16 12:03:53.756673
dl_token.c153b107103b4708ac1d9d45f38bbd7fa7bc6f1ac1627280d406482745aa33ba	201|skill-token-agent-pgsktok|1781625833	\N	2026-06-16 12:03:53.775433
dl_token.d17b95e6097964926ba0e03ebcbd8f185d71f28f8f0f2f6fcbb75ee53fd78e57	202|skill-token-agent-pgsktok|1781624633	\N	2026-06-16 12:03:53.803721
dl_token.f90898c64ff49cc6a5dcabccf365e3c9ac3f750c1afbe6b4a339ca2b219b5bdf	202|skill-token-agent-pgsktok|1781624633	\N	2026-06-16 12:03:53.812535
dl_token.8277515450a8d78ba7c2302ec8963bb548afd145c90a245ad3bab242ae3c0ad1	203|skill-token-agent-pgsktok|1781625833	\N	2026-06-16 12:03:53.852832
dl_token.45e9b13377d3e3599f762bf2c341d1292cabb3521c6923326aa80ba0e9277c85	379|skill-token-agent-pgsktok|1781625042	\N	2026-06-16 12:10:42.404262
dl_token.5f178889ae9b85dc7fedea048ab8e7f1d1224ec4414a6184f22ccc775e27634d	379|skill-token-agent-pgsktok|1781625042	\N	2026-06-16 12:10:42.411243
dl_token.b58f1b91e6264600b38edac69f66f922a4971f13707589b493a27dcd6f2ba364	380|skill-token-agent-pgsktok|1781626242	\N	2026-06-16 12:10:42.452315
dl_token.c5bff41776adaf7d39718145136883576ad8bf5348c942121e223b03328cc69c	210|skill-token-agent-pgsktok|1781625856	\N	2026-06-16 12:04:16.818181
dl_token.4f0baf7d6fffed2f20e6a25eeb0cd9666253c35511e1f4368f0380e3eeb58290	209|skill-token-agent-pgsktok|1781625856	\N	2026-06-16 12:04:16.801216
dl_token.3098f9fb0b44789cac2214e39cbcd8833f259ecd31fd5a85f9399634c7d799dd	211|skill-token-agent-pgsktok|1781624656	\N	2026-06-16 12:04:16.847107
dl_token.a7348827423d02d404e801df51fda51d5888c7411313ebfbec1d8ef7cdfdeff0	211|skill-token-agent-pgsktok|1781624656	\N	2026-06-16 12:04:16.854759
dl_token.b62795b010483fc1eb0b74577b1b9b65c89e677cd11433d5f634e626af89af4c	212|skill-token-agent-pgsktok|1781625856	\N	2026-06-16 12:04:16.896382
recovery_codes.full-flow-agent	[{"hash": "9fd00bf4f344da6201559a8a2886cf03daeea15982ea405b7e91e62dc4c77c13", "used": false}, {"hash": "3e0dd0183478c8b84ae41472da4199c5f583f456077e1616c23ba4319c91af8d", "used": false}, {"hash": "e90491ed3095f34dd0e0cb7ce42848dd8e0234e0b2443dc8e9f203ba31e857be", "used": false}, {"hash": "70a5f7e6cf0b164a4408f308714a8fe4a45b34d7c3b230ebab6d462d642251a9", "used": false}, {"hash": "78d243058ffaa543ab1948ae63fa6b58db44d5bcb6c018e1aae3d701725c57bb", "used": false}, {"hash": "c992699930db668e4355b4a95f61ad1ec157270b9751eb3179cf13b9d9467f68", "used": false}, {"hash": "b2f0443fb942324a47ff3c6848ae2a76e664b00dafe8fc1de2de909556f36ed4", "used": false}, {"hash": "095c2c31d7b287496c1e2db2fe66e601c42f087b5bc22d29ce291e3b6d7cb38e", "used": false}]	Recovery codes for agent full-flow-agent	2026-06-16 12:10:40.241109
dl_token.0cbc314df1dea8ccbb6c74d1cd55893e5d2b974c1bbac4fc88502aaf6730f4a0	230|skill-token-agent-pgsktok|1781625961	\N	2026-06-16 12:06:01.402033
dl_token.f0e8c80ea2c93eb1a02a65b07d9aec9d347015043472f55ee980ce2655763ae1	231|skill-token-agent-pgsktok|1781625961	\N	2026-06-16 12:06:01.419195
dl_token.9b04583416b6f06d61a8beeef5cef41bfd475f6833496d6df2bab36310d2b01a	232|skill-token-agent-pgsktok|1781624761	\N	2026-06-16 12:06:01.492836
dl_token.6698b7945c5a0c80a88d333ddbc61ad239f7bb0e564dbb7162c750ad6f94888b	232|skill-token-agent-pgsktok|1781624761	\N	2026-06-16 12:06:01.50023
dl_token.3ec93ae81ed2195b607ddd32d2e1e42851987f74537b76a89a0ef665436d873c	233|skill-token-agent-pgsktok|1781625961	\N	2026-06-16 12:06:01.542851
recovery_codes.admin-test-agent	[{"hash": "0c4073b3f59d9fba001dd7402b39d4db25181ea37a9f3f68273acc9b0c9cdd44", "used": false}, {"hash": "f7bf2b30dd8924a864d850a33bed81a1dfab18d62ab41f8b0eeff06886590a03", "used": false}, {"hash": "e470e5a9152b9ce5dbec72984feb6168b62b8ca8e48e0e077842e60fd252d358", "used": false}, {"hash": "d3c318c005bd650207c97bf30fee4b3787d6001370628cc50097bd68094d4dc8", "used": false}, {"hash": "fdebb472a01f15f325da9444c71aa63a52e3d0829904c425b8496bfb63d3af65", "used": false}, {"hash": "60645d5b32a1e294a17114d218c6e8f3396788a73de57495f4c45d9071ce00c1", "used": false}, {"hash": "6eab676b1097aa6622959422e77ff5f833b19734ca82ce827e75f6206870242e", "used": false}, {"hash": "65e44384f98caee09b82e53e7ea86a083beb5301e0f573ad8305b635c78befcc", "used": false}]	Recovery codes for agent admin-test-agent	2026-06-16 12:10:40.218523
dl_token.26547ebda9756d3c178ec8deb1b8e4c9a5913ec89cbe5ca9ce5202a2c7d3b7ad	356|skill-token-agent-pgsktok|1781626202	\N	2026-06-16 12:10:02.389726
dl_token.01ddbbd5dc6342cc6dea57a762d485fd267a4a7dedd0ef02ea634f3c63d9c527	357|skill-token-agent-pgsktok|1781626202	\N	2026-06-16 12:10:02.406597
dl_token.c8d7f5f7f3f3a76c6abc2bc7c3e0b11a65fbed10d1eea8146458000d9f59a1b5	358|skill-token-agent-pgsktok|1781625002	\N	2026-06-16 12:10:02.434314
dl_token.c8e593dd30b33a3e46d9bb22ae6c6cc3f7979f862422e149e126e97c5589b62b	358|skill-token-agent-pgsktok|1781625002	\N	2026-06-16 12:10:02.44055
dl_token.a02186d847f41585fe2618cf88489ff4c1cc00890734c6ca63ddabcc1825f88e	251|skill-token-agent-pgsktok|1781626048	\N	2026-06-16 12:07:28.348013
dl_token.15f692c98c680ea0ebe7807437c13a05074f6106b6d76231fce7d17e7d0b9da5	252|skill-token-agent-pgsktok|1781626048	\N	2026-06-16 12:07:28.362862
dl_token.1c7059a41cc813195564ed311b7d64865982d0e172cf8796c932fc741ad73c81	253|skill-token-agent-pgsktok|1781624848	\N	2026-06-16 12:07:28.390535
dl_token.37e3e7dec4a12894cbe81dc69e18005e9c8185b5d79b8caaaaf41d76213f1309	253|skill-token-agent-pgsktok|1781624848	\N	2026-06-16 12:07:28.397055
dl_token.b58398855aa3a9642dcbe49da22c57daa0813e0f8fe55fc6b2b5a0547dc2d666	359|skill-token-agent-pgsktok|1781626202	\N	2026-06-16 12:10:02.480191
dl_token.15754b689c87aeccb7a02b4f2279911ddd52a918d9b32bd84c5f9f66a72400ae	254|skill-token-agent-pgsktok|1781626048	\N	2026-06-16 12:07:28.440516
dl_token.a8cc53201aa67a818bad0f787f671cd2d7383ca0f3420077cf1ef81988fd6344	295|skill-token-agent-pgsktok|1781624907	\N	2026-06-16 12:08:27.430767
dl_token.d15344a48280823b65fe2bf839b54311a806cfcb2eab01679c892a0992c19b04	272|skill-token-agent-pgsktok|1781626080	\N	2026-06-16 12:08:00.467461
dl_token.5a4dee47fd14605eef548f2065eb4c83f3e4b811a7aa6e84c610ed62ccc42dd6	273|skill-token-agent-pgsktok|1781626080	\N	2026-06-16 12:08:00.484878
dl_token.a8d48fb6de7639343ca9a456f52335b0d85ef0315b63806e280fb185c1499b77	274|skill-token-agent-pgsktok|1781624880	\N	2026-06-16 12:08:00.509644
dl_token.c298283af43d993e3246b334d14be78d3f9144015ade6f6b6cb9d9a9976c4009	274|skill-token-agent-pgsktok|1781624880	\N	2026-06-16 12:08:00.515054
dl_token.66b583b98f3804c4dbf42c1a39148bf3c6f3fc59e883e3216f8a9fe585d9e5fc	275|skill-token-agent-pgsktok|1781626080	\N	2026-06-16 12:08:00.554005
dl_token.d88075197d0d28556c2f7627f86c6dc95c18355666a0bab40013dfa925b6f8bf	317|skill-token-agent-pgsktok|1781626118	\N	2026-06-16 12:08:38.507238
dl_token.e4ed2a948cf37f76d77552e7b9f3d9b3a7428d5c410b027c51caa79730ab3c48	296|skill-token-agent-pgsktok|1781626107	\N	2026-06-16 12:08:27.47124
dl_token.53f0fa4e27d4ad75ca76002d179e06f99d371f9b9efca73b47bc24603fd17190	293|skill-token-agent-pgsktok|1781626107	\N	2026-06-16 12:08:27.378302
dl_token.1755b428e62983bd128bfbc0ffce35c0e6ba6f0c74c7d4774d3456b12b7e41b5	294|skill-token-agent-pgsktok|1781626107	\N	2026-06-16 12:08:27.394646
dl_token.c4902970d7ee9ff09e93373125eedc8201938b256593ac8d9a4cbd21b6029339	295|skill-token-agent-pgsktok|1781624907	\N	2026-06-16 12:08:27.424356
dl_token.20c8cc80d603acc28961c1fa0ea347687b19b1d142b669d59874d59f218ad945	314|skill-token-agent-pgsktok|1781626118	\N	2026-06-16 12:08:38.422848
dl_token.c5981f1b68b6c1a0e0c37ec3b3a3be00971f9084847ad85852c837e3993999d8	315|skill-token-agent-pgsktok|1781626118	\N	2026-06-16 12:08:38.440428
dl_token.6d954e1dd76241af48262ee419223719b7caec6a074ff384186e7f38c7e8c09d	316|skill-token-agent-pgsktok|1781624918	\N	2026-06-16 12:08:38.46461
dl_token.de1ec5ce95ab085ee5bdaeb4c760c50d02f6b93c1df71fb8b628dc4868840ff2	316|skill-token-agent-pgsktok|1781624918	\N	2026-06-16 12:08:38.470805
\.


--
-- Data for Name: system_users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.system_users (user_id, username, password_hash, salt, role, status, auth_source, ldap_dn, last_ldap_sync, last_login, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: tags; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.tags (tag_id, tag_name, tag_group, usage_count, created_at) FROM stdin;
\.


--
-- Data for Name: task_context_snapshots; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_context_snapshots (snapshot_id, plan_id, snapshot_type, context_data, created_at) FROM stdin;
\.


--
-- Data for Name: task_dependencies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_dependencies (dep_id, source_plan_id, target_plan_id, dep_type) FROM stdin;
\.


--
-- Data for Name: task_plans_active; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_plans_active (plan_id, agent_id, goal, status, priority, strategy, result_summary, branch_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: task_plans_cancelled; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_plans_cancelled (plan_id, agent_id, goal, status, priority, strategy, result_summary, branch_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: task_plans_completed; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_plans_completed (plan_id, agent_id, goal, status, priority, strategy, result_summary, branch_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: task_plans_default; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_plans_default (plan_id, agent_id, goal, status, priority, strategy, result_summary, branch_id, created_at, updated_at) FROM stdin;
1	pg-spec-agent-1781624636	Execute spec 1781624636	PENDING	5	\N	\N	\N	2026-06-16 11:43:59.232201	2026-06-16 11:43:59.232201
2	pg-spec-agent-1781624646	Execute spec 1781624646	PENDING	5	\N	\N	\N	2026-06-16 11:44:06.65858	2026-06-16 11:44:06.65858
3	pg-spec-agent-1781624736	Execute spec 1781624736	PENDING	5	\N	\N	\N	2026-06-16 11:45:36.660784	2026-06-16 11:45:36.660784
4	pg-spec-agent-1781624754	Execute spec 1781624754	PENDING	5	\N	\N	\N	2026-06-16 11:45:54.666769	2026-06-16 11:45:54.666769
5	pg-spec-agent-1781624762	Execute spec 1781624762	PENDING	5	\N	\N	\N	2026-06-16 11:46:02.623598	2026-06-16 11:46:02.623598
6	pg-spec-agent-1781624795	Execute spec 1781624795	PENDING	5	\N	\N	\N	2026-06-16 11:46:35.668	2026-06-16 11:46:35.668
7	pg-spec-agent-1781624801	Execute spec 1781624801	PENDING	5	\N	\N	\N	2026-06-16 11:46:44.194958	2026-06-16 11:46:44.194958
8	pg-spec-agent-1781625015	Execute spec 1781625015	PENDING	5	\N	\N	\N	2026-06-16 11:50:18.246304	2026-06-16 11:50:18.246304
9	pg-spec-agent-1781625634	Execute spec 1781625634	PENDING	5	\N	\N	\N	2026-06-16 12:00:37.452971	2026-06-16 12:00:37.452971
10	pg-spec-agent-1781625758	Execute spec 1781625758	PENDING	5	\N	\N	\N	2026-06-16 12:02:41.450422	2026-06-16 12:02:41.450422
11	pg-spec-agent-1781625958	Execute spec 1781625958	PENDING	5	\N	\N	\N	2026-06-16 12:06:01.601389	2026-06-16 12:06:01.601389
12	pg-spec-agent-1781626045	Execute spec 1781626045	PENDING	5	\N	\N	\N	2026-06-16 12:07:28.49315	2026-06-16 12:07:28.49315
13	pg-spec-agent-1781626077	Execute spec 1781626077	PENDING	5	\N	\N	\N	2026-06-16 12:08:00.609401	2026-06-16 12:08:00.609401
14	pg-spec-agent-1781626104	Execute spec 1781626104	PENDING	5	\N	\N	\N	2026-06-16 12:08:27.526459	2026-06-16 12:08:27.526459
15	pg-spec-agent-1781626115	Execute spec 1781626115	PENDING	5	\N	\N	\N	2026-06-16 12:08:38.558631	2026-06-16 12:08:38.558631
16	pg-spec-agent-1781626161	Execute spec 1781626161	PENDING	5	\N	\N	\N	2026-06-16 12:09:24.517238	2026-06-16 12:09:24.517238
17	pg-spec-agent-1781626199	Execute spec 1781626199	PENDING	5	\N	\N	\N	2026-06-16 12:10:02.538014	2026-06-16 12:10:02.538014
18	pg-spec-agent-1781626239	Execute spec 1781626239	PENDING	5	\N	\N	\N	2026-06-16 12:10:42.511345	2026-06-16 12:10:42.511345
\.


--
-- Data for Name: task_plans_paused; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_plans_paused (plan_id, agent_id, goal, status, priority, strategy, result_summary, branch_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: task_steps; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_steps (step_id, plan_id, plan_status, step_order, description, tool_name, tool_input, tool_output, status, created_at) FROM stdin;
\.


--
-- Data for Name: task_tool_calls; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task_tool_calls (call_id, plan_id, step_id, tool_name, tool_input, tool_output, status, duration_ms, created_at) FROM stdin;
\.


--
-- Data for Name: workspace_context; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.workspace_context (context_id, workspace_id, agent_id, session_id, context_type, context_data, parent_context_id, branch_id, visibility, created_at) FROM stdin;
1	4	pg-ws-agent-1781623308	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:21:51.158628
2	4	pg-ws-agent-1781623308	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:21:51.166705
3	9	pg-ws-agent-1781623468	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:24:31.180735
4	9	pg-ws-agent-1781623468	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:24:31.189299
5	10	pg-ws-agent2-1781623468	2	BRANCH_POINT	{"branch_id": 1, "branch_name": "handoff-to-pg-ws-agent2-1781623468", "branch_type": "HANDOFF", "fork_context_id": null}	\N	1	SHARED	2026-06-16 11:24:31.216361
6	10	pg-ws-agent2-1781623468	3	HANDOFF	{"reason": "pg test handoff"}	\N	1	SHARED	2026-06-16 11:24:31.225776
7	14	pg-ws-agent-1781623917	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:32:00.227462
8	14	pg-ws-agent-1781623917	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:32:00.235673
9	15	pg-ws-agent2-1781623917	4	BRANCH_POINT	{"branch_id": 2, "branch_name": "handoff-to-pg-ws-agent2-1781623917", "branch_type": "HANDOFF", "fork_context_id": null}	\N	2	SHARED	2026-06-16 11:32:00.260606
10	15	pg-ws-agent2-1781623917	5	HANDOFF	{"reason": "pg test handoff"}	\N	2	SHARED	2026-06-16 11:32:00.267432
11	20	pg-ws-agent-1781624171	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:36:14.297409
12	20	pg-ws-agent-1781624171	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:36:14.306243
13	21	pg-ws-agent2-1781624171	7	BRANCH_POINT	{"branch_id": 3, "branch_name": "handoff-to-pg-ws-agent2-1781624171", "branch_type": "HANDOFF", "fork_context_id": null}	\N	3	SHARED	2026-06-16 11:36:14.338087
14	21	pg-ws-agent2-1781624171	8	HANDOFF	{"reason": "pg test handoff"}	\N	3	SHARED	2026-06-16 11:36:14.34664
15	25	pg-ws-agent-1781624271	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:37:54.32002
16	25	pg-ws-agent-1781624271	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:37:54.328343
17	26	pg-ws-agent2-1781624271	9	BRANCH_POINT	{"branch_id": 4, "branch_name": "handoff-to-pg-ws-agent2-1781624271", "branch_type": "HANDOFF", "fork_context_id": null}	\N	4	SHARED	2026-06-16 11:37:54.358698
18	26	pg-ws-agent2-1781624271	10	HANDOFF	{"reason": "pg test handoff"}	\N	4	SHARED	2026-06-16 11:37:54.368296
19	30	pg-ws-agent-1781624408	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:40:11.236278
20	30	pg-ws-agent-1781624408	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:40:11.244171
21	31	pg-ws-agent2-1781624408	11	BRANCH_POINT	{"branch_id": 5, "branch_name": "handoff-to-pg-ws-agent2-1781624408", "branch_type": "HANDOFF", "fork_context_id": null}	\N	5	SHARED	2026-06-16 11:40:11.273901
22	31	pg-ws-agent2-1781624408	12	HANDOFF	{"reason": "pg test handoff"}	\N	5	SHARED	2026-06-16 11:40:11.281628
23	35	pg-ws-agent-1781624636	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:43:59.345406
24	35	pg-ws-agent-1781624636	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:43:59.353888
25	36	pg-ws-agent2-1781624636	13	BRANCH_POINT	{"branch_id": 6, "branch_name": "handoff-to-pg-ws-agent2-1781624636", "branch_type": "HANDOFF", "fork_context_id": null}	\N	6	SHARED	2026-06-16 11:43:59.383712
26	36	pg-ws-agent2-1781624636	14	HANDOFF	{"reason": "pg test handoff"}	\N	6	SHARED	2026-06-16 11:43:59.392248
27	40	pg-ws-agent-1781624801	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:46:44.298135
28	40	pg-ws-agent-1781624801	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:46:44.307186
29	41	pg-ws-agent2-1781624801	15	BRANCH_POINT	{"branch_id": 7, "branch_name": "handoff-to-pg-ws-agent2-1781624801", "branch_type": "HANDOFF", "fork_context_id": null}	\N	7	SHARED	2026-06-16 11:46:44.337666
30	41	pg-ws-agent2-1781624801	16	HANDOFF	{"reason": "pg test handoff"}	\N	7	SHARED	2026-06-16 11:46:44.345003
31	45	pg-ws-agent-1781625015	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 11:50:18.346646
32	45	pg-ws-agent-1781625015	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 11:50:18.355304
33	50	pg-ws-agent-1781625634	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:00:37.559484
34	50	pg-ws-agent-1781625634	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:00:37.567998
35	51	pg-ws-agent2-1781625634	18	BRANCH_POINT	{"branch_id": 8, "branch_name": "handoff-to-pg-ws-agent2-1781625634", "branch_type": "HANDOFF", "fork_context_id": null}	\N	8	SHARED	2026-06-16 12:00:37.600562
36	51	pg-ws-agent2-1781625634	19	HANDOFF	{"reason": "pg test handoff"}	\N	8	SHARED	2026-06-16 12:00:37.608674
37	55	pg-ws-agent-1781625758	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:02:41.550726
38	55	pg-ws-agent-1781625758	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:02:41.558879
39	56	pg-ws-agent2-1781625758	20	BRANCH_POINT	{"branch_id": 9, "branch_name": "handoff-to-pg-ws-agent2-1781625758", "branch_type": "HANDOFF", "fork_context_id": null}	\N	9	SHARED	2026-06-16 12:02:41.59066
40	56	pg-ws-agent2-1781625758	21	HANDOFF	{"reason": "pg test handoff"}	\N	9	SHARED	2026-06-16 12:02:41.598896
41	61	pg-ws-agent-1781625958	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:06:01.706108
42	61	pg-ws-agent-1781625958	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:06:01.715177
43	62	pg-ws-agent2-1781625958	22	BRANCH_POINT	{"branch_id": 10, "branch_name": "handoff-to-pg-ws-agent2-1781625958", "branch_type": "HANDOFF", "fork_context_id": null}	\N	10	SHARED	2026-06-16 12:06:01.747446
44	62	pg-ws-agent2-1781625958	23	HANDOFF	{"reason": "pg test handoff"}	\N	10	SHARED	2026-06-16 12:06:01.754259
45	67	pg-ws-agent-1781626045	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:07:28.592682
46	67	pg-ws-agent-1781626045	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:07:28.601205
47	68	pg-ws-agent2-1781626045	24	BRANCH_POINT	{"branch_id": 11, "branch_name": "handoff-to-pg-ws-agent2-1781626045", "branch_type": "HANDOFF", "fork_context_id": null}	\N	11	SHARED	2026-06-16 12:07:28.631749
48	68	pg-ws-agent2-1781626045	25	HANDOFF	{"reason": "pg test handoff"}	\N	11	SHARED	2026-06-16 12:07:28.638479
49	73	pg-ws-agent-1781626077	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:08:00.712955
50	73	pg-ws-agent-1781626077	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:08:00.722224
51	74	pg-ws-agent2-1781626077	26	BRANCH_POINT	{"branch_id": 12, "branch_name": "handoff-to-pg-ws-agent2-1781626077", "branch_type": "HANDOFF", "fork_context_id": null}	\N	12	SHARED	2026-06-16 12:08:00.756877
52	74	pg-ws-agent2-1781626077	27	HANDOFF	{"reason": "pg test handoff"}	\N	12	SHARED	2026-06-16 12:08:00.763751
54	80	pg-ws-agent-1781626104	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:08:27.628475
55	80	pg-ws-agent-1781626104	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:08:27.637262
56	81	pg-ws-agent2-1781626104	28	BRANCH_POINT	{"branch_id": 13, "branch_name": "handoff-to-pg-ws-agent2-1781626104", "branch_type": "HANDOFF", "fork_context_id": null}	\N	13	SHARED	2026-06-16 12:08:27.668491
57	81	pg-ws-agent2-1781626104	29	HANDOFF	{"reason": "pg test handoff"}	\N	13	SHARED	2026-06-16 12:08:27.6772
59	86	pg-ws-agent-1781626115	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:08:38.662484
60	86	pg-ws-agent-1781626115	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:08:38.670928
61	87	pg-ws-agent2-1781626115	30	BRANCH_POINT	{"branch_id": 14, "branch_name": "handoff-to-pg-ws-agent2-1781626115", "branch_type": "HANDOFF", "fork_context_id": null}	\N	14	SHARED	2026-06-16 12:08:38.70067
62	87	pg-ws-agent2-1781626115	31	HANDOFF	{"reason": "pg test handoff"}	\N	14	SHARED	2026-06-16 12:08:38.709029
64	92	pg-ws-agent-1781626161	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:09:24.616376
65	92	pg-ws-agent-1781626161	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:09:24.625453
66	93	pg-ws-agent2-1781626161	32	BRANCH_POINT	{"branch_id": 15, "branch_name": "handoff-to-pg-ws-agent2-1781626161", "branch_type": "HANDOFF", "fork_context_id": null}	\N	15	SHARED	2026-06-16 12:09:24.658024
67	93	pg-ws-agent2-1781626161	33	HANDOFF	{"reason": "pg test handoff"}	\N	15	SHARED	2026-06-16 12:09:24.66512
69	98	pg-ws-agent-1781626199	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:10:02.644549
70	98	pg-ws-agent-1781626199	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:10:02.65507
71	99	pg-ws-agent2-1781626199	34	BRANCH_POINT	{"branch_id": 16, "branch_name": "handoff-to-pg-ws-agent2-1781626199", "branch_type": "HANDOFF", "fork_context_id": null}	\N	16	SHARED	2026-06-16 12:10:02.686435
72	99	pg-ws-agent2-1781626199	35	HANDOFF	{"reason": "pg test handoff"}	\N	16	SHARED	2026-06-16 12:10:02.694092
74	104	pg-ws-agent-1781626239	\N	CHECKPOINT	{"conversation": [{"role": "user", "content": "hello PG"}], "working_memory": {"findings": ["pg test"]}}	\N	\N	SHARED	2026-06-16 12:10:42.614952
75	104	pg-ws-agent-1781626239	\N	HANDOFF	{"info": "pg handoff data"}	\N	\N	SHARED	2026-06-16 12:10:42.622976
76	105	pg-ws-agent2-1781626239	36	BRANCH_POINT	{"branch_id": 17, "branch_name": "handoff-to-pg-ws-agent2-1781626239", "branch_type": "HANDOFF", "fork_context_id": null}	\N	17	SHARED	2026-06-16 12:10:42.654612
77	105	pg-ws-agent2-1781626239	37	HANDOFF	{"reason": "pg test handoff"}	\N	17	SHARED	2026-06-16 12:10:42.661906
\.


--
-- Data for Name: workspace_context_audit; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.workspace_context_audit (audit_id, context_id, workspace_id, action_type, old_value, new_value, changed_by, changed_at) FROM stdin;
\.


--
-- Data for Name: workspace_tasks; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.workspace_tasks (workspace_id, plan_id) FROM stdin;
\.


--
-- Data for Name: workspaces; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.workspaces (workspace_id, workspace_name, workspace_type, workspace_alias, isolation_mode, owner_user_id, current_agent_id, current_session_id, branch_id, summary, metadata, status, created_at, updated_at) FROM stdin;
1	CollabGroup: PG Test Collab Group 1781623308	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781623308"}	ACTIVE	2026-06-16 11:21:50.048998	2026-06-16 11:21:50.048998
2	Personal: pg-collab-lead-1781623308 in 1	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781623308", "group_id": 1}	ACTIVE	2026-06-16 11:21:50.069927	2026-06-16 11:21:50.069927
3	Personal: pg-collab-member-1781623308 in 1	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781623308", "group_id": 1}	ACTIVE	2026-06-16 11:21:50.076333	2026-06-16 11:21:50.076333
21	PG Handoff Workspace 1781624171	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781624171	8	\N	\N	\N	ACTIVE	2026-06-16 11:36:14.314196	2026-06-16 11:36:14.349329
5	PG Handoff Workspace 1781623308	CONVERSATION	\N	SHARED	admin	\N	\N	\N	\N	\N	ACTIVE	2026-06-16 11:21:51.173948	2026-06-16 11:21:51.173948
4	PG User Workspace 1781623308	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781623308	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:21:51.127215	2026-06-16 11:21:51.190365
6	CollabGroup: PG Test Collab Group 1781623468	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781623468"}	ACTIVE	2026-06-16 11:24:29.954334	2026-06-16 11:24:29.954334
7	Personal: pg-collab-lead-1781623468 in 2	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781623468", "group_id": 2}	ACTIVE	2026-06-16 11:24:29.975839	2026-06-16 11:24:29.975839
8	Personal: pg-collab-member-1781623468 in 2	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781623468", "group_id": 2}	ACTIVE	2026-06-16 11:24:29.983034	2026-06-16 11:24:29.983034
20	PG User Workspace 1781624171	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781624171	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:36:14.260507	2026-06-16 11:36:14.364309
22	CollabGroup: PG Test Collab Group 1781624271	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781624271"}	ACTIVE	2026-06-16 11:37:52.96253	2026-06-16 11:37:52.96253
10	PG Handoff Workspace 1781623468	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781623468	3	\N	\N	\N	ACTIVE	2026-06-16 11:24:31.195201	2026-06-16 11:24:31.228875
9	PG User Workspace 1781623468	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781623468	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:24:31.144673	2026-06-16 11:24:31.238155
11	CollabGroup: PG Test Collab Group 1781623917	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781623917"}	ACTIVE	2026-06-16 11:31:58.942079	2026-06-16 11:31:58.942079
12	Personal: pg-collab-lead-1781623917 in 3	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781623917", "group_id": 3}	ACTIVE	2026-06-16 11:31:58.966144	2026-06-16 11:31:58.966144
13	Personal: pg-collab-member-1781623917 in 3	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781623917", "group_id": 3}	ACTIVE	2026-06-16 11:31:58.97331	2026-06-16 11:31:58.97331
23	Personal: pg-collab-lead-1781624271 in 5	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781624271", "group_id": 5}	ACTIVE	2026-06-16 11:37:52.992179	2026-06-16 11:37:52.992179
24	Personal: pg-collab-member-1781624271 in 5	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781624271", "group_id": 5}	ACTIVE	2026-06-16 11:37:52.999566	2026-06-16 11:37:52.999566
15	PG Handoff Workspace 1781623917	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781623917	5	\N	\N	\N	ACTIVE	2026-06-16 11:32:00.242111	2026-06-16 11:32:00.270009
14	PG User Workspace 1781623917	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781623917	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:32:00.190879	2026-06-16 11:32:00.283293
16	PG Handoff Workspace 1781624117	CONVERSATION	\N	SHARED	admin	\N	\N	\N	\N	\N	ACTIVE	2026-06-16 11:35:17.651475	2026-06-16 11:35:17.651475
17	CollabGroup: PG Test Collab Group 1781624171	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781624171"}	ACTIVE	2026-06-16 11:36:12.96579	2026-06-16 11:36:12.96579
18	Personal: pg-collab-lead-1781624171 in 4	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781624171", "group_id": 4}	ACTIVE	2026-06-16 11:36:12.990522	2026-06-16 11:36:12.990522
19	Personal: pg-collab-member-1781624171 in 4	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781624171", "group_id": 4}	ACTIVE	2026-06-16 11:36:12.997692	2026-06-16 11:36:12.997692
26	PG Handoff Workspace 1781624271	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781624271	10	\N	\N	\N	ACTIVE	2026-06-16 11:37:54.335941	2026-06-16 11:37:54.371369
25	PG User Workspace 1781624271	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781624271	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:37:54.284239	2026-06-16 11:37:54.388377
27	CollabGroup: PG Test Collab Group 1781624408	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781624408"}	ACTIVE	2026-06-16 11:40:09.953865	2026-06-16 11:40:09.953865
28	Personal: pg-collab-lead-1781624408 in 6	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781624408", "group_id": 6}	ACTIVE	2026-06-16 11:40:09.984974	2026-06-16 11:40:09.984974
29	Personal: pg-collab-member-1781624408 in 6	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781624408", "group_id": 6}	ACTIVE	2026-06-16 11:40:09.991326	2026-06-16 11:40:09.991326
33	Personal: pg-collab-lead-1781624636 in 7	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781624636", "group_id": 7}	ACTIVE	2026-06-16 11:43:57.947309	2026-06-16 11:43:57.947309
34	Personal: pg-collab-member-1781624636 in 7	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781624636", "group_id": 7}	ACTIVE	2026-06-16 11:43:57.953893	2026-06-16 11:43:57.953893
31	PG Handoff Workspace 1781624408	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781624408	12	\N	\N	\N	ACTIVE	2026-06-16 11:40:11.251346	2026-06-16 11:40:11.284289
30	PG User Workspace 1781624408	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781624408	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:40:11.200036	2026-06-16 11:40:11.300715
32	CollabGroup: PG Test Collab Group 1781624636	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781624636"}	ACTIVE	2026-06-16 11:43:57.922575	2026-06-16 11:43:57.922575
35	PG User Workspace 1781624636	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781624636	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:43:59.31009	2026-06-16 11:43:59.410477
36	PG Handoff Workspace 1781624636	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781624636	14	\N	\N	\N	ACTIVE	2026-06-16 11:43:59.36177	2026-06-16 11:43:59.395174
37	CollabGroup: PG Test Collab Group 1781624801	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781624801"}	ACTIVE	2026-06-16 11:46:42.888139	2026-06-16 11:46:42.888139
38	Personal: pg-collab-lead-1781624801 in 8	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781624801", "group_id": 8}	ACTIVE	2026-06-16 11:46:42.912579	2026-06-16 11:46:42.912579
39	Personal: pg-collab-member-1781624801 in 8	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781624801", "group_id": 8}	ACTIVE	2026-06-16 11:46:42.918717	2026-06-16 11:46:42.918717
41	PG Handoff Workspace 1781624801	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781624801	16	\N	\N	\N	ACTIVE	2026-06-16 11:46:44.313625	2026-06-16 11:46:44.348306
40	PG User Workspace 1781624801	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781624801	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:46:44.262408	2026-06-16 11:46:44.364425
42	CollabGroup: PG Test Collab Group 1781625015	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781625015"}	ACTIVE	2026-06-16 11:50:16.932412	2026-06-16 11:50:16.932412
43	Personal: pg-collab-lead-1781625015 in 9	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781625015", "group_id": 9}	ACTIVE	2026-06-16 11:50:16.958644	2026-06-16 11:50:16.958644
44	Personal: pg-collab-member-1781625015 in 9	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781625015", "group_id": 9}	ACTIVE	2026-06-16 11:50:16.966195	2026-06-16 11:50:16.966195
46	PG Handoff Workspace 1781625015	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781625015	17	\N	\N	\N	ACTIVE	2026-06-16 11:50:18.362256	2026-06-16 11:50:18.375901
45	PG User Workspace 1781625015	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781625015	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 11:50:18.312678	2026-06-16 11:50:18.409376
47	CollabGroup: PG Test Collab Group 1781625634	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781625634"}	ACTIVE	2026-06-16 12:00:35.945389	2026-06-16 12:00:35.945389
48	Personal: pg-collab-lead-1781625634 in 10	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781625634", "group_id": 10}	ACTIVE	2026-06-16 12:00:35.971507	2026-06-16 12:00:35.971507
49	Personal: pg-collab-member-1781625634 in 10	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781625634", "group_id": 10}	ACTIVE	2026-06-16 12:00:35.978526	2026-06-16 12:00:35.978526
72	Personal: pg-collab-member-1781626077 in 14	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781626077", "group_id": 14}	ACTIVE	2026-06-16 12:07:59.017047	2026-06-16 12:07:59.017047
62	PG Handoff Workspace 1781625958	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781625958	23	\N	\N	\N	ACTIVE	2026-06-16 12:06:01.721991	2026-06-16 12:06:01.757115
51	PG Handoff Workspace 1781625634	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781625634	19	\N	\N	\N	ACTIVE	2026-06-16 12:00:37.575278	2026-06-16 12:00:37.61177
50	PG User Workspace 1781625634	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781625634	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:00:37.518446	2026-06-16 12:00:37.627084
52	CollabGroup: PG Test Collab Group 1781625758	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781625758"}	ACTIVE	2026-06-16 12:02:39.922333	2026-06-16 12:02:39.922333
53	Personal: pg-collab-lead-1781625758 in 11	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781625758", "group_id": 11}	ACTIVE	2026-06-16 12:02:39.946303	2026-06-16 12:02:39.946303
54	Personal: pg-collab-member-1781625758 in 11	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781625758", "group_id": 11}	ACTIVE	2026-06-16 12:02:39.95279	2026-06-16 12:02:39.95279
61	PG User Workspace 1781625958	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781625958	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:06:01.670317	2026-06-16 12:06:01.774135
56	PG Handoff Workspace 1781625758	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781625758	21	\N	\N	\N	ACTIVE	2026-06-16 12:02:41.566872	2026-06-16 12:02:41.602383
55	PG User Workspace 1781625758	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781625758	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:02:41.514761	2026-06-16 12:02:41.619632
58	CollabGroup: PG Test Collab Group 1781625958	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781625958"}	ACTIVE	2026-06-16 12:05:59.934136	2026-06-16 12:05:59.934136
59	Personal: pg-collab-lead-1781625958 in 12	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781625958", "group_id": 12}	ACTIVE	2026-06-16 12:05:59.958503	2026-06-16 12:05:59.958503
60	Personal: pg-collab-member-1781625958 in 12	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781625958", "group_id": 12}	ACTIVE	2026-06-16 12:05:59.966143	2026-06-16 12:05:59.966143
64	CollabGroup: PG Test Collab Group 1781626045	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781626045"}	ACTIVE	2026-06-16 12:07:26.913176	2026-06-16 12:07:26.913176
65	Personal: pg-collab-lead-1781626045 in 13	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781626045", "group_id": 13}	ACTIVE	2026-06-16 12:07:26.936514	2026-06-16 12:07:26.936514
66	Personal: pg-collab-member-1781626045 in 13	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781626045", "group_id": 13}	ACTIVE	2026-06-16 12:07:26.944053	2026-06-16 12:07:26.944053
68	PG Handoff Workspace 1781626045	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781626045	25	\N	\N	\N	ACTIVE	2026-06-16 12:07:28.608488	2026-06-16 12:07:28.641867
67	PG User Workspace 1781626045	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781626045	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:07:28.55892	2026-06-16 12:07:28.656973
70	CollabGroup: PG Test Collab Group 1781626077	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781626077"}	ACTIVE	2026-06-16 12:07:58.983156	2026-06-16 12:07:58.983156
71	Personal: pg-collab-lead-1781626077 in 14	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781626077", "group_id": 14}	ACTIVE	2026-06-16 12:07:59.009966	2026-06-16 12:07:59.009966
74	PG Handoff Workspace 1781626077	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781626077	27	\N	\N	\N	ACTIVE	2026-06-16 12:08:00.730866	2026-06-16 12:08:00.766704
73	PG User Workspace 1781626077	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781626077	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:08:00.677961	2026-06-16 12:08:00.785142
77	CollabGroup: PG Test Collab Group 1781626104	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781626104"}	ACTIVE	2026-06-16 12:08:25.918303	2026-06-16 12:08:25.918303
78	Personal: pg-collab-lead-1781626104 in 15	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781626104", "group_id": 15}	ACTIVE	2026-06-16 12:08:25.945229	2026-06-16 12:08:25.945229
79	Personal: pg-collab-member-1781626104 in 15	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781626104", "group_id": 15}	ACTIVE	2026-06-16 12:08:25.953732	2026-06-16 12:08:25.953732
80	PG User Workspace 1781626104	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781626104	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:08:27.590499	2026-06-16 12:08:27.697396
81	PG Handoff Workspace 1781626104	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781626104	29	\N	\N	\N	ACTIVE	2026-06-16 12:08:27.64633	2026-06-16 12:08:27.6804
83	CollabGroup: PG Test Collab Group 1781626115	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781626115"}	ACTIVE	2026-06-16 12:08:36.957773	2026-06-16 12:08:36.957773
84	Personal: pg-collab-lead-1781626115 in 16	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781626115", "group_id": 16}	ACTIVE	2026-06-16 12:08:36.983785	2026-06-16 12:08:36.983785
85	Personal: pg-collab-member-1781626115 in 16	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781626115", "group_id": 16}	ACTIVE	2026-06-16 12:08:36.991697	2026-06-16 12:08:36.991697
105	PG Handoff Workspace 1781626239	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781626239	37	\N	\N	\N	ACTIVE	2026-06-16 12:10:42.630089	2026-06-16 12:10:42.665785
87	PG Handoff Workspace 1781626115	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781626115	31	\N	\N	\N	ACTIVE	2026-06-16 12:08:38.677776	2026-06-16 12:08:38.712269
86	PG User Workspace 1781626115	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781626115	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:08:38.62444	2026-06-16 12:08:38.729046
89	CollabGroup: PG Test Collab Group 1781626161	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781626161"}	ACTIVE	2026-06-16 12:09:22.921085	2026-06-16 12:09:22.921085
90	Personal: pg-collab-lead-1781626161 in 17	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781626161", "group_id": 17}	ACTIVE	2026-06-16 12:09:22.946334	2026-06-16 12:09:22.946334
91	Personal: pg-collab-member-1781626161 in 17	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781626161", "group_id": 17}	ACTIVE	2026-06-16 12:09:22.95438	2026-06-16 12:09:22.95438
104	PG User Workspace 1781626239	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781626239	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:10:42.578733	2026-06-16 12:10:42.682983
93	PG Handoff Workspace 1781626161	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781626161	33	\N	\N	\N	ACTIVE	2026-06-16 12:09:24.631657	2026-06-16 12:09:24.669472
92	PG User Workspace 1781626161	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781626161	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:09:24.579494	2026-06-16 12:09:24.68548
95	CollabGroup: PG Test Collab Group 1781626199	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781626199"}	ACTIVE	2026-06-16 12:10:00.918782	2026-06-16 12:10:00.918782
96	Personal: pg-collab-lead-1781626199 in 18	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781626199", "group_id": 18}	ACTIVE	2026-06-16 12:10:00.942847	2026-06-16 12:10:00.942847
97	Personal: pg-collab-member-1781626199 in 18	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781626199", "group_id": 18}	ACTIVE	2026-06-16 12:10:00.950048	2026-06-16 12:10:00.950048
99	PG Handoff Workspace 1781626199	CONVERSATION	\N	SHARED	admin	pg-ws-agent2-1781626199	35	\N	\N	\N	ACTIVE	2026-06-16 12:10:02.662244	2026-06-16 12:10:02.69867
98	PG User Workspace 1781626199	CONVERSATION	\N	SHARED	admin	pg-ws-agent-1781626199	\N	\N	PG test summary	\N	ACTIVE	2026-06-16 12:10:02.605456	2026-06-16 12:10:02.717601
101	CollabGroup: PG Test Collab Group 1781626239	COLLAB_GROUP	\N	SHARED	\N	\N	\N	\N	\N	{"group_type": "PROJECT", "collab_group_name": "PG Test Collab Group 1781626239"}	ACTIVE	2026-06-16 12:10:40.907741	2026-06-16 12:10:40.907741
102	Personal: pg-collab-lead-1781626239 in 19	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "LEAD", "agent_id": "pg-collab-lead-1781626239", "group_id": 19}	ACTIVE	2026-06-16 12:10:40.931747	2026-06-16 12:10:40.931747
103	Personal: pg-collab-member-1781626239 in 19	PERSONAL_IN_GROUP	\N	ISOLATED	\N	\N	\N	\N	\N	{"role": "CONTRIBUTOR", "agent_id": "pg-collab-member-1781626239", "group_id": 19}	ACTIVE	2026-06-16 12:10:40.937623	2026-06-16 12:10:40.937623
\.


--
-- Name: agent_collaboration_collab_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agent_collaboration_collab_id_seq', 1, false);


--
-- Name: agent_credentials_credential_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agent_credentials_credential_id_seq', 1, false);


--
-- Name: agent_permission_log_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agent_permission_log_log_id_seq', 1, false);


--
-- Name: agent_session_session_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agent_session_session_id_seq', 37, true);


--
-- Name: branch_merge_log_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.branch_merge_log_log_id_seq', 1, false);


--
-- Name: collab_group_members_member_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.collab_group_members_member_id_seq', 57, true);


--
-- Name: collab_groups_group_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.collab_groups_group_id_seq', 19, true);


--
-- Name: compliance_log_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.compliance_log_log_id_seq', 17, true);


--
-- Name: context_branches_branch_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.context_branches_branch_id_seq', 17, true);


--
-- Name: entities_entity_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.entities_entity_id_seq', 145, true);


--
-- Name: entity_access_audit_audit_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.entity_access_audit_audit_id_seq', 16, true);


--
-- Name: entity_access_log_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.entity_access_log_log_id_seq', 1, false);


--
-- Name: entity_edges_edge_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.entity_edges_edge_id_seq', 71, true);


--
-- Name: ldap_config_config_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ldap_config_config_id_seq', 70, true);


--
-- Name: skill_access_token_token_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.skill_access_token_token_id_seq', 1, false);


--
-- Name: skill_meta_skill_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.skill_meta_skill_id_seq', 380, true);


--
-- Name: spec_plan_links_link_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.spec_plan_links_link_id_seq', 13, true);


--
-- Name: system_users_user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.system_users_user_id_seq', 1, false);


--
-- Name: tags_tag_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tags_tag_id_seq', 1, false);


--
-- Name: task_context_snapshots_snapshot_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.task_context_snapshots_snapshot_id_seq', 1, false);


--
-- Name: task_dependencies_dep_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.task_dependencies_dep_id_seq', 1, false);


--
-- Name: task_plans_plan_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.task_plans_plan_id_seq', 18, true);


--
-- Name: task_steps_step_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.task_steps_step_id_seq', 1, false);


--
-- Name: task_tool_calls_call_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.task_tool_calls_call_id_seq', 1, false);


--
-- Name: workspace_context_audit_audit_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.workspace_context_audit_audit_id_seq', 9, true);


--
-- Name: workspace_context_context_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.workspace_context_context_id_seq', 77, true);


--
-- Name: workspaces_workspace_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.workspaces_workspace_id_seq', 105, true);


--
-- Name: agent_collaboration agent_collaboration_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_collaboration
    ADD CONSTRAINT agent_collaboration_pkey PRIMARY KEY (collab_id);


--
-- Name: agent_credentials agent_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_credentials
    ADD CONSTRAINT agent_credentials_pkey PRIMARY KEY (credential_id);


--
-- Name: agent_permission_log agent_permission_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_permission_log
    ADD CONSTRAINT agent_permission_log_pkey PRIMARY KEY (log_id);


--
-- Name: agent_registry agent_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_registry
    ADD CONSTRAINT agent_registry_pkey PRIMARY KEY (agent_id);


--
-- Name: agent_session pk_agent_session; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_session
    ADD CONSTRAINT pk_agent_session PRIMARY KEY (session_id, is_active);


--
-- Name: agent_session_active agent_session_active_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_session_active
    ADD CONSTRAINT agent_session_active_pkey PRIMARY KEY (session_id, is_active);


--
-- Name: agent_session_inactive agent_session_inactive_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_session_inactive
    ADD CONSTRAINT agent_session_inactive_pkey PRIMARY KEY (session_id, is_active);


--
-- Name: branch_merge_log branch_merge_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.branch_merge_log
    ADD CONSTRAINT branch_merge_log_pkey PRIMARY KEY (log_id);


--
-- Name: collab_group_members collab_group_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_group_members
    ADD CONSTRAINT collab_group_members_pkey PRIMARY KEY (member_id);


--
-- Name: collab_groups collab_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_groups
    ADD CONSTRAINT collab_groups_pkey PRIMARY KEY (group_id);


--
-- Name: compliance_log compliance_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compliance_log
    ADD CONSTRAINT compliance_log_pkey PRIMARY KEY (log_id);


--
-- Name: context_branches context_branches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_branches
    ADD CONSTRAINT context_branches_pkey PRIMARY KEY (branch_id);


--
-- Name: entities pk_entities; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities
    ADD CONSTRAINT pk_entities PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_default entities_default_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_default
    ADD CONSTRAINT entities_default_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_experience entities_experience_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_experience
    ADD CONSTRAINT entities_experience_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_harness_template entities_harness_template_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_harness_template
    ADD CONSTRAINT entities_harness_template_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_knowledge entities_knowledge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_knowledge
    ADD CONSTRAINT entities_knowledge_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_memory entities_memory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_memory
    ADD CONSTRAINT entities_memory_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_other entities_other_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_other
    ADD CONSTRAINT entities_other_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_skill entities_skill_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_skill
    ADD CONSTRAINT entities_skill_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_spec entities_spec_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_spec
    ADD CONSTRAINT entities_spec_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entities_task_output entities_task_output_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities_task_output
    ADD CONSTRAINT entities_task_output_pkey PRIMARY KEY (entity_id, entity_type);


--
-- Name: entity_access_audit entity_access_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_access_audit
    ADD CONSTRAINT entity_access_audit_pkey PRIMARY KEY (audit_id);


--
-- Name: entity_edges entity_edges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_edges
    ADD CONSTRAINT entity_edges_pkey PRIMARY KEY (edge_id);


--
-- Name: ldap_config ldap_config_config_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ldap_config
    ADD CONSTRAINT ldap_config_config_name_key UNIQUE (config_name);


--
-- Name: ldap_config ldap_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ldap_config
    ADD CONSTRAINT ldap_config_pkey PRIMARY KEY (config_id);


--
-- Name: entity_embeddings pk_entity_embeddings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_embeddings
    ADD CONSTRAINT pk_entity_embeddings PRIMARY KEY (entity_id, entity_type);


--
-- Name: entity_tags pk_entity_tags; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_tags
    ADD CONSTRAINT pk_entity_tags PRIMARY KEY (entity_id, entity_type, tag_id);


--
-- Name: harness_meta pk_harness_meta; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.harness_meta
    ADD CONSTRAINT pk_harness_meta PRIMARY KEY (entity_id, entity_type);


--
-- Name: knowledge_meta pk_knowledge_meta; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_meta
    ADD CONSTRAINT pk_knowledge_meta PRIMARY KEY (entity_id, entity_type);


--
-- Name: spec_meta pk_spec_meta; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spec_meta
    ADD CONSTRAINT pk_spec_meta PRIMARY KEY (entity_id, entity_type);


--
-- Name: task_plans pk_task_plans; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans
    ADD CONSTRAINT pk_task_plans PRIMARY KEY (plan_id, status);


--
-- Name: workspace_tasks pk_workspace_tasks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_tasks
    ADD CONSTRAINT pk_workspace_tasks PRIMARY KEY (workspace_id, plan_id);


--
-- Name: skill_access_token skill_access_token_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_access_token
    ADD CONSTRAINT skill_access_token_pkey PRIMARY KEY (token_id);


--
-- Name: skill_access_token skill_access_token_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_access_token
    ADD CONSTRAINT skill_access_token_token_hash_key UNIQUE (token_hash);


--
-- Name: skill_meta skill_meta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_meta
    ADD CONSTRAINT skill_meta_pkey PRIMARY KEY (skill_id);


--
-- Name: spec_plan_links spec_plan_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spec_plan_links
    ADD CONSTRAINT spec_plan_links_pkey PRIMARY KEY (link_id);


--
-- Name: system_config system_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_config
    ADD CONSTRAINT system_config_pkey PRIMARY KEY (config_key);


--
-- Name: system_users system_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_users
    ADD CONSTRAINT system_users_pkey PRIMARY KEY (user_id);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (tag_id);


--
-- Name: task_context_snapshots task_context_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_context_snapshots
    ADD CONSTRAINT task_context_snapshots_pkey PRIMARY KEY (snapshot_id);


--
-- Name: task_dependencies task_dependencies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_dependencies
    ADD CONSTRAINT task_dependencies_pkey PRIMARY KEY (dep_id);


--
-- Name: task_plans_active task_plans_active_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans_active
    ADD CONSTRAINT task_plans_active_pkey PRIMARY KEY (plan_id, status);


--
-- Name: task_plans_cancelled task_plans_cancelled_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans_cancelled
    ADD CONSTRAINT task_plans_cancelled_pkey PRIMARY KEY (plan_id, status);


--
-- Name: task_plans_completed task_plans_completed_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans_completed
    ADD CONSTRAINT task_plans_completed_pkey PRIMARY KEY (plan_id, status);


--
-- Name: task_plans_default task_plans_default_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans_default
    ADD CONSTRAINT task_plans_default_pkey PRIMARY KEY (plan_id, status);


--
-- Name: task_plans_paused task_plans_paused_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_plans_paused
    ADD CONSTRAINT task_plans_paused_pkey PRIMARY KEY (plan_id, status);


--
-- Name: task_steps task_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_steps
    ADD CONSTRAINT task_steps_pkey PRIMARY KEY (step_id);


--
-- Name: task_tool_calls task_tool_calls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tool_calls
    ADD CONSTRAINT task_tool_calls_pkey PRIMARY KEY (call_id);


--
-- Name: collab_group_members uk_cgm_membership; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_group_members
    ADD CONSTRAINT uk_cgm_membership UNIQUE (group_id, agent_id);


--
-- Name: spec_plan_links uk_spl_link; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spec_plan_links
    ADD CONSTRAINT uk_spl_link UNIQUE (spec_id, plan_id, link_type);


--
-- Name: system_users uk_su_username; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_users
    ADD CONSTRAINT uk_su_username UNIQUE (username);


--
-- Name: tags uk_tags_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT uk_tags_name UNIQUE (tag_name);


--
-- Name: workspace_context_audit workspace_context_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_context_audit
    ADD CONSTRAINT workspace_context_audit_pkey PRIMARY KEY (audit_id);


--
-- Name: workspace_context workspace_context_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_context
    ADD CONSTRAINT workspace_context_pkey PRIMARY KEY (context_id);


--
-- Name: workspaces workspaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (workspace_id);


--
-- Name: idx_as_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_as_agent ON ONLY public.agent_session USING btree (agent_id);


--
-- Name: agent_session_active_agent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_active_agent_id_idx ON public.agent_session_active USING btree (agent_id);


--
-- Name: idx_as_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_as_owner ON ONLY public.agent_session USING btree (owner_user_id);


--
-- Name: agent_session_active_owner_user_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_active_owner_user_id_idx ON public.agent_session_active USING btree (owner_user_id);


--
-- Name: idx_as_predecessor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_as_predecessor ON ONLY public.agent_session USING btree (predecessor_session_id);


--
-- Name: agent_session_active_predecessor_session_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_active_predecessor_session_id_idx ON public.agent_session_active USING btree (predecessor_session_id);


--
-- Name: idx_as_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_as_workspace ON ONLY public.agent_session USING btree (workspace_id);


--
-- Name: agent_session_active_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_active_workspace_id_idx ON public.agent_session_active USING btree (workspace_id);


--
-- Name: agent_session_inactive_agent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_inactive_agent_id_idx ON public.agent_session_inactive USING btree (agent_id);


--
-- Name: agent_session_inactive_owner_user_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_inactive_owner_user_id_idx ON public.agent_session_inactive USING btree (owner_user_id);


--
-- Name: agent_session_inactive_predecessor_session_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_inactive_predecessor_session_id_idx ON public.agent_session_inactive USING btree (predecessor_session_id);


--
-- Name: agent_session_inactive_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agent_session_inactive_workspace_id_idx ON public.agent_session_inactive USING btree (workspace_id);


--
-- Name: idx_entities_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_category ON ONLY public.entities USING btree (category);


--
-- Name: entities_default_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_default_category_idx ON public.entities_default USING btree (category);


--
-- Name: idx_entities_owned_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_owned_by ON ONLY public.entities USING btree (owned_by_agent);


--
-- Name: entities_default_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_default_owned_by_agent_idx ON public.entities_default USING btree (owned_by_agent);


--
-- Name: idx_entities_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_search ON ONLY public.entities USING gin (search_vector);


--
-- Name: entities_default_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_default_search_vector_idx ON public.entities_default USING gin (search_vector);


--
-- Name: idx_entities_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_status ON ONLY public.entities USING btree (status);


--
-- Name: entities_default_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_default_status_idx ON public.entities_default USING btree (status);


--
-- Name: idx_entities_visibility; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_visibility ON ONLY public.entities USING btree (visibility);


--
-- Name: entities_default_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_default_visibility_idx ON public.entities_default USING btree (visibility);


--
-- Name: idx_entities_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_workspace ON ONLY public.entities USING btree (workspace_id);


--
-- Name: entities_default_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_default_workspace_id_idx ON public.entities_default USING btree (workspace_id);


--
-- Name: entities_experience_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_experience_category_idx ON public.entities_experience USING btree (category);


--
-- Name: entities_experience_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_experience_owned_by_agent_idx ON public.entities_experience USING btree (owned_by_agent);


--
-- Name: entities_experience_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_experience_search_vector_idx ON public.entities_experience USING gin (search_vector);


--
-- Name: entities_experience_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_experience_status_idx ON public.entities_experience USING btree (status);


--
-- Name: entities_experience_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_experience_visibility_idx ON public.entities_experience USING btree (visibility);


--
-- Name: entities_experience_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_experience_workspace_id_idx ON public.entities_experience USING btree (workspace_id);


--
-- Name: entities_harness_template_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_harness_template_category_idx ON public.entities_harness_template USING btree (category);


--
-- Name: entities_harness_template_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_harness_template_owned_by_agent_idx ON public.entities_harness_template USING btree (owned_by_agent);


--
-- Name: entities_harness_template_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_harness_template_search_vector_idx ON public.entities_harness_template USING gin (search_vector);


--
-- Name: entities_harness_template_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_harness_template_status_idx ON public.entities_harness_template USING btree (status);


--
-- Name: entities_harness_template_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_harness_template_visibility_idx ON public.entities_harness_template USING btree (visibility);


--
-- Name: entities_harness_template_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_harness_template_workspace_id_idx ON public.entities_harness_template USING btree (workspace_id);


--
-- Name: entities_knowledge_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_knowledge_category_idx ON public.entities_knowledge USING btree (category);


--
-- Name: entities_knowledge_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_knowledge_owned_by_agent_idx ON public.entities_knowledge USING btree (owned_by_agent);


--
-- Name: entities_knowledge_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_knowledge_search_vector_idx ON public.entities_knowledge USING gin (search_vector);


--
-- Name: entities_knowledge_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_knowledge_status_idx ON public.entities_knowledge USING btree (status);


--
-- Name: entities_knowledge_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_knowledge_visibility_idx ON public.entities_knowledge USING btree (visibility);


--
-- Name: entities_knowledge_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_knowledge_workspace_id_idx ON public.entities_knowledge USING btree (workspace_id);


--
-- Name: entities_memory_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_memory_category_idx ON public.entities_memory USING btree (category);


--
-- Name: entities_memory_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_memory_owned_by_agent_idx ON public.entities_memory USING btree (owned_by_agent);


--
-- Name: entities_memory_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_memory_search_vector_idx ON public.entities_memory USING gin (search_vector);


--
-- Name: entities_memory_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_memory_status_idx ON public.entities_memory USING btree (status);


--
-- Name: entities_memory_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_memory_visibility_idx ON public.entities_memory USING btree (visibility);


--
-- Name: entities_memory_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_memory_workspace_id_idx ON public.entities_memory USING btree (workspace_id);


--
-- Name: entities_other_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_other_category_idx ON public.entities_other USING btree (category);


--
-- Name: entities_other_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_other_owned_by_agent_idx ON public.entities_other USING btree (owned_by_agent);


--
-- Name: entities_other_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_other_search_vector_idx ON public.entities_other USING gin (search_vector);


--
-- Name: entities_other_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_other_status_idx ON public.entities_other USING btree (status);


--
-- Name: entities_other_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_other_visibility_idx ON public.entities_other USING btree (visibility);


--
-- Name: entities_other_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_other_workspace_id_idx ON public.entities_other USING btree (workspace_id);


--
-- Name: entities_skill_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_skill_category_idx ON public.entities_skill USING btree (category);


--
-- Name: entities_skill_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_skill_owned_by_agent_idx ON public.entities_skill USING btree (owned_by_agent);


--
-- Name: entities_skill_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_skill_search_vector_idx ON public.entities_skill USING gin (search_vector);


--
-- Name: entities_skill_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_skill_status_idx ON public.entities_skill USING btree (status);


--
-- Name: entities_skill_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_skill_visibility_idx ON public.entities_skill USING btree (visibility);


--
-- Name: entities_skill_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_skill_workspace_id_idx ON public.entities_skill USING btree (workspace_id);


--
-- Name: entities_spec_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_spec_category_idx ON public.entities_spec USING btree (category);


--
-- Name: entities_spec_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_spec_owned_by_agent_idx ON public.entities_spec USING btree (owned_by_agent);


--
-- Name: entities_spec_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_spec_search_vector_idx ON public.entities_spec USING gin (search_vector);


--
-- Name: entities_spec_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_spec_status_idx ON public.entities_spec USING btree (status);


--
-- Name: entities_spec_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_spec_visibility_idx ON public.entities_spec USING btree (visibility);


--
-- Name: entities_spec_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_spec_workspace_id_idx ON public.entities_spec USING btree (workspace_id);


--
-- Name: entities_task_output_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_task_output_category_idx ON public.entities_task_output USING btree (category);


--
-- Name: entities_task_output_owned_by_agent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_task_output_owned_by_agent_idx ON public.entities_task_output USING btree (owned_by_agent);


--
-- Name: entities_task_output_search_vector_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_task_output_search_vector_idx ON public.entities_task_output USING gin (search_vector);


--
-- Name: entities_task_output_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_task_output_status_idx ON public.entities_task_output USING btree (status);


--
-- Name: entities_task_output_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_task_output_visibility_idx ON public.entities_task_output USING btree (visibility);


--
-- Name: entities_task_output_workspace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entities_task_output_workspace_id_idx ON public.entities_task_output USING btree (workspace_id);


--
-- Name: idx_eal_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eal_time ON ONLY public.entity_access_log USING btree (access_time);


--
-- Name: entity_access_log_202605_access_time_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entity_access_log_202605_access_time_idx ON public.entity_access_log_202605 USING btree (access_time);


--
-- Name: idx_eal_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eal_entity ON ONLY public.entity_access_log USING btree (entity_id);


--
-- Name: entity_access_log_202605_entity_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entity_access_log_202605_entity_id_idx ON public.entity_access_log_202605 USING btree (entity_id);


--
-- Name: entity_access_log_202606_access_time_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entity_access_log_202606_access_time_idx ON public.entity_access_log_202606 USING btree (access_time);


--
-- Name: entity_access_log_202606_entity_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entity_access_log_202606_entity_id_idx ON public.entity_access_log_202606 USING btree (entity_id);


--
-- Name: entity_access_log_max_access_time_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entity_access_log_max_access_time_idx ON public.entity_access_log_max USING btree (access_time);


--
-- Name: entity_access_log_max_entity_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entity_access_log_max_entity_id_idx ON public.entity_access_log_max USING btree (entity_id);


--
-- Name: idx_ac_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ac_active ON public.agent_credentials USING btree (is_active);


--
-- Name: idx_ac_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ac_agent ON public.agent_credentials USING btree (agent_id);


--
-- Name: idx_ac_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ac_user ON public.agent_credentials USING btree (user_id);


--
-- Name: idx_apl_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apl_agent ON public.agent_permission_log USING btree (agent_id);


--
-- Name: idx_ar_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ar_created_by ON public.agent_registry USING btree (created_by_agent_id);


--
-- Name: idx_ar_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ar_role ON public.agent_registry USING btree (agent_role);


--
-- Name: idx_ar_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ar_status ON public.agent_registry USING btree (status);


--
-- Name: idx_ar_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ar_type ON public.agent_registry USING btree (agent_type);


--
-- Name: idx_ar_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ar_user ON public.agent_registry USING btree (current_user_id);


--
-- Name: idx_bml_src; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bml_src ON public.branch_merge_log USING btree (source_branch_id);


--
-- Name: idx_bml_tgt; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bml_tgt ON public.branch_merge_log USING btree (target_branch_id);


--
-- Name: idx_cb_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cb_agent ON public.context_branches USING btree (agent_id);


--
-- Name: idx_cb_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cb_parent ON public.context_branches USING btree (parent_branch_id);


--
-- Name: idx_cb_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cb_status ON public.context_branches USING btree (status);


--
-- Name: idx_cb_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cb_type ON public.context_branches USING btree (branch_type);


--
-- Name: idx_cb_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cb_workspace ON public.context_branches USING btree (workspace_id);


--
-- Name: idx_cg_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cg_status ON public.collab_groups USING btree (status);


--
-- Name: idx_cg_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cg_type ON public.collab_groups USING btree (group_type);


--
-- Name: idx_cg_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cg_workspace ON public.collab_groups USING btree (workspace_id);


--
-- Name: idx_cgm_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cgm_agent ON public.collab_group_members USING btree (agent_id);


--
-- Name: idx_cgm_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cgm_group ON public.collab_group_members USING btree (group_id);


--
-- Name: idx_cl_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cl_created ON public.compliance_log USING btree (created_at);


--
-- Name: idx_cl_event; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cl_event ON public.compliance_log USING btree (event_type);


--
-- Name: idx_col_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_source ON public.agent_collaboration USING btree (source_agent_id);


--
-- Name: idx_col_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_target ON public.agent_collaboration USING btree (target_agent_id);


--
-- Name: idx_eaa_accessor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eaa_accessor ON public.entity_access_audit USING btree (accessor_id);


--
-- Name: idx_eaa_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eaa_entity ON public.entity_access_audit USING btree (entity_id, entity_type);


--
-- Name: idx_edges_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edges_target ON public.entity_edges USING btree (target_id);


--
-- Name: idx_edges_target_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edges_target_type ON public.entity_edges USING btree (target_id, edge_type);


--
-- Name: idx_edges_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edges_type ON public.entity_edges USING btree (edge_type);


--
-- Name: idx_ee_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ee_embedding ON public.entity_embeddings USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_et_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_et_tag ON public.entity_tags USING btree (tag_id);


--
-- Name: idx_hm_exec_mode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hm_exec_mode ON public.harness_meta USING btree (execution_mode);


--
-- Name: idx_km_difficulty; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_km_difficulty ON public.knowledge_meta USING btree (difficulty);


--
-- Name: idx_km_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_km_domain ON public.knowledge_meta USING btree (domain);


--
-- Name: idx_km_next_review; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_km_next_review ON public.knowledge_meta USING btree (next_review) WHERE (next_review IS NOT NULL);


--
-- Name: idx_km_topic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_km_topic ON public.knowledge_meta USING btree (topic);


--
-- Name: idx_sat_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sat_hash ON public.skill_access_token USING btree (token_hash);


--
-- Name: idx_sat_skill; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sat_skill ON public.skill_access_token USING btree (skill_id);


--
-- Name: idx_skm_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_skm_name ON public.skill_meta USING btree (skill_name);


--
-- Name: idx_skm_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_skm_status ON public.skill_meta USING btree (status);


--
-- Name: idx_skm_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_skm_type ON public.skill_meta USING btree (skill_type);


--
-- Name: idx_sm_branch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sm_branch ON public.spec_meta USING btree (branch_id) WHERE (branch_id IS NOT NULL);


--
-- Name: idx_sm_complexity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sm_complexity ON public.spec_meta USING btree (complexity);


--
-- Name: idx_sm_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sm_scope ON public.spec_meta USING btree (spec_scope) WHERE (spec_scope IS NOT NULL);


--
-- Name: idx_sm_spec_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sm_spec_status ON public.spec_meta USING btree (spec_status);


--
-- Name: idx_spl_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spl_plan ON public.spec_plan_links USING btree (plan_id);


--
-- Name: idx_spl_spec; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spl_spec ON public.spec_plan_links USING btree (spec_id);


--
-- Name: idx_tcs_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tcs_plan ON public.task_context_snapshots USING btree (plan_id);


--
-- Name: idx_td_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_td_source ON public.task_dependencies USING btree (source_plan_id);


--
-- Name: idx_td_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_td_target ON public.task_dependencies USING btree (target_plan_id);


--
-- Name: idx_tp_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tp_agent ON ONLY public.task_plans USING btree (agent_id);


--
-- Name: idx_tp_branch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tp_branch ON ONLY public.task_plans USING btree (branch_id);


--
-- Name: idx_ts_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ts_plan ON public.task_steps USING btree (plan_id);


--
-- Name: idx_ttc_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ttc_plan ON public.task_tool_calls USING btree (plan_id);


--
-- Name: idx_ttc_step; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ttc_step ON public.task_tool_calls USING btree (step_id);


--
-- Name: idx_wc_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wc_agent ON public.workspace_context USING btree (agent_id);


--
-- Name: idx_wc_branch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wc_branch ON public.workspace_context USING btree (branch_id);


--
-- Name: idx_wc_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wc_type ON public.workspace_context USING btree (context_type);


--
-- Name: idx_wc_visibility; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wc_visibility ON public.workspace_context USING btree (visibility);


--
-- Name: idx_wc_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wc_workspace ON public.workspace_context USING btree (workspace_id);


--
-- Name: idx_wca_context; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wca_context ON public.workspace_context_audit USING btree (context_id);


--
-- Name: idx_wca_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wca_workspace ON public.workspace_context_audit USING btree (workspace_id);


--
-- Name: idx_ws_alias; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ws_alias ON public.workspaces USING btree (workspace_alias);


--
-- Name: idx_ws_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ws_owner ON public.workspaces USING btree (owner_user_id);


--
-- Name: idx_ws_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ws_status ON public.workspaces USING btree (status);


--
-- Name: task_plans_active_agent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_active_agent_id_idx ON public.task_plans_active USING btree (agent_id);


--
-- Name: task_plans_active_branch_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_active_branch_id_idx ON public.task_plans_active USING btree (branch_id);


--
-- Name: task_plans_cancelled_agent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_cancelled_agent_id_idx ON public.task_plans_cancelled USING btree (agent_id);


--
-- Name: task_plans_cancelled_branch_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_cancelled_branch_id_idx ON public.task_plans_cancelled USING btree (branch_id);


--
-- Name: task_plans_completed_agent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_completed_agent_id_idx ON public.task_plans_completed USING btree (agent_id);


--
-- Name: task_plans_completed_branch_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_completed_branch_id_idx ON public.task_plans_completed USING btree (branch_id);


--
-- Name: task_plans_default_agent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_default_agent_id_idx ON public.task_plans_default USING btree (agent_id);


--
-- Name: task_plans_default_branch_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_default_branch_id_idx ON public.task_plans_default USING btree (branch_id);


--
-- Name: task_plans_paused_agent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_paused_agent_id_idx ON public.task_plans_paused USING btree (agent_id);


--
-- Name: task_plans_paused_branch_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX task_plans_paused_branch_id_idx ON public.task_plans_paused USING btree (branch_id);


--
-- Name: agent_session_active_agent_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_agent ATTACH PARTITION public.agent_session_active_agent_id_idx;


--
-- Name: agent_session_active_owner_user_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_owner ATTACH PARTITION public.agent_session_active_owner_user_id_idx;


--
-- Name: agent_session_active_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_agent_session ATTACH PARTITION public.agent_session_active_pkey;


--
-- Name: agent_session_active_predecessor_session_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_predecessor ATTACH PARTITION public.agent_session_active_predecessor_session_id_idx;


--
-- Name: agent_session_active_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_workspace ATTACH PARTITION public.agent_session_active_workspace_id_idx;


--
-- Name: agent_session_inactive_agent_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_agent ATTACH PARTITION public.agent_session_inactive_agent_id_idx;


--
-- Name: agent_session_inactive_owner_user_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_owner ATTACH PARTITION public.agent_session_inactive_owner_user_id_idx;


--
-- Name: agent_session_inactive_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_agent_session ATTACH PARTITION public.agent_session_inactive_pkey;


--
-- Name: agent_session_inactive_predecessor_session_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_predecessor ATTACH PARTITION public.agent_session_inactive_predecessor_session_id_idx;


--
-- Name: agent_session_inactive_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_as_workspace ATTACH PARTITION public.agent_session_inactive_workspace_id_idx;


--
-- Name: entities_default_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_default_category_idx;


--
-- Name: entities_default_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_default_owned_by_agent_idx;


--
-- Name: entities_default_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_default_pkey;


--
-- Name: entities_default_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_default_search_vector_idx;


--
-- Name: entities_default_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_default_status_idx;


--
-- Name: entities_default_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_default_visibility_idx;


--
-- Name: entities_default_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_default_workspace_id_idx;


--
-- Name: entities_experience_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_experience_category_idx;


--
-- Name: entities_experience_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_experience_owned_by_agent_idx;


--
-- Name: entities_experience_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_experience_pkey;


--
-- Name: entities_experience_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_experience_search_vector_idx;


--
-- Name: entities_experience_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_experience_status_idx;


--
-- Name: entities_experience_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_experience_visibility_idx;


--
-- Name: entities_experience_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_experience_workspace_id_idx;


--
-- Name: entities_harness_template_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_harness_template_category_idx;


--
-- Name: entities_harness_template_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_harness_template_owned_by_agent_idx;


--
-- Name: entities_harness_template_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_harness_template_pkey;


--
-- Name: entities_harness_template_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_harness_template_search_vector_idx;


--
-- Name: entities_harness_template_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_harness_template_status_idx;


--
-- Name: entities_harness_template_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_harness_template_visibility_idx;


--
-- Name: entities_harness_template_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_harness_template_workspace_id_idx;


--
-- Name: entities_knowledge_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_knowledge_category_idx;


--
-- Name: entities_knowledge_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_knowledge_owned_by_agent_idx;


--
-- Name: entities_knowledge_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_knowledge_pkey;


--
-- Name: entities_knowledge_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_knowledge_search_vector_idx;


--
-- Name: entities_knowledge_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_knowledge_status_idx;


--
-- Name: entities_knowledge_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_knowledge_visibility_idx;


--
-- Name: entities_knowledge_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_knowledge_workspace_id_idx;


--
-- Name: entities_memory_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_memory_category_idx;


--
-- Name: entities_memory_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_memory_owned_by_agent_idx;


--
-- Name: entities_memory_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_memory_pkey;


--
-- Name: entities_memory_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_memory_search_vector_idx;


--
-- Name: entities_memory_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_memory_status_idx;


--
-- Name: entities_memory_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_memory_visibility_idx;


--
-- Name: entities_memory_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_memory_workspace_id_idx;


--
-- Name: entities_other_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_other_category_idx;


--
-- Name: entities_other_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_other_owned_by_agent_idx;


--
-- Name: entities_other_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_other_pkey;


--
-- Name: entities_other_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_other_search_vector_idx;


--
-- Name: entities_other_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_other_status_idx;


--
-- Name: entities_other_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_other_visibility_idx;


--
-- Name: entities_other_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_other_workspace_id_idx;


--
-- Name: entities_skill_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_skill_category_idx;


--
-- Name: entities_skill_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_skill_owned_by_agent_idx;


--
-- Name: entities_skill_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_skill_pkey;


--
-- Name: entities_skill_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_skill_search_vector_idx;


--
-- Name: entities_skill_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_skill_status_idx;


--
-- Name: entities_skill_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_skill_visibility_idx;


--
-- Name: entities_skill_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_skill_workspace_id_idx;


--
-- Name: entities_spec_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_spec_category_idx;


--
-- Name: entities_spec_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_spec_owned_by_agent_idx;


--
-- Name: entities_spec_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_spec_pkey;


--
-- Name: entities_spec_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_spec_search_vector_idx;


--
-- Name: entities_spec_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_spec_status_idx;


--
-- Name: entities_spec_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_spec_visibility_idx;


--
-- Name: entities_spec_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_spec_workspace_id_idx;


--
-- Name: entities_task_output_category_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_category ATTACH PARTITION public.entities_task_output_category_idx;


--
-- Name: entities_task_output_owned_by_agent_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_owned_by ATTACH PARTITION public.entities_task_output_owned_by_agent_idx;


--
-- Name: entities_task_output_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_entities ATTACH PARTITION public.entities_task_output_pkey;


--
-- Name: entities_task_output_search_vector_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_search ATTACH PARTITION public.entities_task_output_search_vector_idx;


--
-- Name: entities_task_output_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_status ATTACH PARTITION public.entities_task_output_status_idx;


--
-- Name: entities_task_output_visibility_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_visibility ATTACH PARTITION public.entities_task_output_visibility_idx;


--
-- Name: entities_task_output_workspace_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_entities_workspace ATTACH PARTITION public.entities_task_output_workspace_id_idx;


--
-- Name: entity_access_log_202605_access_time_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_eal_time ATTACH PARTITION public.entity_access_log_202605_access_time_idx;


--
-- Name: entity_access_log_202605_entity_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_eal_entity ATTACH PARTITION public.entity_access_log_202605_entity_id_idx;


--
-- Name: entity_access_log_202606_access_time_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_eal_time ATTACH PARTITION public.entity_access_log_202606_access_time_idx;


--
-- Name: entity_access_log_202606_entity_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_eal_entity ATTACH PARTITION public.entity_access_log_202606_entity_id_idx;


--
-- Name: entity_access_log_max_access_time_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_eal_time ATTACH PARTITION public.entity_access_log_max_access_time_idx;


--
-- Name: entity_access_log_max_entity_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_eal_entity ATTACH PARTITION public.entity_access_log_max_entity_id_idx;


--
-- Name: task_plans_active_agent_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_agent ATTACH PARTITION public.task_plans_active_agent_id_idx;


--
-- Name: task_plans_active_branch_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_branch ATTACH PARTITION public.task_plans_active_branch_id_idx;


--
-- Name: task_plans_active_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_task_plans ATTACH PARTITION public.task_plans_active_pkey;


--
-- Name: task_plans_cancelled_agent_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_agent ATTACH PARTITION public.task_plans_cancelled_agent_id_idx;


--
-- Name: task_plans_cancelled_branch_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_branch ATTACH PARTITION public.task_plans_cancelled_branch_id_idx;


--
-- Name: task_plans_cancelled_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_task_plans ATTACH PARTITION public.task_plans_cancelled_pkey;


--
-- Name: task_plans_completed_agent_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_agent ATTACH PARTITION public.task_plans_completed_agent_id_idx;


--
-- Name: task_plans_completed_branch_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_branch ATTACH PARTITION public.task_plans_completed_branch_id_idx;


--
-- Name: task_plans_completed_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_task_plans ATTACH PARTITION public.task_plans_completed_pkey;


--
-- Name: task_plans_default_agent_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_agent ATTACH PARTITION public.task_plans_default_agent_id_idx;


--
-- Name: task_plans_default_branch_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_branch ATTACH PARTITION public.task_plans_default_branch_id_idx;


--
-- Name: task_plans_default_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_task_plans ATTACH PARTITION public.task_plans_default_pkey;


--
-- Name: task_plans_paused_agent_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_agent ATTACH PARTITION public.task_plans_paused_agent_id_idx;


--
-- Name: task_plans_paused_branch_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_tp_branch ATTACH PARTITION public.task_plans_paused_branch_id_idx;


--
-- Name: task_plans_paused_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_task_plans ATTACH PARTITION public.task_plans_paused_pkey;


--
-- Name: agent_registry trg_agent_registry_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_agent_registry_updated_at BEFORE UPDATE ON public.agent_registry FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: collab_groups trg_collab_groups_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_collab_groups_updated_at BEFORE UPDATE ON public.collab_groups FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: entities trg_entities_search_vector; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_entities_search_vector BEFORE INSERT OR UPDATE OF title, summary, content ON public.entities FOR EACH ROW EXECUTE FUNCTION public.entities_search_vector_update();


--
-- Name: skill_meta trg_skill_meta_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_skill_meta_updated_at BEFORE UPDATE ON public.skill_meta FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: system_config trg_system_config_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_system_config_updated_at BEFORE UPDATE ON public.system_config FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: system_users trg_system_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_system_users_updated_at BEFORE UPDATE ON public.system_users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: task_plans trg_task_plans_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_task_plans_updated_at BEFORE UPDATE ON public.task_plans FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: workspaces trg_workspaces_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workspaces_updated_at BEFORE UPDATE ON public.workspaces FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: agent_credentials fk_ac_agent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_credentials
    ADD CONSTRAINT fk_ac_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: agent_registry fk_ar_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_registry
    ADD CONSTRAINT fk_ar_created_by FOREIGN KEY (created_by_agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: branch_merge_log fk_bml_src; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.branch_merge_log
    ADD CONSTRAINT fk_bml_src FOREIGN KEY (source_branch_id) REFERENCES public.context_branches(branch_id);


--
-- Name: branch_merge_log fk_bml_tgt; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.branch_merge_log
    ADD CONSTRAINT fk_bml_tgt FOREIGN KEY (target_branch_id) REFERENCES public.context_branches(branch_id);


--
-- Name: context_branches fk_cb_agent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_branches
    ADD CONSTRAINT fk_cb_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: context_branches fk_cb_parent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_branches
    ADD CONSTRAINT fk_cb_parent FOREIGN KEY (parent_branch_id) REFERENCES public.context_branches(branch_id) ON DELETE SET NULL;


--
-- Name: context_branches fk_cb_workspace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_branches
    ADD CONSTRAINT fk_cb_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(workspace_id) ON DELETE CASCADE;


--
-- Name: collab_groups fk_cg_branch; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_groups
    ADD CONSTRAINT fk_cg_branch FOREIGN KEY (branch_id) REFERENCES public.context_branches(branch_id) ON DELETE SET NULL;


--
-- Name: collab_groups fk_cg_coordinator; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_groups
    ADD CONSTRAINT fk_cg_coordinator FOREIGN KEY (coordinator_agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: collab_groups fk_cg_workspace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_groups
    ADD CONSTRAINT fk_cg_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(workspace_id);


--
-- Name: collab_group_members fk_cgm_agent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_group_members
    ADD CONSTRAINT fk_cgm_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: collab_group_members fk_cgm_group; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_group_members
    ADD CONSTRAINT fk_cgm_group FOREIGN KEY (group_id) REFERENCES public.collab_groups(group_id) ON DELETE CASCADE;


--
-- Name: collab_group_members fk_cgm_workspace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collab_group_members
    ADD CONSTRAINT fk_cgm_workspace FOREIGN KEY (personal_workspace_id) REFERENCES public.workspaces(workspace_id);


--
-- Name: agent_collaboration fk_col_source; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_collaboration
    ADD CONSTRAINT fk_col_source FOREIGN KEY (source_agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: agent_collaboration fk_col_target; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_collaboration
    ADD CONSTRAINT fk_col_target FOREIGN KEY (target_agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: entity_access_log fk_eal_agent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.entity_access_log
    ADD CONSTRAINT fk_eal_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: entity_edges fk_edge_source; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_edges
    ADD CONSTRAINT fk_edge_source FOREIGN KEY (source_id, source_type) REFERENCES public.entities(entity_id, entity_type) ON DELETE CASCADE;


--
-- Name: entities fk_entities_workspace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.entities
    ADD CONSTRAINT fk_entities_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(workspace_id);


--
-- Name: entity_tags fk_et_entity; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_tags
    ADD CONSTRAINT fk_et_entity FOREIGN KEY (entity_id, entity_type) REFERENCES public.entities(entity_id, entity_type) ON DELETE CASCADE;


--
-- Name: entity_tags fk_et_tag; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_tags
    ADD CONSTRAINT fk_et_tag FOREIGN KEY (tag_id) REFERENCES public.tags(tag_id);


--
-- Name: knowledge_meta fk_km_entity; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_meta
    ADD CONSTRAINT fk_km_entity FOREIGN KEY (entity_id, entity_type) REFERENCES public.entities(entity_id, entity_type) ON DELETE CASCADE;


--
-- Name: agent_session fk_session_agent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.agent_session
    ADD CONSTRAINT fk_session_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: agent_session fk_session_branch; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.agent_session
    ADD CONSTRAINT fk_session_branch FOREIGN KEY (branch_id) REFERENCES public.context_branches(branch_id) ON DELETE SET NULL;


--
-- Name: agent_session fk_session_workspace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.agent_session
    ADD CONSTRAINT fk_session_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(workspace_id);


--
-- Name: task_steps fk_step_plan; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_steps
    ADD CONSTRAINT fk_step_plan FOREIGN KEY (plan_id, plan_status) REFERENCES public.task_plans(plan_id, status);


--
-- Name: task_plans fk_tp_agent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.task_plans
    ADD CONSTRAINT fk_tp_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: task_plans fk_tp_branch; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.task_plans
    ADD CONSTRAINT fk_tp_branch FOREIGN KEY (branch_id) REFERENCES public.context_branches(branch_id) ON DELETE SET NULL;


--
-- Name: workspace_context fk_wc_agent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_context
    ADD CONSTRAINT fk_wc_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id);


--
-- Name: workspace_context fk_wc_branch; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_context
    ADD CONSTRAINT fk_wc_branch FOREIGN KEY (branch_id) REFERENCES public.context_branches(branch_id) ON DELETE SET NULL;


--
-- Name: workspace_context fk_wc_parent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_context
    ADD CONSTRAINT fk_wc_parent FOREIGN KEY (parent_context_id) REFERENCES public.workspace_context(context_id) ON DELETE SET NULL;


--
-- Name: workspace_context fk_wc_workspace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_context
    ADD CONSTRAINT fk_wc_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(workspace_id) ON DELETE CASCADE;


--
-- Name: workspace_tasks fk_wt_workspace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_tasks
    ADD CONSTRAINT fk_wt_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(workspace_id) ON DELETE CASCADE;


--
-- v4.0.1: bind Business Agent identity to the authenticated database role.
CREATE TABLE IF NOT EXISTS public.agent_db_identity (
    role_name name PRIMARY KEY,
    agent_id varchar(64) NOT NULL UNIQUE
        REFERENCES public.agent_registry(agent_id) ON DELETE CASCADE
);

REVOKE ALL ON public.agent_db_identity FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.current_agent_identity()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT COALESCE(
        (SELECT identity.agent_id::text
           FROM public.agent_db_identity AS identity
          WHERE identity.role_name = current_user),
        current_setting('app.current_agent_id', true)
    )
$$;

-- Name: agent_credentials ac_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY ac_agent_isolation ON public.agent_credentials USING (((agent_id)::text = public.current_agent_identity()));


--
-- Name: agent_collaboration; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.agent_collaboration ENABLE ROW LEVEL SECURITY;

--
-- Name: agent_credentials; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.agent_credentials ENABLE ROW LEVEL SECURITY;

--
-- Name: agent_permission_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.agent_permission_log ENABLE ROW LEVEL SECURITY;

--
-- Name: agent_session; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.agent_session ENABLE ROW LEVEL SECURITY;

--
-- Name: agent_permission_log apl_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY apl_agent_isolation ON public.agent_permission_log USING ((((agent_id)::text = public.current_agent_identity()) OR (EXISTS ( SELECT 1
   FROM public.agent_registry ar
  WHERE (((ar.agent_id)::text = public.current_agent_identity()) AND ((ar.agent_role)::text = 'COORDINATOR'::text))))));


--
-- Name: agent_session as_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY as_agent_isolation ON public.agent_session USING ((((agent_id)::text = public.current_agent_identity()) OR (EXISTS ( SELECT 1
   FROM public.agent_registry ar
  WHERE (((ar.agent_id)::text = public.current_agent_identity()) AND ((ar.agent_role)::text = 'COORDINATOR'::text))))));


--
-- Name: branch_merge_log bml_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY bml_agent_isolation ON public.branch_merge_log USING ((EXISTS ( SELECT 1
   FROM public.context_branches b
  WHERE ((b.branch_id = ANY (ARRAY[branch_merge_log.source_branch_id, branch_merge_log.target_branch_id])) AND (EXISTS ( SELECT 1
           FROM public.workspaces w
          WHERE ((w.workspace_id = b.workspace_id) AND (((w.isolation_mode)::text = 'SHARED'::text) OR ((w.current_agent_id)::text = public.current_agent_identity())))))))));


--
-- Name: branch_merge_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.branch_merge_log ENABLE ROW LEVEL SECURITY;

--
-- Name: context_branches cb_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cb_agent_isolation ON public.context_branches USING ((EXISTS ( SELECT 1
   FROM public.workspaces w
  WHERE ((w.workspace_id = context_branches.workspace_id) AND (((w.isolation_mode)::text = 'SHARED'::text) OR ((w.current_agent_id)::text = public.current_agent_identity()))))));


--
-- Name: compliance_log cl_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cl_aiadmin ON public.compliance_log TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: agent_collaboration col_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY col_agent_isolation ON public.agent_collaboration USING ((((source_agent_id)::text = public.current_agent_identity()) OR ((target_agent_id)::text = public.current_agent_identity())));


--
-- Name: collab_group_members; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.collab_group_members ENABLE ROW LEVEL SECURITY;

--
-- Name: collab_groups; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.collab_groups ENABLE ROW LEVEL SECURITY;

--
-- Name: compliance_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.compliance_log ENABLE ROW LEVEL SECURITY;

--
-- Name: context_branches; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.context_branches ENABLE ROW LEVEL SECURITY;

--
-- Name: entity_access_audit eaa_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY eaa_aiadmin ON public.entity_access_audit TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: entity_access_audit eaa_end_user; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY eaa_end_user ON public.entity_access_audit FOR SELECT USING (((accessor_id)::text = public.current_agent_identity()));


--
-- Name: entity_access_log eal_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY eal_agent_isolation ON public.entity_access_log USING ((((agent_id)::text = public.current_agent_identity()) OR (EXISTS ( SELECT 1
   FROM public.agent_registry ar
  WHERE (((ar.agent_id)::text = public.current_agent_identity()) AND ((ar.agent_role)::text = 'COORDINATOR'::text))))));


--
-- Name: entity_edges edges_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY edges_agent_isolation ON public.entity_edges USING ((EXISTS ( SELECT 1
   FROM public.entities e
  WHERE ((e.entity_id = entity_edges.source_id) AND ((e.entity_type)::text = (entity_edges.source_type)::text) AND (((e.visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])) OR (((e.visibility)::text = 'PRIVATE'::text) AND ((e.owned_by_agent)::text = public.current_agent_identity())))))));


--
-- Name: entities; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.entities ENABLE ROW LEVEL SECURITY;

--
-- Name: entities entities_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY entities_agent_isolation ON public.entities USING ((((visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])) OR (((visibility)::text = 'PRIVATE'::text) AND ((owned_by_agent)::text = public.current_agent_identity()))));


--
-- Name: entity_access_audit; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.entity_access_audit ENABLE ROW LEVEL SECURITY;

--
-- Name: entity_access_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.entity_access_log ENABLE ROW LEVEL SECURITY;

--
-- Name: entity_edges; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.entity_edges ENABLE ROW LEVEL SECURITY;

--
-- Name: entity_tags; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.entity_tags ENABLE ROW LEVEL SECURITY;

--
-- Name: entity_tags et_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY et_agent_isolation ON public.entity_tags USING ((EXISTS ( SELECT 1
   FROM public.entities e
  WHERE ((e.entity_id = entity_tags.entity_id) AND ((e.entity_type)::text = (entity_tags.entity_type)::text) AND (((e.visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])) OR (((e.visibility)::text = 'PRIVATE'::text) AND ((e.owned_by_agent)::text = public.current_agent_identity())))))));


--
-- Name: harness_meta; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.harness_meta ENABLE ROW LEVEL SECURITY;

--
-- Name: harness_meta harness_meta_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY harness_meta_aiadmin ON public.harness_meta TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: harness_meta harness_meta_end_user; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY harness_meta_end_user ON public.harness_meta USING ((EXISTS ( SELECT 1
   FROM public.entities e
  WHERE ((e.entity_id = harness_meta.entity_id) AND ((e.entity_type)::text = (harness_meta.entity_type)::text) AND (((e.owned_by_agent)::text = public.current_agent_identity()) OR ((e.visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))))));


--
-- Name: knowledge_meta; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.knowledge_meta ENABLE ROW LEVEL SECURITY;

--
-- Name: knowledge_meta knowledge_meta_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY knowledge_meta_aiadmin ON public.knowledge_meta TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: knowledge_meta knowledge_meta_end_user; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY knowledge_meta_end_user ON public.knowledge_meta USING ((EXISTS ( SELECT 1
   FROM public.entities e
  WHERE ((e.entity_id = knowledge_meta.entity_id) AND ((e.entity_type)::text = (knowledge_meta.entity_type)::text) AND (((e.owned_by_agent)::text = public.current_agent_identity()) OR ((e.visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))))));


--
-- Name: ldap_config ldap_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY ldap_aiadmin ON public.ldap_config TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: ldap_config; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.ldap_config ENABLE ROW LEVEL SECURITY;

--
-- Name: skill_access_token sat_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY sat_aiadmin ON public.skill_access_token TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: skill_access_token sat_end_user; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY sat_end_user ON public.skill_access_token FOR SELECT USING (((requested_by)::text = public.current_agent_identity()));


--
-- Name: skill_access_token; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.skill_access_token ENABLE ROW LEVEL SECURITY;

--
-- Name: skill_meta; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.skill_meta ENABLE ROW LEVEL SECURITY;

--
-- Name: skill_meta skm_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY skm_agent_isolation ON public.skill_meta USING ((((visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])) OR (((visibility)::text = 'PRIVATE'::text) AND ((owned_by_agent)::text = public.current_agent_identity()))));


--
-- Name: spec_meta; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.spec_meta ENABLE ROW LEVEL SECURITY;

--
-- Name: spec_meta spec_meta_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY spec_meta_aiadmin ON public.spec_meta TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: spec_meta spec_meta_end_user; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY spec_meta_end_user ON public.spec_meta USING ((EXISTS ( SELECT 1
   FROM public.entities e
  WHERE ((e.entity_id = spec_meta.entity_id) AND ((e.entity_type)::text = (spec_meta.entity_type)::text) AND (((e.owned_by_agent)::text = public.current_agent_identity()) OR ((e.visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])))))));


--
-- Name: spec_plan_links; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.spec_plan_links ENABLE ROW LEVEL SECURITY;

--
-- Name: spec_plan_links spl_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY spl_agent_isolation ON public.spec_plan_links USING ((EXISTS ( SELECT 1
   FROM public.entities e
  WHERE ((e.entity_id = spec_plan_links.spec_id) AND (((e.visibility)::text = ANY (ARRAY[('SHARED'::character varying)::text, ('PUBLIC'::character varying)::text])) OR (((e.visibility)::text = 'PRIVATE'::text) AND ((e.owned_by_agent)::text = public.current_agent_identity())))))));


--
-- Name: task_plans; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.task_plans ENABLE ROW LEVEL SECURITY;

--
-- Name: task_steps; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.task_steps ENABLE ROW LEVEL SECURITY;

--
-- Name: workspace_context wc_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY wc_agent_isolation ON public.workspace_context USING ((EXISTS ( SELECT 1
   FROM public.workspaces w
  WHERE ((w.workspace_id = workspace_context.workspace_id) AND (((w.isolation_mode)::text = 'SHARED'::text) OR ((w.current_agent_id)::text = public.current_agent_identity()))))));


--
-- Name: workspace_context_audit wca_aiadmin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY wca_aiadmin ON public.workspace_context_audit TO :"schema_owner" USING (true) WITH CHECK (true);


--
-- Name: workspace_context; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.workspace_context ENABLE ROW LEVEL SECURITY;

--
-- Name: workspace_context_audit; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.workspace_context_audit ENABLE ROW LEVEL SECURITY;

--
-- Name: workspace_tasks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.workspace_tasks ENABLE ROW LEVEL SECURITY;

--
-- Name: workspaces; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;

--
-- Name: workspaces ws_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY ws_agent_isolation ON public.workspaces USING ((((isolation_mode)::text = 'SHARED'::text) OR ((owner_user_id)::text = public.current_agent_identity()) OR ((current_agent_id)::text = public.current_agent_identity())));


--
-- Name: workspace_tasks wt_agent_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY wt_agent_isolation ON public.workspace_tasks USING ((EXISTS ( SELECT 1
   FROM public.workspaces w
  WHERE ((w.workspace_id = workspace_tasks.workspace_id) AND (((w.isolation_mode)::text = 'SHARED'::text) OR ((w.current_agent_id)::text = public.current_agent_identity()))))));


-- ============================================================================
-- Loop Engineering Tables [NEW v3.7.5]
-- ============================================================================

-- Add LOOP_DEFINITION to entities type constraint
ALTER TABLE public.entities DROP CONSTRAINT IF EXISTS ck_entities_type;
ALTER TABLE public.entities ADD CONSTRAINT ck_entities_type
    CHECK (entity_type IN ('MEMORY','KNOWLEDGE','TASK_OUTPUT','EXPERIENCE','HARNESS_TEMPLATE','SPEC','SKILL','LOOP_DEFINITION','OTHER'));

-- 24. loop_meta (sidecar to entities, like harness_meta)
CREATE TABLE IF NOT EXISTS public.loop_meta (
    entity_id           BIGINT       NOT NULL,
    entity_type         VARCHAR(32)  DEFAULT 'LOOP_DEFINITION' NOT NULL,
    loop_version        VARCHAR(32)  DEFAULT '1.0' NOT NULL,
    goal_definition     JSONB        NOT NULL,
    stop_conditions     JSONB        NOT NULL,
    evaluation_config   JSONB        NOT NULL,
    trigger_config      JSONB,
    harness_template_id BIGINT,
    workspace_id        BIGINT,
    branch_id           BIGINT,
    spec_id             BIGINT,
    parent_loop_id      BIGINT,
    collab_group_id     BIGINT,
    CONSTRAINT pk_loop_meta PRIMARY KEY (entity_id, entity_type),
    CONSTRAINT fk_lm_entity FOREIGN KEY (entity_id, entity_type) REFERENCES public.entities(entity_id, entity_type) ON DELETE CASCADE,
    CONSTRAINT fk_lm_collab FOREIGN KEY (collab_group_id) REFERENCES public.collab_groups(group_id),
    CONSTRAINT ck_lm_entity_type CHECK (entity_type = 'LOOP_DEFINITION')
);

-- 25. loop_runs (partitioned by LIST(status) like task_plans)
CREATE TABLE IF NOT EXISTS public.loop_runs (
    run_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loop_id          BIGINT       NOT NULL,
    agent_id         VARCHAR(64)  NOT NULL,
    trigger_type     VARCHAR(32)  DEFAULT 'MANUAL' NOT NULL,
    trigger_source   VARCHAR(256),
    status           VARCHAR(30)  DEFAULT 'PENDING' NOT NULL,
    iteration_count  INTEGER      DEFAULT 0 NOT NULL,
    total_tokens     BIGINT       DEFAULT 0 NOT NULL,
    final_result     VARCHAR(4000),
    error_message    VARCHAR(2000),
    parent_run_id    BIGINT,
    started_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at     TIMESTAMP,
    CONSTRAINT fk_lr_agent FOREIGN KEY (agent_id) REFERENCES public.agent_registry(agent_id),
    CONSTRAINT fk_lr_parent_run FOREIGN KEY (parent_run_id) REFERENCES public.loop_runs(run_id),
    CONSTRAINT ck_lr_status CHECK (status IN ('PENDING','RUNNING','PAUSED','COMPLETED','STOPPED','FAILED','TIMEOUT')),
    CONSTRAINT ck_lr_trigger CHECK (trigger_type IN ('MANUAL','SCHEDULE','EVENT','HOOK'))
);

CREATE INDEX IF NOT EXISTS idx_lr_loop ON public.loop_runs(loop_id);
CREATE INDEX IF NOT EXISTS idx_lr_agent ON public.loop_runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_lr_status ON public.loop_runs(status);
CREATE INDEX IF NOT EXISTS idx_lr_parent_run ON public.loop_runs(parent_run_id);

-- 26. loop_iterations (FK to loop_runs, like task_steps to task_plans)
CREATE TABLE IF NOT EXISTS public.loop_iterations (
    iteration_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id             BIGINT       NOT NULL,
    iteration_order    INTEGER      NOT NULL,
    plan_data          JSONB,
    actions            JSONB,
    observations       JSONB,
    evaluation_result  JSONB,
    evaluation_passed  VARCHAR(1)   DEFAULT 'N' NOT NULL,
    adjustment         JSONB,
    token_usage        BIGINT       DEFAULT 0 NOT NULL,
    started_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at       TIMESTAMP,
    CONSTRAINT fk_li_run FOREIGN KEY (run_id) REFERENCES public.loop_runs(run_id) ON DELETE CASCADE,
    CONSTRAINT ck_li_passed CHECK (evaluation_passed IN ('Y','N'))
);

CREATE INDEX IF NOT EXISTS idx_li_run ON public.loop_iterations(run_id);
CREATE INDEX IF NOT EXISTS idx_li_order ON public.loop_iterations(iteration_order);

-- 27. loop_hooks (non-partitioned, like context_branches)
CREATE TABLE IF NOT EXISTS public.loop_hooks (
    hook_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loop_id     BIGINT       NOT NULL,
    hook_event  VARCHAR(32)  NOT NULL,
    hook_type   VARCHAR(32)  NOT NULL,
    hook_config JSONB,
    priority    INTEGER      DEFAULT 5 NOT NULL,
    enabled     VARCHAR(1)   DEFAULT 'Y' NOT NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_lh_event CHECK (hook_event IN ('PRE_RUN','POST_ITERATION','ON_STOP','ON_FAIL','ON_TIMEOUT','ON_START')),
    CONSTRAINT ck_lh_type CHECK (hook_type IN ('WEBHOOK','SCRIPT','NOTIFICATION','LOG','MCP_CALL')),
    CONSTRAINT ck_lh_enabled CHECK (enabled IN ('Y','N')),
    CONSTRAINT ck_lh_priority CHECK (priority BETWEEN 1 AND 10)
);

CREATE INDEX IF NOT EXISTS idx_lh_loop ON public.loop_hooks(loop_id);

-- 27b. task_loop_binding
CREATE TABLE IF NOT EXISTS public.task_loop_binding (
    binding_id BIGSERIAL PRIMARY KEY,
    step_id BIGINT NOT NULL REFERENCES public.task_steps(step_id),
    loop_id BIGINT NOT NULL,
    binding_type VARCHAR(20) DEFAULT 'COMPLETION',
    auto_start VARCHAR(1) DEFAULT 'N',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT ck_tlb_type CHECK (binding_type IN ('COMPLETION','VALIDATION')),
    CONSTRAINT ck_tlb_auto CHECK (auto_start IN ('Y','N'))
);

CREATE INDEX IF NOT EXISTS idx_tlb_step ON public.task_loop_binding(step_id);
CREATE INDEX IF NOT EXISTS idx_tlb_loop ON public.task_loop_binding(loop_id);

-- 28. loop_audit [ENT-ONLY v3.7.5] - audit trail for loop lifecycle actions
CREATE TABLE IF NOT EXISTS public.loop_audit (
    audit_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loop_id         BIGINT,
    run_id          BIGINT,
    action_type     VARCHAR(32) NOT NULL,
    action_by       VARCHAR(64),
    collab_group_id BIGINT,
    action_detail   JSONB,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    -- loop_id references loop_meta(entity_id) but FK omitted because entities is partitioned with composite PK
    -- loop_id references run_id in loop_runs
    CONSTRAINT fk_la_run FOREIGN KEY (run_id) REFERENCES public.loop_runs(run_id) ON DELETE SET NULL,
    CONSTRAINT fk_la_collab FOREIGN KEY (collab_group_id) REFERENCES public.collab_groups(group_id) ON DELETE SET NULL,
    CONSTRAINT ck_la_action CHECK (action_type IN ('CREATE','UPDATE','DELETE','START_RUN','PAUSE_RUN','RESUME_RUN','STOP_RUN','RECORD_ITERATION','ADD_HOOK','REMOVE_HOOK','TIMEOUT','CLEANUP'))
);
CREATE INDEX IF NOT EXISTS idx_la_loop ON public.loop_audit(loop_id);
CREATE INDEX IF NOT EXISTS idx_la_run ON public.loop_audit(run_id);
CREATE INDEX IF NOT EXISTS idx_la_created ON public.loop_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_la_collab ON public.loop_audit(collab_group_id);
ALTER TABLE public.loop_audit ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS la_owner_all ON public.loop_audit;
CREATE POLICY la_owner_all ON public.loop_audit FOR ALL USING (current_user = :'schema_owner');

-- RLS Policies for Loop tables
ALTER TABLE public.loop_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loop_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loop_iterations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loop_hooks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lm_agent_isolation ON public.loop_meta;
CREATE POLICY lm_agent_isolation ON public.loop_meta
    USING (EXISTS (
        SELECT 1 FROM public.entities e
        WHERE e.entity_id = loop_meta.entity_id
        AND (e.owned_by_agent = public.current_agent_identity()
             OR e.visibility IN ('SHARED','PUBLIC'))
    ));

DROP POLICY IF EXISTS lr_agent_isolation ON public.loop_runs;
CREATE POLICY lr_agent_isolation ON public.loop_runs
    USING (agent_id = public.current_agent_identity()
           OR EXISTS (
               SELECT 1 FROM public.entities e
               JOIN public.loop_meta m ON e.entity_id = m.entity_id
               WHERE e.entity_id = loop_runs.loop_id
               AND e.visibility IN ('SHARED','PUBLIC')
           ));

DROP POLICY IF EXISTS li_agent_isolation ON public.loop_iterations;
CREATE POLICY li_agent_isolation ON public.loop_iterations
    USING (EXISTS (
        SELECT 1 FROM public.loop_runs r
        WHERE r.run_id = loop_iterations.run_id
        AND (r.agent_id = public.current_agent_identity()
             OR EXISTS (
                 SELECT 1 FROM public.entities e
                 JOIN public.loop_meta m ON e.entity_id = m.entity_id
                 WHERE e.entity_id = r.loop_id AND e.visibility IN ('SHARED','PUBLIC')
             ))
    ));

DROP POLICY IF EXISTS lh_agent_isolation ON public.loop_hooks;
CREATE POLICY lh_agent_isolation ON public.loop_hooks
    USING (EXISTS (
        SELECT 1 FROM public.entities e
        WHERE e.entity_id = loop_hooks.loop_id
        AND (e.owned_by_agent = public.current_agent_identity()
             OR e.visibility IN ('SHARED','PUBLIC'))
    ));

-- Allow aiadmin full access
DROP POLICY IF EXISTS lm_owner_all ON public.loop_meta;
CREATE POLICY lm_owner_all ON public.loop_meta FOR ALL USING (current_user = :'schema_owner');
DROP POLICY IF EXISTS lr_owner_all ON public.loop_runs;
CREATE POLICY lr_owner_all ON public.loop_runs FOR ALL USING (current_user = :'schema_owner');
DROP POLICY IF EXISTS li_owner_all ON public.loop_iterations;
CREATE POLICY li_owner_all ON public.loop_iterations FOR ALL USING (current_user = :'schema_owner');
DROP POLICY IF EXISTS lh_owner_all ON public.loop_hooks;
CREATE POLICY lh_owner_all ON public.loop_hooks FOR ALL USING (current_user = :'schema_owner');

CREATE INDEX IF NOT EXISTS idx_lm_spec ON public.loop_meta(spec_id);
CREATE INDEX IF NOT EXISTS idx_lm_parent_loop ON public.loop_meta(parent_loop_id);
CREATE INDEX IF NOT EXISTS idx_lm_collab ON public.loop_meta(collab_group_id);
CREATE INDEX IF NOT EXISTS idx_ts_loop ON public.task_steps(loop_id);
CREATE INDEX IF NOT EXISTS idx_ts_completion ON public.task_steps(step_completion_type);


--
-- PostgreSQL database dump complete
--

\unrestrict 76Wp7adbaBBB9zy9rLASF86x1AU573WukoerTf6PVwr4lSpRYkaX6XhZf6NLLFa


-- v3.7.5 Extensions
-- v3.7.5 Extensions: Agent Communication, Orchestration, Events, Observability, Tools
-- ============================================================

-- D5: Add TRACE_ID columns for distributed tracing
SET search_path TO public;
ALTER TABLE AGENT_SESSION ADD COLUMN IF NOT EXISTS TRACE_ID VARCHAR(64);


ALTER TABLE TASK_PLANS ADD COLUMN IF NOT EXISTS TRACE_ID VARCHAR(64);


ALTER TABLE LOOP_RUNS ADD COLUMN IF NOT EXISTS TRACE_ID VARCHAR(64);


ALTER TABLE TASK_TOOL_CALLS ADD COLUMN IF NOT EXISTS TRACE_ID VARCHAR(64);
ALTER TABLE TASK_TOOL_CALLS ADD COLUMN IF NOT EXISTS PARENT_TOOL_CALL_ID BIGINT REFERENCES TASK_TOOL_CALLS(CALL_ID);
CREATE INDEX IF NOT EXISTS IDX_TTC_TRACE ON TASK_TOOL_CALLS(TRACE_ID);
CREATE INDEX IF NOT EXISTS IDX_TTC_PARENT ON TASK_TOOL_CALLS(PARENT_TOOL_CALL_ID);

ALTER TABLE ENTITY_ACCESS_LOG ADD COLUMN IF NOT EXISTS TRACE_ID VARCHAR(64);
ALTER TABLE ENTITY_ACCESS_LOG ADD COLUMN IF NOT EXISTS DURATION_MS BIGINT;


ALTER TABLE WORKSPACE_CONTEXT ADD COLUMN IF NOT EXISTS TRACE_ID VARCHAR(64);

-- D6: Extend HARNESS_META with tool registry columns
ALTER TABLE HARNESS_META ADD COLUMN IF NOT EXISTS TOOL_SOURCE VARCHAR(32);
ALTER TABLE HARNESS_META ADD COLUMN IF NOT EXISTS TOOL_NAMESPACE VARCHAR(64);
ALTER TABLE HARNESS_META ADD COLUMN IF NOT EXISTS TOOL_VERSION VARCHAR(32);
ALTER TABLE HARNESS_META ADD COLUMN IF NOT EXISTS INPUT_SCHEMA JSONB;
ALTER TABLE HARNESS_META ADD COLUMN IF NOT EXISTS OUTPUT_SCHEMA JSONB;
ALTER TABLE HARNESS_META ADD COLUMN IF NOT EXISTS TOOL_ENABLED VARCHAR(1) DEFAULT 'Y';
CREATE INDEX IF NOT EXISTS IDX_HM_NS ON HARNESS_META(TOOL_NAMESPACE);
CREATE INDEX IF NOT EXISTS IDX_HM_SOURCE ON HARNESS_META(TOOL_SOURCE);

-- ============================================================
-- 35. COLLAB_MESSAGES (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE COLLAB_MESSAGES (
    MESSAGE_ID           VARCHAR(64)   PRIMARY KEY,
    GROUP_ID             BIGINT        NOT NULL,
    SENDER_AGENT_ID      VARCHAR(64)   NOT NULL,
    RECEIVER_AGENT_ID    VARCHAR(64),
    PARENT_MESSAGE_ID    VARCHAR(64),
    THREAD_ID            VARCHAR(64),
    SUBJECT              VARCHAR(500),
    BODY                 TEXT           NOT NULL,
    MESSAGE_TYPE         VARCHAR(32)   DEFAULT 'TEXT' NOT NULL,
    PRIORITY             VARCHAR(16)   DEFAULT 'NORMAL' NOT NULL,
    STATUS               VARCHAR(16)   DEFAULT 'SENT' NOT NULL,
    ATTACHMENT_ENTITY_ID BIGINT,
    READ_AT              TIMESTAMP,
    CREATED_AT           TIMESTAMP      DEFAULT NOW() NOT NULL,
    CONSTRAINT FK_CM_GROUP FOREIGN KEY (GROUP_ID) REFERENCES COLLAB_GROUPS(GROUP_ID) ON DELETE CASCADE,
    CONSTRAINT FK_CM_SENDER FOREIGN KEY (SENDER_AGENT_ID) REFERENCES AGENT_REGISTRY(AGENT_ID),
    CONSTRAINT FK_CM_RECEIVER FOREIGN KEY (RECEIVER_AGENT_ID) REFERENCES AGENT_REGISTRY(AGENT_ID),
    CONSTRAINT FK_CM_PARENT FOREIGN KEY (PARENT_MESSAGE_ID) REFERENCES COLLAB_MESSAGES(MESSAGE_ID) ON DELETE SET NULL,
    CONSTRAINT FK_CM_THREAD FOREIGN KEY (THREAD_ID) REFERENCES COLLAB_MESSAGES(MESSAGE_ID) ON DELETE SET NULL,
    CONSTRAINT CK_CM_TYPE CHECK (MESSAGE_TYPE IN ('TEXT','QUERY','RESPONSE','ALERT','NOTIFICATION','COMMAND','REPORT')),
    CONSTRAINT CK_CM_PRIORITY CHECK (PRIORITY IN ('LOW','NORMAL','HIGH','URGENT')),
    CONSTRAINT CK_CM_STATUS CHECK (STATUS IN ('SENT','DELIVERED','READ','DELETED'))
);
CREATE INDEX IDX_CM_GROUP ON COLLAB_MESSAGES(GROUP_ID, CREATED_AT DESC);
CREATE INDEX IDX_CM_RECEIVER ON COLLAB_MESSAGES(RECEIVER_AGENT_ID, STATUS, CREATED_AT DESC);
CREATE INDEX IDX_CM_SENDER ON COLLAB_MESSAGES(SENDER_AGENT_ID, CREATED_AT DESC);
CREATE INDEX IDX_CM_THREAD ON COLLAB_MESSAGES(THREAD_ID, CREATED_AT);

-- ============================================================
-- 36. STEP_RETRY_POLICY (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE STEP_RETRY_POLICY (
    POLICY_ID          VARCHAR(64)  PRIMARY KEY,
    STEP_ID           BIGINT       NOT NULL,
    MAX_RETRIES        INTEGER   DEFAULT 3,
    BACKOFF_SECONDS    INTEGER   DEFAULT 5,
    BACKOFF_MULTIPLIER NUMERIC(3,1)   DEFAULT 2.0,
    TIMEOUT_SECONDS    BIGINT,
    FALLBACK_ACTION    VARCHAR(32)  DEFAULT 'FAIL',
    RETRY_COUNT        INTEGER   DEFAULT 0,
    LAST_RETRY_AT      TIMESTAMP,
    CREATED_AT         TIMESTAMP     DEFAULT NOW() NOT NULL,
    CONSTRAINT FK_SRP_STEP FOREIGN KEY (STEP_ID) REFERENCES TASK_STEPS(STEP_ID) ON DELETE CASCADE,
    CONSTRAINT CK_SRP_FALLBACK CHECK (FALLBACK_ACTION IN ('FAIL','SKIP','USE_CACHED','NOTIFY_COORDINATOR'))
);
CREATE INDEX IDX_SRP_STEP ON STEP_RETRY_POLICY(STEP_ID);

-- ============================================================
-- 37. STEP_EXECUTION_PLAN (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE STEP_EXECUTION_PLAN (
    PLAN_ID            VARCHAR(64)  PRIMARY KEY,
    ROOT_PLAN_ID       BIGINT       NOT NULL,
    STEP_GROUP_ID      INTEGER,
    STEP_ORDER         INTEGER   NOT NULL,
    STEP_ID            BIGINT       NOT NULL,
    PARENT_STEP_ID     BIGINT,
    PARALLEL_GROUP     INTEGER,
    STATUS             VARCHAR(16)  DEFAULT 'PENDING',
    ASSIGNED_AGENT_ID  VARCHAR(64),
    STARTED_AT         TIMESTAMP,
    COMPLETED_AT       TIMESTAMP,
    CONSTRAINT FK_SEP_STEP FOREIGN KEY (STEP_ID) REFERENCES TASK_STEPS(STEP_ID),
    CONSTRAINT FK_SEP_AGENT FOREIGN KEY (ASSIGNED_AGENT_ID) REFERENCES AGENT_REGISTRY(AGENT_ID),
    CONSTRAINT CK_SEP_STATUS CHECK (STATUS IN ('PENDING','RUNNING','COMPLETED','FAILED','SKIPPED','BLOCKED'))
);
CREATE INDEX IDX_SEP_PLAN ON STEP_EXECUTION_PLAN(ROOT_PLAN_ID, STEP_ORDER);
CREATE INDEX IDX_SEP_STATUS ON STEP_EXECUTION_PLAN(STATUS);

-- ============================================================
-- 38. EVENT_LOG (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE EVENT_LOG (
    EVENT_ID     VARCHAR(64)  PRIMARY KEY,
    EVENT_TYPE   VARCHAR(64)  NOT NULL,
    SOURCE_ID    VARCHAR(64),
    SOURCE_TYPE  VARCHAR(32),
    PAYLOAD      JSONB,
    CREATED_AT   TIMESTAMP     DEFAULT NOW() NOT NULL
);
CREATE INDEX IDX_EL_TYPE ON EVENT_LOG(EVENT_TYPE, CREATED_AT DESC);
CREATE INDEX IDX_EL_SOURCE ON EVENT_LOG(SOURCE_ID, EVENT_TYPE);

-- ============================================================
-- 39. EVENT_SUBSCRIPTIONS (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE EVENT_SUBSCRIPTIONS (
    SUB_ID         VARCHAR(64)  PRIMARY KEY,
    AGENT_ID       VARCHAR(64)  NOT NULL,
    EVENT_TYPE     VARCHAR(64)  NOT NULL,
    FILTER_PATTERN VARCHAR(500),
    ENABLED        VARCHAR(1)   DEFAULT 'Y' NOT NULL,
    CREATED_AT     TIMESTAMP     DEFAULT NOW() NOT NULL,
    CONSTRAINT FK_ES_AGENT FOREIGN KEY (AGENT_ID) REFERENCES AGENT_REGISTRY(AGENT_ID),
    CONSTRAINT CK_ES_ENABLED CHECK (ENABLED IN ('Y','N')),
    CONSTRAINT UK_ES_AGENT_EVENT UNIQUE (AGENT_ID, EVENT_TYPE)
);
CREATE INDEX IDX_ES_EVENT ON EVENT_SUBSCRIPTIONS(EVENT_TYPE, ENABLED);

-- ============================================================
-- 40. AGENT_CAPABILITY_INDEX (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE AGENT_CAPABILITY_INDEX (
    CAP_ID        VARCHAR(64)  PRIMARY KEY,
    AGENT_ID      VARCHAR(64)  NOT NULL,
    CAPABILITY    VARCHAR(256) NOT NULL,
    CONFIDENCE    NUMERIC(5,4)   DEFAULT 1.0000,
    LAST_VERIFIED_AT TIMESTAMP,
    CREATED_AT    TIMESTAMP     DEFAULT NOW() NOT NULL,
    CONSTRAINT FK_ACI_AGENT FOREIGN KEY (AGENT_ID) REFERENCES AGENT_REGISTRY(AGENT_ID)
);
CREATE INDEX IDX_ACI_CAP ON AGENT_CAPABILITY_INDEX(CAPABILITY);
CREATE INDEX IDX_ACI_AGENT ON AGENT_CAPABILITY_INDEX(AGENT_ID);

-- ============================================================
-- 41. TOOL_REGISTRY (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE TOOL_REGISTRY (
    TOOL_ID          VARCHAR(64)  PRIMARY KEY,
    TOOL_NAME        VARCHAR(256) NOT NULL,
    TOOL_NAMESPACE   VARCHAR(64)  NOT NULL,
    TOOL_VERSION     VARCHAR(32),
    DESCRIPTION      VARCHAR(2000),
    INPUT_SCHEMA     JSONB,
    OUTPUT_SCHEMA    JSONB,
    RUNTIME_REQS     JSONB,
    TOOL_TYPE        VARCHAR(32)  DEFAULT 'API',
    STATUS           VARCHAR(16)  DEFAULT 'ACTIVE',
    CALL_COUNT       BIGINT  DEFAULT 0,
    LAST_CALLED_AT   TIMESTAMP,
    CREATED_AT       TIMESTAMP     DEFAULT NOW() NOT NULL,
    UPDATED_AT       TIMESTAMP     DEFAULT NOW() NOT NULL,
    CONSTRAINT UK_TR_NAME UNIQUE (TOOL_NAME, TOOL_VERSION),
    CONSTRAINT CK_TR_TYPE CHECK (TOOL_TYPE IN ('API','FUNCTION','SQL','SCRIPT','WEBHOOK')),
    CONSTRAINT CK_TR_STATUS CHECK (STATUS IN ('ACTIVE','DEPRECATED','RETIRED'))
);
CREATE INDEX IDX_TR_NS ON TOOL_REGISTRY(TOOL_NAMESPACE);
CREATE INDEX IDX_TR_TYPE ON TOOL_REGISTRY(TOOL_TYPE);
CREATE INDEX IDX_TR_STATUS ON TOOL_REGISTRY(STATUS);

-- ============================================================
-- 42. TOOL_CHAINS (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE TOOL_CHAINS (
    CHAIN_ID         VARCHAR(64)  PRIMARY KEY,
    CHAIN_NAME       VARCHAR(256) NOT NULL,
    DESCRIPTION      VARCHAR(2000),
    CREATED_BY       VARCHAR(64),
    CREATED_AT       TIMESTAMP     DEFAULT NOW() NOT NULL,
    UPDATED_AT       TIMESTAMP     DEFAULT NOW() NOT NULL
);

-- ============================================================
-- 43. TOOL_CHAIN_STEPS (Non-Partitioned) [NEW v3.7.5]
-- ============================================================

CREATE TABLE TOOL_CHAIN_STEPS (
    CHAIN_STEP_ID    VARCHAR(64)  PRIMARY KEY,
    CHAIN_ID         VARCHAR(64)  NOT NULL,
    STEP_ORDER       INTEGER   NOT NULL,
    TOOL_ID          VARCHAR(64)  NOT NULL,
    INPUT_MAPPING    JSONB,
    OUTPUT_MAPPING   JSONB,
    PARALLEL_GROUP   INTEGER,
    TIMEOUT_SECONDS  BIGINT,
    CONSTRAINT FK_TCS_CHAIN FOREIGN KEY (CHAIN_ID) REFERENCES TOOL_CHAINS(CHAIN_ID) ON DELETE CASCADE,
    CONSTRAINT FK_TCS_TOOL FOREIGN KEY (TOOL_ID) REFERENCES TOOL_REGISTRY(TOOL_ID)
);
CREATE INDEX IDX_TCS_CHAIN ON TOOL_CHAIN_STEPS(CHAIN_ID, STEP_ORDER);

-- ============================================================



-- ============================================================
-- v3.9.0 Extensions: MCP, Human-in-the-Loop Approval, Model Routing
-- ============================================================

-- Add approval columns to STEP_EXECUTION_PLAN
ALTER TABLE STEP_EXECUTION_PLAN ADD COLUMN IF NOT EXISTS REQUIRES_APPROVAL CHAR(1) DEFAULT 'N';
ALTER TABLE STEP_EXECUTION_PLAN ADD COLUMN IF NOT EXISTS APPROVED_BY VARCHAR(64);
ALTER TABLE STEP_EXECUTION_PLAN ADD COLUMN IF NOT EXISTS APPROVED_AT TIMESTAMP;

-- Add approval column to LOOP_META
ALTER TABLE LOOP_META ADD COLUMN IF NOT EXISTS REQUIRE_APPROVAL CHAR(1) DEFAULT 'N';

-- Add approval column to TOOL_REGISTRY
ALTER TABLE TOOL_REGISTRY ADD COLUMN IF NOT EXISTS REQUIRES_APPROVAL CHAR(1) DEFAULT 'N';

-- 44. APPROVAL_REQUESTS [NEW v3.9.0]
CREATE TABLE IF NOT EXISTS APPROVAL_REQUESTS (
    APPROVAL_ID      VARCHAR(64)   PRIMARY KEY,
    ENTITY_TYPE      VARCHAR(32)   NOT NULL,
    ENTITY_ID        VARCHAR(64)   NOT NULL,
    REQUESTED_BY     VARCHAR(64)   NOT NULL,
    APPROVAL_STATUS  VARCHAR(16)   DEFAULT 'PENDING' NOT NULL,
    APPROVED_BY      VARCHAR(64),
    APPROVED_AT      TIMESTAMP,
    REJECT_REASON    VARCHAR(500),
    CREATED_AT       TIMESTAMP     DEFAULT NOW() NOT NULL,
    CONSTRAINT CK_AR_STATUS CHECK (APPROVAL_STATUS IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT CK_AR_ENTITY CHECK (ENTITY_TYPE IN ('STEP','LOOP','TOOL'))
);
CREATE INDEX IF NOT EXISTS IDX_AR_STATUS ON APPROVAL_REQUESTS(APPROVAL_STATUS, CREATED_AT DESC);
CREATE INDEX IF NOT EXISTS IDX_AR_ENTITY ON APPROVAL_REQUESTS(ENTITY_TYPE, ENTITY_ID);

-- v3.10.0: Trust configuration
INSERT INTO system_config (config_key, config_value, description) VALUES ('trust_success_delta', '0.1', 'Trust increase on task success') ON CONFLICT DO NOTHING;
INSERT INTO system_config (config_key, config_value, description) VALUES ('trust_failure_delta', '0.15', 'Trust decrease on task failure') ON CONFLICT DO NOTHING;
INSERT INTO system_config (config_key, config_value, description) VALUES ('trust_min_threshold', '0.3', 'Min trust for task delegation') ON CONFLICT DO NOTHING;
INSERT INTO system_config (config_key, config_value, description) VALUES ('trust_max_value', '1.0', 'Max trust value') ON CONFLICT DO NOTHING;
INSERT INTO system_config (config_key, config_value, description) VALUES ('trust_initial_coordinator', '0.5', 'Initial trust to group coordinator') ON CONFLICT DO NOTHING;
INSERT INTO system_config (config_key, config_value, description) VALUES ('trust_initial_member', '0.3', 'Initial trust to other group members') ON CONFLICT DO NOTHING;
