CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- AI Agent Infra v5.0.0 - PostgreSQL 18.3 - Phase 2: PL/pgSQL API Schemas
-- ============================================================

-- ============================================================
-- 1. Schema: memory_fusion
-- ============================================================

CREATE SCHEMA IF NOT EXISTS memory_fusion;

CREATE OR REPLACE FUNCTION memory_fusion.fuse_similar(
    p_category       TEXT    DEFAULT NULL,
    p_min_similarity NUMERIC DEFAULT 0.85,
    p_dry_run        BOOLEAN DEFAULT TRUE
)
RETURNS TABLE(source_id BIGINT, target_id BIGINT, similarity NUMERIC, action TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_pair  RECORD;
    v_count INT := 0;
BEGIN
    FOR v_pair IN
        SELECT e1.entity_id AS src, e2.entity_id AS tgt,
               1 - (ee1.embedding <=> ee2.embedding) AS sim
        FROM entities e1
        JOIN entity_embeddings ee1 ON ee1.entity_id = e1.entity_id AND ee1.entity_type = e1.entity_type
        JOIN entities e2 ON e1.entity_id < e2.entity_id
                        AND e1.entity_type = 'MEMORY'
                        AND e2.entity_type = 'MEMORY'
                        AND e1.status = 'ACTIVE'
                        AND e2.status = 'ACTIVE'
                        AND (p_category IS NULL OR (e1.category = p_category AND e2.category = p_category))
        JOIN entity_embeddings ee2 ON ee2.entity_id = e2.entity_id AND ee2.entity_type = e2.entity_type
        WHERE 1 - (ee1.embedding <=> ee2.embedding) >= p_min_similarity
    LOOP
        IF p_dry_run THEN
            action := 'WOULD_FUSE';
        ELSE
            INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata)
            VALUES (v_pair.src, 'MEMORY', v_pair.tgt, 'MEMORY', 'SIMILAR_TO', v_pair.sim, 0.9,
                    jsonb_build_object('fusion_candidate', TRUE, 'category', p_category))
            ON CONFLICT DO NOTHING;

            UPDATE entities
            SET status = 'ARCHIVED', updated_at = CURRENT_TIMESTAMP
            WHERE entity_id = v_pair.tgt AND entity_type = 'MEMORY';

            action := 'FUSED';
            v_count := v_count + 1;
        END IF;

        similarity := v_pair.sim;
        source_id  := v_pair.src;
        target_id  := v_pair.tgt;
        RETURN NEXT;
    END LOOP;

    INSERT INTO system_config (config_key, config_value, description)
    VALUES ('fusion.last_run', to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
            'Last fusion run: ' || v_count || ' memories fused')
    ON CONFLICT (config_key) DO UPDATE
    SET config_value = EXCLUDED.config_value, description = EXCLUDED.description, updated_at = CURRENT_TIMESTAMP;

    RETURN;
END;
$$;

CREATE OR REPLACE FUNCTION memory_fusion.extract_knowledge(
    p_category  TEXT DEFAULT NULL,
    p_min_count INT  DEFAULT 3
)
RETURNS TABLE(category TEXT, memory_count INT, knowledge_entity_id BIGINT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_grp       RECORD;
    v_new_id    BIGINT;
    v_extracted INT := 0;
BEGIN
    FOR v_grp IN
        SELECT e.category, COUNT(*) AS cnt
        FROM entities e
        WHERE e.entity_type = 'MEMORY'
          AND e.status = 'ACTIVE'
          AND (p_category IS NULL OR e.category = p_category)
        GROUP BY e.category
        HAVING COUNT(*) >= p_min_count
    LOOP
        INSERT INTO entities (entity_type, title, summary, category, status, owned_by_agent, source_agent, visibility, importance, retrieval_count)
        VALUES ('KNOWLEDGE',
                'Extracted: ' || v_grp.category || ' patterns',
                'Auto-extracted knowledge from ' || v_grp.cnt || ' memories in category ' || v_grp.category,
                v_grp.category,
                'ACTIVE', 'SYSTEM', 'SYSTEM', 'SHARED', 5, 0)
        RETURNING entity_id INTO v_new_id;

        INSERT INTO knowledge_meta (entity_id, domain, topic, difficulty, review_count, next_review)
        VALUES (v_new_id, v_grp.category, v_grp.category, 'INTERMEDIATE', 0,
                CURRENT_TIMESTAMP + INTERVAL '7 days');

        v_extracted := v_extracted + 1;

        category := v_grp.category;
        memory_count := v_grp.cnt;
        knowledge_entity_id := v_new_id;
        RETURN NEXT;
    END LOOP;

    INSERT INTO system_config (config_key, config_value, description)
    VALUES ('knowledge.last_extraction', to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
            'Last extraction: ' || v_extracted || ' knowledge items created')
    ON CONFLICT (config_key) DO UPDATE
    SET config_value = EXCLUDED.config_value, description = EXCLUDED.description, updated_at = CURRENT_TIMESTAMP;

    RETURN;
END;
$$;

CREATE OR REPLACE FUNCTION memory_fusion.decay_old(
    p_days_threshold INT     DEFAULT 90,
    p_decay_factor   NUMERIC DEFAULT 0.5
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    UPDATE entities
    SET importance = GREATEST(1, ROUND(importance * p_decay_factor)),
        updated_at = CURRENT_TIMESTAMP
    WHERE entity_type = 'MEMORY'
      AND status = 'ACTIVE'
      AND created_at < CURRENT_TIMESTAMP - (p_days_threshold || ' days')::INTERVAL;

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;

CREATE OR REPLACE FUNCTION memory_fusion.get_fusion_stats()
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_memories      INT;
    v_knowledge     INT;
    v_edges         INT;
    v_similar_pairs INT;
    v_archived      INT;
BEGIN
    SELECT COUNT(*) INTO v_memories FROM entities WHERE entity_type = 'MEMORY' AND status = 'ACTIVE';
    SELECT COUNT(*) INTO v_knowledge FROM entities WHERE entity_type = 'KNOWLEDGE' AND status = 'ACTIVE';
    SELECT COUNT(*) INTO v_edges FROM entity_edges;
    SELECT COUNT(*) INTO v_similar_pairs FROM entity_edges WHERE edge_type = 'SIMILAR_TO';
    SELECT COUNT(*) INTO v_archived FROM entities WHERE entity_type = 'MEMORY' AND status = 'ARCHIVED';

    RETURN jsonb_build_object(
        'total_memories', v_memories,
        'total_knowledge', v_knowledge,
        'total_edges', v_edges,
        'similar_pairs', v_similar_pairs,
        'archived_memories', v_archived
    );
END;
$$;


-- ============================================================
-- 2. Schema: knowledge_api
-- ============================================================

CREATE SCHEMA IF NOT EXISTS knowledge_api;

CREATE OR REPLACE FUNCTION knowledge_api.schedule_review(
    p_entity_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE knowledge_meta
    SET next_review = CURRENT_TIMESTAMP + LEAST(POWER(2, COALESCE(review_count, 0)), 30) * INTERVAL '1 day'
    WHERE entity_id = p_entity_id;
END;
$$;

CREATE OR REPLACE FUNCTION knowledge_api.record_review(
    p_entity_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE knowledge_meta
    SET review_count = review_count + 1,
        last_reviewed = CURRENT_TIMESTAMP,
        next_review = CURRENT_TIMESTAMP + LEAST(POWER(2, review_count + 1), 30) * INTERVAL '1 day'
    WHERE entity_id = p_entity_id;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION knowledge_api.get_due_reviews(
    p_limit INT DEFAULT 50
)
RETURNS TABLE(entity_id BIGINT, entity_type VARCHAR, title VARCHAR, category VARCHAR,
              domain VARCHAR, topic VARCHAR, difficulty VARCHAR,
              review_count INT, last_reviewed TIMESTAMP, next_review TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.entity_id, e.entity_type, e.title, e.category,
           km.domain, km.topic, km.difficulty,
           km.review_count, km.last_reviewed, km.next_review
    FROM entities e
    JOIN knowledge_meta km ON km.entity_id = e.entity_id
    WHERE e.status = 'ACTIVE'
      AND km.next_review <= CURRENT_TIMESTAMP
    ORDER BY km.next_review
    LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION knowledge_api.get_concept_lineage(
    p_entity_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_ancestors   JSONB;
    v_descendants JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'entity_id', e.entity_id,
        'entity_type', e.entity_type,
        'title', e.title,
        'edge_type', eg.edge_type,
        'strength', eg.strength
    ) ORDER BY eg.strength DESC), '[]'::jsonb) INTO v_ancestors
    FROM entity_edges eg
    JOIN entities e ON e.entity_id = eg.source_id AND e.entity_type = eg.source_type
    WHERE eg.target_id = p_entity_id;

    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'entity_id', e.entity_id,
        'entity_type', e.entity_type,
        'title', e.title,
        'edge_type', eg.edge_type,
        'strength', eg.strength
    ) ORDER BY eg.strength DESC), '[]'::jsonb) INTO v_descendants
    FROM entity_edges eg
    JOIN entities e ON e.entity_id = eg.target_id
    WHERE eg.source_id = p_entity_id;

    RETURN jsonb_build_object(
        'entity_id', p_entity_id,
        'ancestors', v_ancestors,
        'descendants', v_descendants
    );
END;
$$;

CREATE OR REPLACE FUNCTION knowledge_api.validate_concept(
    p_entity_id BIGINT,
    p_validator  TEXT DEFAULT 'SYSTEM'
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE knowledge_meta
    SET validation_status = 'VALIDATED'
    WHERE entity_id = p_entity_id
      AND validation_status = 'PENDING';

    UPDATE entities
    SET updated_at = CURRENT_TIMESTAMP
    WHERE entity_id = p_entity_id;

    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION knowledge_api.deprecate_concept(
    p_entity_id BIGINT,
    p_reason    TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE knowledge_meta
    SET is_current = FALSE,
        deprecated_at = CURRENT_TIMESTAMP,
        validation_status = 'EXPIRED'
    WHERE entity_id = p_entity_id;

    UPDATE entities
    SET status = 'ARCHIVED',
        updated_at = CURRENT_TIMESTAMP
    WHERE entity_id = p_entity_id;

    RETURN TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION knowledge_api.create_concept_version(
    p_entity_id  BIGINT,
    p_new_content TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_old_meta RECORD;
    v_new_id   BIGINT;
BEGIN
    SELECT * INTO v_old_meta FROM knowledge_meta WHERE entity_id = p_entity_id AND is_current = TRUE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No current knowledge_meta found for entity_id %', p_entity_id;
    END IF;

    UPDATE knowledge_meta
    SET is_current = FALSE
    WHERE entity_id = p_entity_id AND is_current = TRUE;

    INSERT INTO entities (entity_type, title, content, summary, category, status,
                          owned_by_agent, source_agent, visibility, importance, retrieval_count, workspace_id)
    SELECT entity_type, title, COALESCE(p_new_content, content), summary, category, 'ACTIVE',
           owned_by_agent, owned_by_agent, visibility, importance, 0, workspace_id
    FROM entities
    WHERE entity_id = p_entity_id
    RETURNING entity_id INTO v_new_id;

    INSERT INTO knowledge_meta (entity_id, domain, topic, difficulty, source_type, confidence, version, is_current, review_count, next_review)
    VALUES (v_new_id, v_old_meta.domain, v_old_meta.topic, v_old_meta.difficulty,
            v_old_meta.source_type, v_old_meta.confidence, v_old_meta.version + 1, TRUE, 0,
            CURRENT_TIMESTAMP + INTERVAL '7 days');

    INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence)
    VALUES (p_entity_id, 'KNOWLEDGE', v_new_id, 'KNOWLEDGE', 'EVOLVED_FROM', 1.0, 0.9);

    RETURN v_new_id;
END;
$$;


-- ============================================================
-- 3. Schema: agent_perm
-- ============================================================

CREATE SCHEMA IF NOT EXISTS agent_perm;

CREATE OR REPLACE FUNCTION agent_perm.check_entity_access(
    p_agent_id  VARCHAR,
    p_entity_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_visibility   VARCHAR;
    v_owner        VARCHAR;
    v_workspace_id BIGINT;
BEGIN
    SELECT visibility, owned_by_agent, workspace_id
    INTO v_visibility, v_owner, v_workspace_id
    FROM entities
    WHERE entity_id = p_entity_id;

    IF NOT FOUND THEN
        RETURN 'DENIED';
    END IF;

    IF v_visibility = 'PRIVATE' AND v_owner = p_agent_id THEN
        IF v_workspace_id IS NOT NULL THEN
            RETURN agent_perm.check_workspace_access(p_agent_id, p_entity_id);
        END IF;
        RETURN 'GRANTED';
    ELSIF v_visibility IN ('SHARED', 'PUBLIC') THEN
        IF v_workspace_id IS NOT NULL THEN
            RETURN agent_perm.check_workspace_access(p_agent_id, p_entity_id);
        END IF;
        RETURN 'GRANTED';
    ELSE
        RETURN 'DENIED';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RETURN 'DENIED';
END;
$$;

CREATE OR REPLACE FUNCTION agent_perm.check_workspace_access(
    p_agent_id  VARCHAR,
    p_entity_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_workspace_id  BIGINT;
    v_session_count INT;
BEGIN
    SELECT workspace_id
    INTO v_workspace_id
    FROM entities
    WHERE entity_id = p_entity_id;

    IF NOT FOUND THEN
        RETURN 'DENIED';
    END IF;

    SELECT COUNT(*)
    INTO v_session_count
    FROM agent_session
    WHERE agent_id = p_agent_id
      AND workspace_id = v_workspace_id
      AND is_active = TRUE;

    IF v_session_count > 0 THEN
        RETURN 'GRANTED';
    ELSE
        RETURN 'DENIED';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RETURN 'DENIED';
END;
$$;

CREATE OR REPLACE FUNCTION agent_perm.log_access(
    p_agent_id    VARCHAR,
    p_entity_id   BIGINT,
    p_access_type VARCHAR,
    p_session_id  BIGINT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_log_id BIGINT;
BEGIN
    INSERT INTO entity_access_log (entity_id, entity_type, agent_id, access_type, session_id, context)
    VALUES (p_entity_id, (SELECT entity_type FROM entities WHERE entity_id = p_entity_id),
            p_agent_id, p_access_type, p_session_id, NULL)
    RETURNING log_id INTO v_log_id;
    RETURN v_log_id;
END;
$$;

CREATE OR REPLACE FUNCTION agent_perm.cleanup_expired()
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    UPDATE agent_session
    SET is_active = FALSE,
        last_active_at = CURRENT_TIMESTAMP
    WHERE is_active = TRUE
      AND last_active_at < CURRENT_TIMESTAMP - INTERVAL '300 minutes';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;

CREATE OR REPLACE FUNCTION agent_perm.process_collab()
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    UPDATE agent_collaboration
    SET status = 'EXPIRED'
    WHERE status = 'ACTIVE'
      AND created_at < CURRENT_TIMESTAMP - INTERVAL '7 days';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;


-- ============================================================
-- 4. Schema: session_cleanup
-- ============================================================

CREATE SCHEMA IF NOT EXISTS session_cleanup;

CREATE OR REPLACE FUNCTION session_cleanup.purge_access_logs(
    p_days_to_keep INT DEFAULT 90
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_access INT;
    v_perm   INT;
BEGIN
    DELETE FROM entity_access_log
    WHERE accessed_at < CURRENT_TIMESTAMP - (p_days_to_keep || ' days')::INTERVAL;
    GET DIAGNOSTICS v_access = ROW_COUNT;

    DELETE FROM agent_permission_log
    WHERE created_at < CURRENT_TIMESTAMP - (p_days_to_keep || ' days')::INTERVAL;
    GET DIAGNOSTICS v_perm = ROW_COUNT;

    RETURN v_access + v_perm;
END;
$$;

CREATE OR REPLACE FUNCTION session_cleanup.purge_inactive_sessions(
    p_days_to_keep INT DEFAULT 30
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    DELETE FROM agent_session
    WHERE is_active = FALSE
      AND last_active_at < CURRENT_TIMESTAMP - (p_days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;

CREATE OR REPLACE FUNCTION session_cleanup.archive_old_entities(
    p_days_threshold INT DEFAULT 180
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    UPDATE entities
    SET status = 'ARCHIVED', updated_at = CURRENT_TIMESTAMP
    WHERE entity_type = 'MEMORY'
      AND status = 'ACTIVE'
      AND created_at < CURRENT_TIMESTAMP - (p_days_threshold || ' days')::INTERVAL
      AND importance <= 1;

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;

CREATE OR REPLACE FUNCTION session_cleanup.update_tag_counts()
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    UPDATE tags t
    SET usage_count = (
        SELECT COUNT(*) FROM entity_tags et WHERE et.tag_id = t.tag_id
    );

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    DELETE FROM tags WHERE usage_count = 0;

    RETURN v_affected;
END;
$$;


-- ============================================================
-- 5. Schema: workspace_manager
-- ============================================================

CREATE SCHEMA IF NOT EXISTS workspace_manager;

CREATE OR REPLACE FUNCTION workspace_manager.create(
    p_workspace_name VARCHAR,
    p_owner_user_id  VARCHAR DEFAULT NULL,
    p_workspace_type VARCHAR DEFAULT 'CONVERSATION',
    p_isolation_mode VARCHAR DEFAULT 'SHARED',
    p_metadata       JSONB   DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_workspace_id BIGINT;
BEGIN
    INSERT INTO workspaces (workspace_name, owner_user_id, workspace_type, isolation_mode, metadata)
    VALUES (p_workspace_name, p_owner_user_id, p_workspace_type, p_isolation_mode, p_metadata)
    RETURNING workspace_id INTO v_workspace_id;
    RETURN v_workspace_id;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.update(
    p_workspace_id   BIGINT,
    p_workspace_name VARCHAR DEFAULT NULL,
    p_status         VARCHAR DEFAULT NULL,
    p_isolation_mode VARCHAR DEFAULT NULL,
    p_current_agent  VARCHAR DEFAULT NULL,
    p_summary        TEXT    DEFAULT NULL,
    p_metadata       JSONB   DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE workspaces
    SET workspace_name   = COALESCE(p_workspace_name, workspace_name),
        status           = COALESCE(p_status, status),
        isolation_mode   = COALESCE(p_isolation_mode, isolation_mode),
        current_agent_id = COALESCE(p_current_agent, current_agent_id),
        summary          = COALESCE(p_summary, summary),
        metadata         = COALESCE(p_metadata, metadata),
        updated_at       = CURRENT_TIMESTAMP
    WHERE workspace_id = p_workspace_id;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.pause(
    p_workspace_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE workspaces
    SET status = 'PAUSED', updated_at = CURRENT_TIMESTAMP
    WHERE workspace_id = p_workspace_id;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.complete(
    p_workspace_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE workspaces
    SET status = 'COMPLETED', updated_at = CURRENT_TIMESTAMP
    WHERE workspace_id = p_workspace_id;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.save_context(
    p_workspace_id BIGINT,
    p_agent_id     VARCHAR,
    p_context_type VARCHAR,
    p_context_data JSONB,
    p_session_id   BIGINT DEFAULT NULL,
    p_parent_ctx   BIGINT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_context_id BIGINT;
BEGIN
    INSERT INTO workspace_context (workspace_id, agent_id, session_id, context_type, context_data, parent_context_id)
    VALUES (p_workspace_id, p_agent_id, p_session_id, p_context_type, p_context_data, p_parent_ctx)
    RETURNING context_id INTO v_context_id;
    RETURN v_context_id;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.get_latest_context(
    p_workspace_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'context_id', context_id,
        'workspace_id', workspace_id,
        'agent_id', agent_id,
        'session_id', session_id,
        'context_type', context_type,
        'context_data', context_data,
        'parent_ctx', parent_context_id,
        'created_at', to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) INTO v_result
    FROM workspace_context
    WHERE workspace_id = p_workspace_id
    ORDER BY created_at DESC
    LIMIT 1;

    RETURN v_result;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.get_context_chain(
    p_workspace_id BIGINT,
    p_limit        INT DEFAULT 10
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'context_id', context_id,
        'workspace_id', workspace_id,
        'agent_id', agent_id,
        'session_id', session_id,
        'context_type', context_type,
        'context_data', context_data,
        'parent_ctx', parent_context_id,
        'created_at', to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) ORDER BY created_at DESC), '[]'::jsonb) INTO v_result
    FROM (
        SELECT context_id, workspace_id, agent_id, session_id, context_type,
               context_data, parent_context_id, created_at
        FROM workspace_context
        WHERE workspace_id = p_workspace_id
        ORDER BY created_at DESC
        LIMIT p_limit
    ) sub;

    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.link_task(
    p_workspace_id BIGINT,
    p_plan_id      BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO workspace_tasks (workspace_id, plan_id)
    VALUES (p_workspace_id, p_plan_id)
    ON CONFLICT (workspace_id, plan_id) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.unlink_task(
    p_workspace_id BIGINT,
    p_plan_id      BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM workspace_tasks
    WHERE workspace_id = p_workspace_id
      AND plan_id = p_plan_id;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION workspace_manager.cleanup_abandoned(
    p_days_threshold INT DEFAULT 30
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    DELETE FROM workspaces
    WHERE status = 'ABANDONED'
      AND updated_at < CURRENT_TIMESTAMP - (p_days_threshold || ' days')::INTERVAL;

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;


-- ============================================================
-- 6. Schema: spec_manager
-- ============================================================

CREATE SCHEMA IF NOT EXISTS spec_manager;

CREATE OR REPLACE FUNCTION spec_manager.create(
    p_title              VARCHAR,
    p_content            TEXT    DEFAULT NULL,
    p_summary            TEXT    DEFAULT NULL,
    p_category           VARCHAR DEFAULT NULL,
    p_importance         NUMERIC DEFAULT 5,
    p_owned_by_agent     VARCHAR DEFAULT NULL,
    p_visibility         VARCHAR DEFAULT 'SHARED',
    p_workspace_id       BIGINT  DEFAULT NULL,
    p_spec_scope         VARCHAR DEFAULT NULL,
    p_complexity         VARCHAR DEFAULT 'MEDIUM',
    p_acceptance_criteria JSONB  DEFAULT NULL,
    p_spec_constraints   JSONB   DEFAULT NULL,
    p_parent_spec_id     BIGINT  DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_entity_id BIGINT;
BEGIN
    INSERT INTO entities (entity_type, title, content, summary, category, status,
                          owned_by_agent, source_agent, visibility, importance, retrieval_count, workspace_id)
    VALUES ('SPEC', p_title, p_content, p_summary, p_category, 'DRAFT',
            p_owned_by_agent, p_owned_by_agent, p_visibility, p_importance, 0, p_workspace_id)
    RETURNING entity_id INTO v_entity_id;

    INSERT INTO spec_meta (entity_id, spec_version, spec_status, acceptance_criteria, spec_constraints, spec_scope, complexity, parent_spec_id)
    VALUES (v_entity_id, 1, 'DRAFT', p_acceptance_criteria, p_spec_constraints, p_spec_scope, p_complexity, p_parent_spec_id);

    RETURN v_entity_id;
END;
$$;

CREATE OR REPLACE FUNCTION spec_manager.update(
    p_entity_id          BIGINT,
    p_title              VARCHAR DEFAULT NULL,
    p_content            TEXT    DEFAULT NULL,
    p_summary            TEXT    DEFAULT NULL,
    p_category           VARCHAR DEFAULT NULL,
    p_importance         NUMERIC DEFAULT NULL,
    p_visibility         VARCHAR DEFAULT NULL,
    p_spec_status        VARCHAR DEFAULT NULL,
    p_spec_scope         VARCHAR DEFAULT NULL,
    p_complexity         VARCHAR DEFAULT NULL,
    p_acceptance_criteria JSONB  DEFAULT NULL,
    p_spec_constraints   JSONB   DEFAULT NULL
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE entities
    SET title      = COALESCE(p_title, title),
        content    = COALESCE(p_content, content),
        summary    = COALESCE(p_summary, summary),
        category   = COALESCE(p_category, category),
        importance = COALESCE(p_importance, importance),
        visibility = COALESCE(p_visibility, visibility),
        updated_at = CURRENT_TIMESTAMP
    WHERE entity_id = p_entity_id
      AND entity_type = 'SPEC';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    UPDATE spec_meta
    SET spec_status         = COALESCE(p_spec_status, spec_status),
        spec_scope          = COALESCE(p_spec_scope, spec_scope),
        complexity          = COALESCE(p_complexity, complexity),
        acceptance_criteria = COALESCE(p_acceptance_criteria, acceptance_criteria),
        spec_constraints    = COALESCE(p_spec_constraints, spec_constraints),
        updated_at          = CURRENT_TIMESTAMP
    WHERE entity_id = p_entity_id;

    RETURN v_rows;
END;
$$;

CREATE OR REPLACE FUNCTION spec_manager.get(
    p_entity_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'entity_id', e.entity_id,
        'entity_type', e.entity_type,
        'title', e.title,
        'summary', e.summary,
        'category', e.category,
        'status', e.status,
        'owned_by', e.owned_by_agent,
        'visibility', e.visibility,
        'importance', e.importance,
        'workspace_id', e.workspace_id,
        'spec_meta', jsonb_build_object(
            'spec_version', sm.spec_version,
            'spec_status', sm.spec_status,
            'spec_scope', sm.spec_scope,
            'complexity', sm.complexity,
            'acceptance_criteria', sm.acceptance_criteria,
            'spec_constraints', sm.spec_constraints,
            'parent_spec_id', sm.parent_spec_id
        ),
        'plan_links', COALESCE(
            (SELECT jsonb_agg(jsonb_build_object(
                'link_id', spl.link_id,
                'plan_id', spl.plan_id,
                'link_type', spl.link_type,
                'link_strength', spl.link_strength,
                'created_at', to_char(spl.link_strength, 'FM9999.9999')
            )) FROM spec_plan_links spl WHERE spl.spec_id = p_entity_id),
            '[]'::jsonb
        ),
        'created_at', to_char(e.created_at, 'YYYY-MM-DD"T"HH24:MI:SS'),
        'updated_at', to_char(e.updated_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) INTO v_result
    FROM entities e
    JOIN spec_meta sm ON sm.entity_id = e.entity_id
    WHERE e.entity_id = p_entity_id
      AND e.entity_type = 'SPEC';

    RETURN v_result;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION spec_manager.list(
    p_spec_scope  VARCHAR DEFAULT NULL,
    p_spec_status VARCHAR DEFAULT NULL,
    p_limit       INT     DEFAULT 50
)
RETURNS TABLE(entity_id BIGINT, title VARCHAR, summary VARCHAR, category VARCHAR,
              status VARCHAR, owned_by_agent VARCHAR, importance NUMERIC,
              spec_version INT, spec_status VARCHAR, spec_scope VARCHAR,
              complexity VARCHAR, parent_spec_id BIGINT,
              created_at TIMESTAMP, updated_at TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.entity_id, e.title, e.summary, e.category,
           e.status, e.owned_by_agent, e.importance,
           sm.spec_version, sm.spec_status, sm.spec_scope,
           sm.complexity, sm.parent_spec_id,
           e.created_at, e.updated_at
    FROM entities e
    JOIN spec_meta sm ON sm.entity_id = e.entity_id
    WHERE e.entity_type = 'SPEC'
      AND (p_spec_scope IS NULL OR sm.spec_scope = p_spec_scope)
      AND (p_spec_status IS NULL OR sm.spec_status = p_spec_status)
    ORDER BY e.updated_at DESC
    LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION spec_manager.link_spec_to_plan(
    p_spec_id       BIGINT,
    p_plan_id       BIGINT,
    p_link_type     VARCHAR,
    p_link_strength NUMERIC DEFAULT 1.0
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_link_id BIGINT;
BEGIN
    INSERT INTO spec_plan_links (spec_id, plan_id, link_type, link_strength)
    VALUES (p_spec_id, p_plan_id, p_link_type, p_link_strength)
    ON CONFLICT (spec_id, plan_id, link_type) DO NOTHING
    RETURNING link_id INTO v_link_id;
    RETURN v_link_id;
END;
$$;

CREATE OR REPLACE FUNCTION spec_manager.validate(
    p_spec_id BIGINT,
    p_plan_id BIGINT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_criteria    JSONB;
    v_spec_title  VARCHAR;
    v_total       INT := 0;
    v_passed      INT := 0;
    v_rate        NUMERIC := 0;
    v_status_str  VARCHAR := 'FAIL';
    v_effective_plan_id BIGINT;
BEGIN
    SELECT sm.acceptance_criteria, e.title
    INTO v_criteria, v_spec_title
    FROM spec_meta sm
    JOIN entities e ON e.entity_id = sm.entity_id
    WHERE sm.entity_id = p_spec_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('spec_id', p_spec_id, 'status', 'NOT_FOUND');
    END IF;

    v_effective_plan_id := COALESCE(p_plan_id, (
        SELECT spl.plan_id FROM spec_plan_links spl
        WHERE spl.spec_id = p_spec_id AND spl.link_type = 'VALIDATES'
        LIMIT 1
    ));

    IF v_effective_plan_id IS NOT NULL THEN
        SELECT COUNT(*), COUNT(CASE WHEN ts.status = 'SUCCESS' THEN 1 END)
        INTO v_total, v_passed
        FROM task_steps ts
        WHERE ts.plan_id = v_effective_plan_id;

        IF v_total > 0 THEN
            v_rate := ROUND(v_passed::NUMERIC / v_total, 4);
            IF v_passed = v_total THEN
                v_status_str := 'PASS';
            END IF;
        END IF;
    END IF;

    RETURN jsonb_build_object(
        'spec_id', p_spec_id,
        'spec_title', v_spec_title,
        'plan_id', v_effective_plan_id,
        'total_steps', v_total,
        'passed_steps', v_passed,
        'pass_rate', v_rate,
        'status', v_status_str
    );
EXCEPTION
    WHEN OTHERS THEN
        RETURN jsonb_build_object('spec_id', p_spec_id, 'status', 'NOT_FOUND');
END;
$$;

CREATE OR REPLACE FUNCTION spec_manager.derive(
    p_parent_spec_id BIGINT,
    p_title          VARCHAR,
    p_content        TEXT DEFAULT NULL,
    p_summary        TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_entity_id    BIGINT;
    v_parent_scope VARCHAR;
    v_new_version  INT;
BEGIN
    SELECT sm.spec_scope, sm.spec_version + 1
    INTO v_parent_scope, v_new_version
    FROM spec_meta sm
    WHERE sm.entity_id = p_parent_spec_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Parent spec not found: %', p_parent_spec_id;
    END IF;

    INSERT INTO entities (entity_type, title, content, summary, category, status,
                          owned_by_agent, source_agent, visibility, importance, retrieval_count, workspace_id)
    SELECT 'SPEC', p_title, COALESCE(p_content, e.content), COALESCE(p_summary, e.summary), e.category,
           'DRAFT', e.owned_by_agent, e.owned_by_agent, e.visibility, e.importance, 0, e.workspace_id
    FROM entities e
    WHERE e.entity_id = p_parent_spec_id AND e.entity_type = 'SPEC'
    RETURNING entity_id INTO v_entity_id;

    INSERT INTO spec_meta (entity_id, spec_version, spec_status, acceptance_criteria, spec_constraints, spec_scope, complexity, parent_spec_id)
    SELECT v_entity_id, v_new_version, 'DRAFT',
           sm.acceptance_criteria, sm.spec_constraints, v_parent_scope, sm.complexity, p_parent_spec_id
    FROM spec_meta sm
    WHERE sm.entity_id = p_parent_spec_id;

    RETURN v_entity_id;
END;
$$;

CREATE OR REPLACE FUNCTION spec_manager.delete(
    p_entity_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM spec_plan_links WHERE spec_id = p_entity_id;
    DELETE FROM spec_meta WHERE entity_id = p_entity_id;
    DELETE FROM entities WHERE entity_id = p_entity_id AND entity_type = 'SPEC';
END;
$$;


-- ============================================================
-- 7. Schema: collab_group_manager
-- ============================================================

CREATE SCHEMA IF NOT EXISTS collab_group_manager;

CREATE OR REPLACE FUNCTION collab_group_manager.create(
    p_group_name           VARCHAR,
    p_group_type           VARCHAR DEFAULT 'PROJECT',
    p_description          TEXT    DEFAULT NULL,
    p_coordinator_agent_id VARCHAR DEFAULT NULL,
    p_sharing_policy       VARCHAR DEFAULT 'OPEN',
    p_metadata             JSONB   DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_group_id     BIGINT;
    v_workspace_id BIGINT;
BEGIN
    INSERT INTO workspaces (workspace_name, workspace_type, isolation_mode, metadata)
    VALUES ('Collab: ' || p_group_name, 'COLLAB_GROUP', 'SHARED', p_metadata)
    RETURNING workspace_id INTO v_workspace_id;

    INSERT INTO collab_groups (group_name, group_type, description, workspace_id, coordinator_agent_id, sharing_policy, metadata)
    VALUES (p_group_name, p_group_type, p_description, v_workspace_id, p_coordinator_agent_id, p_sharing_policy, p_metadata)
    RETURNING group_id INTO v_group_id;

    RETURN v_group_id;
END;
$$;

CREATE OR REPLACE FUNCTION collab_group_manager.update(
    p_group_id             BIGINT,
    p_group_name           VARCHAR DEFAULT NULL,
    p_description          TEXT    DEFAULT NULL,
    p_coordinator_agent_id VARCHAR DEFAULT NULL,
    p_sharing_policy       VARCHAR DEFAULT NULL,
    p_status               VARCHAR DEFAULT NULL,
    p_metadata             JSONB   DEFAULT NULL
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE collab_groups
    SET group_name           = COALESCE(p_group_name, group_name),
        description          = COALESCE(p_description, description),
        coordinator_agent_id = COALESCE(p_coordinator_agent_id, coordinator_agent_id),
        sharing_policy       = COALESCE(p_sharing_policy, sharing_policy),
        status               = COALESCE(p_status, status),
        metadata             = COALESCE(p_metadata, metadata),
        updated_at           = CURRENT_TIMESTAMP
    WHERE group_id = p_group_id;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END;
$$;

CREATE OR REPLACE FUNCTION collab_group_manager.get(
    p_group_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'group_id', g.group_id,
        'group_name', g.group_name,
        'group_type', g.group_type,
        'description', g.description,
        'workspace_id', g.workspace_id,
        'coordinator', g.coordinator_agent_id,
        'sharing_policy', g.sharing_policy,
        'status', g.status,
        'metadata', g.metadata,
        'members', COALESCE(
            (SELECT jsonb_agg(jsonb_build_object(
                'member_id', m.member_id,
                'agent_id', m.agent_id,
                'role', m.role,
                'personal_workspace_id', m.personal_workspace_id,
                'joined_at', to_char(m.joined_at, 'YYYY-MM-DD"T"HH24:MI:SS'),
                'status', m.status
            ) ORDER BY m.joined_at)
            FROM collab_group_members m
            WHERE m.group_id = p_group_id AND m.status = 'ACTIVE'),
            '[]'::jsonb
        ),
        'created_at', to_char(g.created_at, 'YYYY-MM-DD"T"HH24:MI:SS'),
        'updated_at', to_char(g.updated_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) INTO v_result
    FROM collab_groups g
    WHERE g.group_id = p_group_id;

    RETURN v_result;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION collab_group_manager.add_member(
    p_group_id BIGINT,
    p_agent_id VARCHAR,
    p_role     VARCHAR DEFAULT 'MEMBER'
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_member_id     BIGINT;
    v_personal_ws_id BIGINT;
BEGIN
    IF p_role IN ('LEAD', 'CONTRIBUTOR') THEN
        INSERT INTO workspaces (workspace_name, workspace_type, isolation_mode)
        VALUES ('Personal: ' || p_agent_id || ' in ' || p_group_id, 'PERSONAL_IN_GROUP', 'ISOLATED')
        RETURNING workspace_id INTO v_personal_ws_id;
    END IF;

    INSERT INTO collab_group_members (group_id, agent_id, role, personal_workspace_id, status)
    VALUES (p_group_id, p_agent_id, p_role, v_personal_ws_id, 'ACTIVE')
    ON CONFLICT (group_id, agent_id) DO UPDATE
        SET status = 'ACTIVE', role = EXCLUDED.role,
            personal_workspace_id = COALESCE(collab_group_members.personal_workspace_id, EXCLUDED.personal_workspace_id)
    RETURNING member_id INTO v_member_id;

    RETURN v_member_id;
END;
$$;

CREATE OR REPLACE FUNCTION collab_group_manager.remove_member(
    p_group_id BIGINT,
    p_agent_id VARCHAR
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    UPDATE collab_group_members
    SET status = 'LEFT'
    WHERE group_id = p_group_id
      AND agent_id = p_agent_id
      AND status = 'ACTIVE';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;

CREATE OR REPLACE FUNCTION collab_group_manager.archive(
    p_group_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE collab_groups
    SET status = 'ARCHIVED', updated_at = CURRENT_TIMESTAMP
    WHERE group_id = p_group_id;

    UPDATE collab_group_members
    SET status = 'REMOVED'
    WHERE group_id = p_group_id AND status = 'ACTIVE';
END;
$$;


-- ============================================================
-- 8. Schema: embedding_manager
-- ============================================================

CREATE SCHEMA IF NOT EXISTS embedding_manager;

CREATE OR REPLACE FUNCTION embedding_manager.generate_embedding(
    p_text TEXT
)
RETURNS vector
LANGUAGE plpgsql
AS $$
DECLARE
    v_vec TEXT;
BEGIN
    v_vec := embedding_generate(p_text);
    IF v_vec IS NULL THEN
        RAISE EXCEPTION 'embedding_generate returned NULL for input text';
    END IF;
    RETURN v_vec::vector;
END;
$$;

CREATE OR REPLACE FUNCTION embedding_manager.generate_and_store(
    p_entity_id   BIGINT,
    p_entity_type VARCHAR,
    p_text        TEXT
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_vec   TEXT;
    v_model VARCHAR;
    v_dim   INT;
    v_cnt   INT;
BEGIN
    v_vec := embedding_generate(p_text);
    IF v_vec IS NULL THEN
        RETURN -1;
    END IF;

    SELECT config_value INTO v_model FROM system_config WHERE config_key = 'embedding_model';
    SELECT config_value::INT INTO v_dim FROM system_config WHERE config_key = 'embedding_dim';

    SELECT COUNT(*) INTO v_cnt FROM entity_embeddings WHERE entity_id = p_entity_id AND entity_type = p_entity_type;
    IF v_cnt > 0 THEN
        UPDATE entity_embeddings
        SET embedding = v_vec::vector, embedding_model = v_model, embedding_dim = v_dim, embedded_at = CURRENT_TIMESTAMP
        WHERE entity_id = p_entity_id AND entity_type = p_entity_type;
    ELSE
        INSERT INTO entity_embeddings (entity_id, entity_type, embedding, embedding_model, embedding_dim, embedded_at)
        VALUES (p_entity_id, p_entity_type, v_vec::vector, v_model, v_dim, CURRENT_TIMESTAMP);
    END IF;

    RETURN 1;
EXCEPTION
    WHEN OTHERS THEN
        RETURN -1;
END;
$$;

CREATE OR REPLACE FUNCTION embedding_manager.cosine_similarity(
    p_id1   BIGINT,
    p_type1 VARCHAR,
    p_id2   BIGINT,
    p_type2 VARCHAR
)
RETURNS NUMERIC
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_sim NUMERIC;
BEGIN
    SELECT 1 - (e1.embedding <=> e2.embedding) INTO v_sim
    FROM entity_embeddings e1, entity_embeddings e2
    WHERE e1.entity_id = p_id1 AND e1.entity_type = p_type1
      AND e2.entity_id = p_id2 AND e2.entity_type = p_type2;

    RETURN ROUND(v_sim, 4);
EXCEPTION
    WHEN OTHERS THEN
        RETURN -1;
END;
$$;

CREATE OR REPLACE FUNCTION embedding_manager.batch_embed_entities(
    p_entity_type VARCHAR,
    p_limit       INT DEFAULT 100
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_rec   RECORD;
    v_count INT := 0;
BEGIN
    FOR v_rec IN
        SELECT e.entity_id, e.entity_type, e.title
        FROM entities e
        WHERE e.entity_type = p_entity_type
          AND NOT EXISTS (SELECT 1 FROM entity_embeddings em WHERE em.entity_id = e.entity_id AND em.entity_type = e.entity_type)
          AND e.title IS NOT NULL
        ORDER BY e.created_at DESC
        LIMIT p_limit
    LOOP
        IF embedding_manager.generate_and_store(v_rec.entity_id, v_rec.entity_type, v_rec.title) = 1 THEN
            v_count := v_count + 1;
        END IF;
    END LOOP;

    INSERT INTO system_config (config_key, config_value, description)
    VALUES ('last_batch_embed', v_count::TEXT, 'Last batch embed count')
    ON CONFLICT (config_key) DO UPDATE
    SET config_value = EXCLUDED.config_value, description = EXCLUDED.description, updated_at = CURRENT_TIMESTAMP;

    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION embedding_manager.get_stats()
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_total     INT;
    v_with_vec  INT;
    v_models    TEXT;
BEGIN
    SELECT COUNT(*), COUNT(CASE WHEN embedding IS NOT NULL THEN 1 END)
    INTO v_total, v_with_vec FROM entity_embeddings;

    SELECT string_agg(DISTINCT embedding_model, ',' ORDER BY embedding_model)
    INTO v_models FROM entity_embeddings WHERE embedding_model IS NOT NULL;

    RETURN jsonb_build_object(
        'total', v_total,
        'with_vector', v_with_vec,
        'models', v_models
    );
END;
$$;


-- ============================================================
-- 9. Schema: db_crypto
-- ============================================================

CREATE SCHEMA IF NOT EXISTS db_crypto;

CREATE OR REPLACE FUNCTION db_crypto.encrypt(
    p_plaintext TEXT,
    p_key       TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_key TEXT;
    v_iv  BYTEA;
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

CREATE OR REPLACE FUNCTION db_crypto.decrypt(
    p_ciphertext TEXT,
    p_key        TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_key       TEXT;
    v_iv        BYTEA;
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

CREATE OR REPLACE FUNCTION db_crypto.rotate_key(
    p_old_key TEXT,
    p_new_key TEXT
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count     INT := 0;
    v_rec       RECORD;
    v_decrypted TEXT;
BEGIN
    FOR v_rec IN SELECT credential_id, credential_value FROM agent_credentials WHERE is_active = TRUE LOOP
        v_decrypted := db_crypto.decrypt(v_rec.credential_value, p_old_key);
        UPDATE agent_credentials
        SET credential_value = db_crypto.encrypt(v_decrypted, p_new_key)
        WHERE credential_id = v_rec.credential_id;
        v_count := v_count + 1;
    END LOOP;
    UPDATE system_config SET config_value = p_new_key WHERE config_key = 'credential_encryption_key';
    RETURN v_count;
END;
$$;


-- ============================================================
-- 10. Schema: branch_manager
-- ============================================================

CREATE SCHEMA IF NOT EXISTS branch_manager;

CREATE OR REPLACE FUNCTION branch_manager.fork(
    p_workspace_id    BIGINT,
    p_fork_context_id BIGINT,
    p_branch_name     VARCHAR,
    p_branch_type     VARCHAR,
    p_agent_id        VARCHAR,
    p_source_agent_id VARCHAR DEFAULT NULL,
    p_purpose         TEXT    DEFAULT NULL,
    p_fork_session_id BIGINT  DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_branch_id        BIGINT;
    v_parent_branch_id BIGINT;
    v_context_id       BIGINT;
BEGIN
    SELECT MAX(b.branch_id) INTO v_parent_branch_id
    FROM context_branches b
    WHERE b.workspace_id = p_workspace_id
      AND b.status = 'ACTIVE'
      AND b.agent_id = p_agent_id;

    INSERT INTO context_branches (workspace_id, parent_branch_id, source_context_id, branch_name, branch_type, status, agent_id, description)
    VALUES (p_workspace_id, v_parent_branch_id, p_fork_context_id, p_branch_name, p_branch_type, 'ACTIVE', p_agent_id, p_purpose)
    RETURNING branch_id INTO v_branch_id;

    INSERT INTO workspace_context (workspace_id, agent_id, session_id, context_type, context_data, parent_context_id, branch_id)
    VALUES (p_workspace_id, p_agent_id, p_fork_session_id, 'BRANCH_POINT',
            jsonb_build_object(
                'branch_id', v_branch_id,
                'branch_name', p_branch_name,
                'branch_type', p_branch_type,
                'fork_context_id', p_fork_context_id
            ),
            p_fork_context_id, v_branch_id)
    RETURNING context_id INTO v_context_id;

    RETURN v_branch_id;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.get(
    p_branch_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'branch_id', branch_id,
        'workspace_id', workspace_id,
        'parent_branch_id', parent_branch_id,
        'fork_context_id', source_context_id,
        'branch_name', branch_name,
        'branch_type', branch_type,
        'branch_status', status,
        'agent_id', agent_id,
        'branch_purpose', description,
        'created_at', to_char(created_at, 'YYYY-MM-DD HH24:MI:SS'),
        'merged_at', to_char(merged_at, 'YYYY-MM-DD HH24:MI:SS'),
        'abandoned_at', to_char(abandoned_at, 'YYYY-MM-DD HH24:MI:SS')
    ) INTO v_result
    FROM context_branches
    WHERE branch_id = p_branch_id;

    RETURN v_result;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.get_tree(
    p_workspace_id BIGINT
)
RETURNS TABLE(branch_id BIGINT, parent_branch_id BIGINT, branch_name VARCHAR, branch_type VARCHAR,
              status VARCHAR, agent_id VARCHAR, source_context_id BIGINT,
              created_at TIMESTAMP, merged_at TIMESTAMP, abandoned_at TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT b.branch_id, b.parent_branch_id, b.branch_name, b.branch_type,
           b.status, b.agent_id, b.source_context_id,
           b.created_at, b.merged_at, b.abandoned_at
    FROM context_branches b
    WHERE b.workspace_id = p_workspace_id
    ORDER BY b.created_at ASC;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.get_chain(
    p_branch_id BIGINT,
    p_limit     INT DEFAULT 50
)
RETURNS TABLE(context_id BIGINT, workspace_id BIGINT, agent_id VARCHAR, session_id BIGINT,
              context_type VARCHAR, context_data JSONB, parent_context_id BIGINT, branch_id BIGINT,
              created_at TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT wc.context_id, wc.workspace_id, wc.agent_id, wc.session_id,
           wc.context_type, wc.context_data, wc.parent_context_id, wc.branch_id,
           wc.created_at
    FROM workspace_context wc
    WHERE wc.branch_id = p_branch_id
    ORDER BY wc.created_at ASC
    LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.diff(
    p_branch_a_id BIGINT,
    p_branch_b_id BIGINT
)
RETURNS TABLE(diff_side TEXT, context_id BIGINT, context_type VARCHAR,
              context_data JSONB, agent_id VARCHAR, created_at TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT 'ONLY_IN_A'::TEXT AS diff_side, wc.context_id, wc.context_type,
           wc.context_data, wc.agent_id, wc.created_at
    FROM workspace_context wc
    WHERE wc.branch_id = p_branch_a_id
      AND wc.context_type != 'BRANCH_POINT'
    UNION ALL
    SELECT 'ONLY_IN_B'::TEXT AS diff_side, wc.context_id, wc.context_type,
           wc.context_data, wc.agent_id, wc.created_at
    FROM workspace_context wc
    WHERE wc.branch_id = p_branch_b_id
      AND wc.context_type != 'BRANCH_POINT'
    ORDER BY diff_side, created_at ASC;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.detect_conflicts(
    p_source_branch_id BIGINT,
    p_target_branch_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM (
        SELECT e.entity_id
        FROM entities e
        WHERE e.entity_id IN (
            SELECT (wc.context_data->>'entity_id')::BIGINT
            FROM workspace_context wc
            WHERE wc.branch_id = p_source_branch_id
              AND wc.context_data->>'entity_id' IS NOT NULL
        )
        INTERSECT
        SELECT e2.entity_id
        FROM entities e2
        WHERE e2.entity_id IN (
            SELECT (wc2.context_data->>'entity_id')::BIGINT
            FROM workspace_context wc2
            WHERE wc2.branch_id = p_target_branch_id
              AND wc2.context_data->>'entity_id' IS NOT NULL
        )
    ) sub;

    RETURN jsonb_build_object(
        'total_conflicts', v_count,
        'entity_conflicts', v_count,
        'auto_resolvable', 0,
        'source_branch_id', p_source_branch_id,
        'target_branch_id', p_target_branch_id
    );
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.merge(
    p_source_branch_id      BIGINT,
    p_target_branch_id      BIGINT,
    p_merge_type            VARCHAR DEFAULT 'MERGE',
    p_merged_by_agent       VARCHAR DEFAULT NULL,
    p_conflict_resolutions  JSONB   DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_merge_id       BIGINT;
    v_conflicts      JSONB;
    v_result         VARCHAR := 'SUCCESS';
    v_source_ws      BIGINT;
    v_conflict_count INT;
    v_context_id     BIGINT;
BEGIN
    v_conflicts := branch_manager.detect_conflicts(p_source_branch_id, p_target_branch_id);
    v_conflict_count := (v_conflicts->>'total_conflicts')::INT;

    IF v_conflict_count > 0 AND p_conflict_resolutions IS NULL THEN
        v_result := 'CONFLICT';
    ELSIF v_conflict_count > 0 THEN
        v_result := 'PARTIAL';
    END IF;

    SELECT workspace_id INTO v_source_ws
    FROM context_branches WHERE branch_id = p_source_branch_id;

    INSERT INTO branch_merge_log (source_branch_id, target_branch_id, merge_status, conflicts_json, merged_at, merged_by_agent)
    VALUES (p_source_branch_id, p_target_branch_id, v_result, v_conflicts, CURRENT_TIMESTAMP, p_merged_by_agent)
    RETURNING log_id INTO v_merge_id;

    UPDATE context_branches
    SET status = 'MERGED', merged_at = CURRENT_TIMESTAMP
    WHERE branch_id = p_source_branch_id;

    INSERT INTO workspace_context (workspace_id, agent_id, context_type, context_data, branch_id)
    VALUES (v_source_ws, p_merged_by_agent, 'SUMMARY',
            jsonb_build_object(
                'merge_id', v_merge_id,
                'source_branch', p_source_branch_id,
                'target_branch', p_target_branch_id,
                'merge_type', p_merge_type,
                'result', v_result
            ),
            p_target_branch_id)
    RETURNING context_id INTO v_context_id;

    RETURN v_merge_id;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.abandon(
    p_branch_id BIGINT,
    p_reason    TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE context_branches
    SET status = 'ABANDONED',
        abandoned_at = CURRENT_TIMESTAMP,
        description = COALESCE(description || ' | ABANDONED: ' || p_reason, 'ABANDONED: ' || p_reason)
    WHERE branch_id = p_branch_id;

    UPDATE agent_session
    SET is_active = FALSE, last_active_at = CURRENT_TIMESTAMP
    WHERE branch_id = p_branch_id AND is_active = TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.pause(
    p_branch_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE context_branches
    SET status = 'PAUSED'
    WHERE branch_id = p_branch_id;

    UPDATE agent_session
    SET is_active = FALSE, last_active_at = CURRENT_TIMESTAMP
    WHERE branch_id = p_branch_id AND is_active = TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.resume(
    p_branch_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_agent_id     VARCHAR;
    v_workspace_id BIGINT;
    v_session_id   BIGINT;
BEGIN
    UPDATE context_branches
    SET status = 'ACTIVE'
    WHERE branch_id = p_branch_id;

    SELECT agent_id, workspace_id INTO v_agent_id, v_workspace_id
    FROM context_branches WHERE branch_id = p_branch_id;

    INSERT INTO agent_session (agent_id, owner_user_id, workspace_id, branch_id, is_active)
    VALUES (v_agent_id, NULL, v_workspace_id, p_branch_id, TRUE)
    RETURNING session_id INTO v_session_id;

    RETURN v_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.get_agent_branches(
    p_agent_id VARCHAR,
    p_status   VARCHAR DEFAULT 'ACTIVE'
)
RETURNS TABLE(branch_id BIGINT, workspace_id BIGINT, parent_branch_id BIGINT, branch_name VARCHAR,
              branch_type VARCHAR, status VARCHAR, source_context_id BIGINT,
              created_at TIMESTAMP, merged_at TIMESTAMP, abandoned_at TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT b.branch_id, b.workspace_id, b.parent_branch_id, b.branch_name,
           b.branch_type, b.status, b.source_context_id,
           b.created_at, b.merged_at, b.abandoned_at
    FROM context_branches b
    WHERE b.agent_id = p_agent_id
      AND (p_status IS NULL OR b.status = p_status)
    ORDER BY b.created_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.get_stats(
    p_branch_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_ctx_count     INT;
    v_session_count INT;
    v_duration_min  NUMERIC;
BEGIN
    SELECT COUNT(*) INTO v_ctx_count
    FROM workspace_context WHERE branch_id = p_branch_id;

    SELECT COUNT(*) INTO v_session_count
    FROM agent_session WHERE branch_id = p_branch_id;

    SELECT COALESCE(ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))) / 60), 0) INTO v_duration_min
    FROM agent_session WHERE branch_id = p_branch_id;

    RETURN jsonb_build_object(
        'branch_id', p_branch_id,
        'context_count', v_ctx_count,
        'session_count', v_session_count,
        'duration_minutes', v_duration_min
    );
EXCEPTION
    WHEN OTHERS THEN
        RETURN jsonb_build_object('branch_id', p_branch_id, 'error', 'not found');
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.mark_as_lesson(
    p_branch_id      BIGINT,
    p_context_id     BIGINT,
    p_lesson_type    VARCHAR,
    p_lesson_summary TEXT,
    p_lesson_detail  TEXT DEFAULT NULL,
    p_agent_id       VARCHAR DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_entity_id    BIGINT;
    v_workspace_id BIGINT;
BEGIN
    SELECT workspace_id INTO v_workspace_id
    FROM context_branches WHERE branch_id = p_branch_id;

    INSERT INTO entities (entity_type, title, content, category, status, owned_by_agent, visibility, workspace_id)
    VALUES ('KNOWLEDGE',
            '[' || p_lesson_type || '] ' || p_lesson_summary,
            p_lesson_detail, 'LESSON_LEARNED', 'ACTIVE',
            p_agent_id, 'SHARED', v_workspace_id)
    RETURNING entity_id INTO v_entity_id;

    INSERT INTO knowledge_meta (entity_id, domain, topic, difficulty)
    VALUES (v_entity_id, 'BRANCH_EXPERIENCE', substring(p_lesson_summary, 1, 50), 'INTERMEDIATE');

    IF p_context_id IS NOT NULL THEN
        INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength)
        VALUES (v_entity_id, 'KNOWLEDGE', p_context_id, 'KNOWLEDGE', 'DERIVED_FROM', 1.0);
    END IF;

    RETURN v_entity_id;
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.extract_lessons(
    p_branch_id    BIGINT,
    p_auto_confirm BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_error_count   INT := 0;
    v_summary_count INT := 0;
    v_workspace_id  BIGINT;
    v_agent_id      VARCHAR;
    v_rec           RECORD;
BEGIN
    SELECT workspace_id, agent_id INTO v_workspace_id, v_agent_id
    FROM context_branches WHERE branch_id = p_branch_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('branch_id', p_branch_id, 'error', 'not found');
    END IF;

    FOR v_rec IN
        SELECT context_id, context_data
        FROM workspace_context
        WHERE branch_id = p_branch_id AND context_type = 'ERROR_STATE'
    LOOP
        v_error_count := v_error_count + 1;
        IF p_auto_confirm THEN
            PERFORM branch_manager.mark_as_lesson(p_branch_id, v_rec.context_id, 'MISTAKE',
                'Error in abandoned branch', NULL, v_agent_id);
        END IF;
    END LOOP;

    FOR v_rec IN
        SELECT context_id, context_data
        FROM workspace_context
        WHERE branch_id = p_branch_id AND context_type = 'SUMMARY'
        ORDER BY created_at DESC LIMIT 1
    LOOP
        v_summary_count := v_summary_count + 1;
        IF p_auto_confirm THEN
            PERFORM branch_manager.mark_as_lesson(p_branch_id, v_rec.context_id, 'INSIGHT',
                'Branch summary', NULL, v_agent_id);
        END IF;
    END LOOP;

    RETURN jsonb_build_object(
        'branch_id', p_branch_id,
        'error_states_found', v_error_count,
        'summaries_found', v_summary_count,
        'auto_confirmed', p_auto_confirm
    );
END;
$$;

CREATE OR REPLACE FUNCTION branch_manager.cleanup(
    p_days_threshold INT DEFAULT 90
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    DELETE FROM branch_merge_log
    WHERE source_branch_id IN (
        SELECT branch_id FROM context_branches
        WHERE status = 'ABANDONED'
          AND abandoned_at < CURRENT_TIMESTAMP - (p_days_threshold || ' days')::INTERVAL
    );

    DELETE FROM workspace_context
    WHERE branch_id IN (
        SELECT branch_id FROM context_branches
        WHERE status = 'ABANDONED'
          AND abandoned_at < CURRENT_TIMESTAMP - (p_days_threshold || ' days')::INTERVAL
    );

    DELETE FROM agent_session
    WHERE branch_id IN (
        SELECT branch_id FROM context_branches
        WHERE status = 'ABANDONED'
          AND abandoned_at < CURRENT_TIMESTAMP - (p_days_threshold || ' days')::INTERVAL
    );

    DELETE FROM context_branches
    WHERE status = 'ABANDONED'
      AND abandoned_at < CURRENT_TIMESTAMP - (p_days_threshold || ' days')::INTERVAL;

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;


-- ============================================================
-- 11. Schema: skill_manager
-- ============================================================

CREATE SCHEMA IF NOT EXISTS skill_manager;

CREATE OR REPLACE FUNCTION skill_manager.register(
    p_skill_name     VARCHAR,
    p_skill_version  VARCHAR DEFAULT NULL,
    p_description    TEXT    DEFAULT NULL,
    p_skill_type     VARCHAR DEFAULT 'TOOL',
    p_category       VARCHAR DEFAULT NULL,
    p_visibility     VARCHAR DEFAULT 'SHARED',
    p_owned_by_agent VARCHAR DEFAULT NULL,
    p_input_schema   JSONB   DEFAULT NULL,
    p_output_schema  JSONB   DEFAULT NULL,
    p_dependencies   JSONB   DEFAULT NULL,
    p_resource_path  VARCHAR DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_skill_id BIGINT;
BEGIN
    INSERT INTO skill_meta (skill_name, skill_version, description, skill_type, category,
                            visibility, owned_by_agent, input_schema, output_schema,
                            dependencies, resource_path)
    VALUES (p_skill_name, p_skill_version, p_description, p_skill_type, p_category,
            p_visibility, p_owned_by_agent, p_input_schema, p_output_schema,
            p_dependencies, p_resource_path)
    RETURNING skill_id INTO v_skill_id;
    RETURN v_skill_id;
END;
$$;

CREATE OR REPLACE FUNCTION skill_manager.update(
    p_skill_id       BIGINT,
    p_skill_name     VARCHAR DEFAULT NULL,
    p_skill_version  VARCHAR DEFAULT NULL,
    p_description    TEXT    DEFAULT NULL,
    p_skill_type     VARCHAR DEFAULT NULL,
    p_category       VARCHAR DEFAULT NULL,
    p_visibility     VARCHAR DEFAULT NULL,
    p_input_schema   JSONB   DEFAULT NULL,
    p_output_schema  JSONB   DEFAULT NULL,
    p_dependencies   JSONB   DEFAULT NULL,
    p_resource_path  VARCHAR DEFAULT NULL,
    p_status         VARCHAR DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE skill_meta
    SET skill_name    = COALESCE(p_skill_name, skill_name),
        skill_version = COALESCE(p_skill_version, skill_version),
        description   = COALESCE(p_description, description),
        skill_type    = COALESCE(p_skill_type, skill_type),
        category      = COALESCE(p_category, category),
        visibility    = COALESCE(p_visibility, visibility),
        input_schema  = COALESCE(p_input_schema, input_schema),
        output_schema = COALESCE(p_output_schema, output_schema),
        dependencies  = COALESCE(p_dependencies, dependencies),
        resource_path = COALESCE(p_resource_path, resource_path),
        status        = COALESCE(p_status, status),
        updated_at    = CURRENT_TIMESTAMP
    WHERE skill_id = p_skill_id;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION skill_manager.delete(
    p_skill_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE skill_meta
    SET status = 'DEPRECATED', updated_at = CURRENT_TIMESTAMP
    WHERE skill_id = p_skill_id;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION skill_manager.get(
    p_skill_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'skill_id', skill_id,
        'skill_name', skill_name,
        'skill_version', skill_version,
        'description', description,
        'skill_type', skill_type,
        'category', category,
        'visibility', visibility,
        'owned_by_agent', owned_by_agent,
        'input_schema', input_schema,
        'output_schema', output_schema,
        'dependencies', dependencies,
        'resource_path', resource_path,
        'download_count', download_count,
        'rating', rating,
        'status', status,
        'created_at', to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS'),
        'updated_at', to_char(updated_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) INTO v_result
    FROM skill_meta
    WHERE skill_id = p_skill_id;

    RETURN v_result;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION skill_manager.list(
    p_skill_type VARCHAR DEFAULT NULL,
    p_category   VARCHAR DEFAULT NULL,
    p_status     VARCHAR DEFAULT 'ACTIVE',
    p_limit      INT     DEFAULT 50
)
RETURNS TABLE(skill_id BIGINT, skill_name VARCHAR, skill_version VARCHAR, description TEXT,
              skill_type VARCHAR, category VARCHAR, status VARCHAR,
              download_count INT, rating NUMERIC,
              created_at TIMESTAMP, updated_at TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT s.skill_id, s.skill_name, s.skill_version, s.description,
           s.skill_type, s.category, s.status,
           s.download_count, s.rating,
           s.created_at, s.updated_at
    FROM skill_meta s
    WHERE (p_skill_type IS NULL OR s.skill_type = p_skill_type)
      AND (p_category IS NULL OR s.category = p_category)
      AND (p_status IS NULL OR s.status = p_status)
    ORDER BY s.created_at DESC
    LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION skill_manager.search(
    p_query    TEXT,
    p_limit    INT     DEFAULT 20
)
RETURNS TABLE(skill_id BIGINT, skill_name VARCHAR, description TEXT,
              skill_type VARCHAR, category VARCHAR, rank REAL)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT s.skill_id, s.skill_name, s.description,
           s.skill_type, s.category,
           ts_rank(to_tsvector('english', COALESCE(s.skill_name, '') || ' ' || COALESCE(s.description, '')),
                   plainto_tsquery('english', p_query)) AS rank
    FROM skill_meta s
    WHERE to_tsvector('english', COALESCE(s.skill_name, '') || ' ' || COALESCE(s.description, ''))
          @@ plainto_tsquery('english', p_query)
      AND s.status = 'ACTIVE'
    ORDER BY rank DESC
    LIMIT p_limit;
END;
$$;


-- ============================================================
-- 12. Schema: user_manager
-- ============================================================

CREATE SCHEMA IF NOT EXISTS user_manager;

CREATE OR REPLACE FUNCTION user_manager.create(
    p_username VARCHAR,
    p_password TEXT    DEFAULT NULL,
    p_role     VARCHAR DEFAULT 'USER',
    p_auth_source VARCHAR DEFAULT 'LOCAL'
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id BIGINT;
    v_salt    VARCHAR;
    v_hash    TEXT;
BEGIN
    v_salt := encode(gen_random_bytes(16), 'hex');
    v_hash := 'SHA256:' || upper(encode(digest(COALESCE(p_password, 'changeme') || v_salt, 'sha256'), 'hex'));

    INSERT INTO system_users (username, password_hash, salt, role, status, auth_source)
    VALUES (p_username, v_hash, v_salt, p_role, 'ACTIVE', p_auth_source)
    RETURNING user_id INTO v_user_id;

    RETURN v_user_id;
EXCEPTION
    WHEN OTHERS THEN
        RETURN -1;
END;
$$;

CREATE OR REPLACE FUNCTION user_manager.authenticate(
    p_username VARCHAR,
    p_password TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_user       RECORD;
    v_test_hash  TEXT;
    v_salt       TEXT;
BEGIN
    SELECT user_id, username, password_hash, salt, role, status
    INTO v_user
    FROM system_users
    WHERE username = p_username AND status = 'ACTIVE';

    IF NOT FOUND THEN
        RETURN jsonb_build_object('authenticated', FALSE, 'reason', 'user_not_found');
    END IF;

    v_salt := COALESCE(v_user.salt, '');
    v_test_hash := 'SHA256:' || upper(encode(digest(p_password || v_salt, 'sha256'), 'hex'));

    IF v_test_hash != v_user.password_hash THEN
        RETURN jsonb_build_object('authenticated', FALSE, 'reason', 'invalid_password');
    END IF;

    UPDATE system_users SET last_login = CURRENT_TIMESTAMP WHERE user_id = v_user.user_id;

    RETURN jsonb_build_object(
        'authenticated', TRUE,
        'user_id', v_user.user_id,
        'username', v_user.username,
        'role', v_user.role
    );
END;
$$;

CREATE OR REPLACE FUNCTION user_manager.get_profile(
    p_user_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'user_id', user_id,
        'username', username,
        'role', role,
        'status', status,
        'auth_source', auth_source,
        'last_login', to_char(last_login, 'YYYY-MM-DD"T"HH24:MI:SS'),
        'created_at', to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) INTO v_result
    FROM system_users
    WHERE user_id = p_user_id;

    RETURN v_result;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION user_manager.update_last_login(
    p_user_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE system_users
    SET last_login = CURRENT_TIMESTAMP
    WHERE user_id = p_user_id;
END;
$$;


-- ============================================================
-- 13. Schema: deploy_api
-- ============================================================

CREATE SCHEMA IF NOT EXISTS deploy_api;

CREATE OR REPLACE FUNCTION deploy_api.check_deployment()
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployed      BOOLEAN := FALSE;
    v_schema_version VARCHAR;
    v_table_count   INT := 0;
    v_edition       VARCHAR;
    v_agent_count   INT := 0;
    v_user_count    INT := 0;
    v_recommendation TEXT;
BEGIN
    BEGIN
        SELECT COUNT(*) INTO v_table_count
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
    EXCEPTION WHEN OTHERS THEN
        v_table_count := 0;
    END;

    IF v_table_count = 0 THEN
        v_recommendation := 'No deployment detected. Safe to run full deployment.';
        RETURN jsonb_build_object(
            'deployed', FALSE,
            'schema_version', NULL,
            'table_count', 0,
            'edition', NULL,
            'agent_count', 0,
            'user_count', 0,
            'recommendation', v_recommendation
        );
    END IF;

    BEGIN
        SELECT config_value INTO v_schema_version
        FROM system_config WHERE config_key = 'schema_version';
        IF v_schema_version IS NOT NULL THEN
            v_deployed := TRUE;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    BEGIN
        SELECT config_value INTO v_edition
        FROM system_config WHERE config_key = 'license_type';
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    BEGIN
        SELECT COUNT(*) INTO v_agent_count FROM agent_registry;
    EXCEPTION WHEN OTHERS THEN
        v_agent_count := 0;
    END;

    BEGIN
        SELECT COUNT(*) INTO v_user_count FROM system_users;
    EXCEPTION WHEN OTHERS THEN
        v_user_count := 0;
    END;

    IF v_deployed THEN
        v_recommendation := 'EXISTING DEPLOYMENT DETECTED (v' || COALESCE(v_schema_version, '?') || ', '
            || v_table_count || ' tables, ' || v_agent_count || ' agents, '
            || v_user_count || ' users). DO NOT re-run deploy scripts.';
    ELSE
        v_recommendation := 'Database has ' || v_table_count
            || ' tables but no schema_version marker. This may be a partial deployment.';
    END IF;

    RETURN jsonb_build_object(
        'deployed', v_deployed,
        'schema_version', v_schema_version,
        'table_count', v_table_count,
        'edition', v_edition,
        'agent_count', v_agent_count,
        'user_count', v_user_count,
        'recommendation', v_recommendation
    );
END;
$$;


-- ============================================================
-- 14. Schema: audit_api [ENT]
-- ============================================================

CREATE SCHEMA IF NOT EXISTS audit_api;

CREATE OR REPLACE FUNCTION audit_api.log_access_event(
    p_entity_id      BIGINT,
    p_entity_type    VARCHAR,
    p_agent_id       VARCHAR,
    p_access_type    VARCHAR,
    p_session_id     BIGINT  DEFAULT NULL,
    p_workspace_id   BIGINT  DEFAULT NULL,
    p_context        JSONB   DEFAULT NULL,
    p_rule_violation VARCHAR DEFAULT NULL,
    p_violation_severity VARCHAR DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_audit_id BIGINT;
BEGIN
    INSERT INTO entity_access_audit (entity_id, entity_type, agent_id, access_type,
        session_id, workspace_id, context, rule_violation, violation_severity)
    VALUES (p_entity_id, p_entity_type, p_agent_id, p_access_type,
        p_session_id, p_workspace_id, p_context, p_rule_violation, p_violation_severity)
    RETURNING audit_id INTO v_audit_id;

    INSERT INTO entity_access_log (entity_id, entity_type, agent_id, access_type, session_id, context)
    VALUES (p_entity_id, p_entity_type, p_agent_id, p_access_type, p_session_id, p_context);

    RETURN v_audit_id;
END;
$$;

CREATE OR REPLACE FUNCTION audit_api.get_access_audit(
    p_resolution_status VARCHAR DEFAULT NULL,
    p_access_type       VARCHAR DEFAULT NULL,
    p_agent_id          VARCHAR DEFAULT NULL,
    p_limit             INT     DEFAULT 100
)
RETURNS TABLE(audit_id BIGINT, entity_id BIGINT, entity_type VARCHAR, agent_id VARCHAR,
              access_type VARCHAR, access_time TIMESTAMP, workspace_id BIGINT,
              rule_violation VARCHAR, violation_severity VARCHAR,
              resolution_status VARCHAR, resolved_by VARCHAR)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT eaa.audit_id, eaa.entity_id, eaa.entity_type, eaa.agent_id,
           eaa.access_type, eaa.access_time, eaa.workspace_id,
           eaa.rule_violation, eaa.violation_severity,
           eaa.resolution_status, eaa.resolved_by
    FROM entity_access_audit eaa
    WHERE (p_resolution_status IS NULL OR eaa.resolution_status = p_resolution_status)
      AND (p_access_type IS NULL OR eaa.access_type = p_access_type)
      AND (p_agent_id IS NULL OR eaa.agent_id = p_agent_id)
    ORDER BY eaa.access_time DESC
    LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION audit_api.get_workspace_audit(
    p_workspace_id BIGINT,
    p_action       VARCHAR DEFAULT NULL,
    p_limit        INT     DEFAULT 50
)
RETURNS TABLE(audit_id BIGINT, context_id BIGINT, workspace_id BIGINT, agent_id VARCHAR,
              action VARCHAR, old_data JSONB, new_data JSONB, diff_summary TEXT,
              created_at TIMESTAMP)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT wca.audit_id, wca.context_id, wca.workspace_id, wca.agent_id,
           wca.action, wca.old_data, wca.new_data, wca.diff_summary,
           wca.created_at
    FROM workspace_context_audit wca
    WHERE wca.workspace_id = p_workspace_id
      AND (p_action IS NULL OR wca.action = p_action)
    ORDER BY wca.created_at DESC
    LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION audit_api.get_compliance_report(
    p_regulation_type VARCHAR DEFAULT NULL,
    p_status          VARCHAR DEFAULT NULL,
    p_since           TIMESTAMP DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_total      INT;
    v_compliant  INT;
    v_non_comp   INT;
    v_pending    INT;
    v_items      JSONB;
BEGIN
    SELECT COUNT(*),
           COUNT(CASE WHEN cl.status = 'COMPLIANT' THEN 1 END),
           COUNT(CASE WHEN cl.status = 'NON_COMPLIANT' THEN 1 END),
           COUNT(CASE WHEN cl.status = 'PENDING_REVIEW' THEN 1 END)
    INTO v_total, v_compliant, v_non_comp, v_pending
    FROM compliance_log cl
    WHERE (p_regulation_type IS NULL OR cl.regulation_type = p_regulation_type)
      AND (p_status IS NULL OR cl.status = p_status)
      AND (p_since IS NULL OR cl.created_at >= p_since);

    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'compliance_id', cl.compliance_id,
        'regulation_type', cl.regulation_type,
        'check_type', cl.check_type,
        'entity_id', cl.entity_id,
        'status', cl.status,
        'details', cl.details,
        'created_at', to_char(cl.created_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) ORDER BY cl.created_at DESC), '[]'::jsonb) INTO v_items
    FROM compliance_log cl
    WHERE (p_regulation_type IS NULL OR cl.regulation_type = p_regulation_type)
      AND (p_status IS NULL OR cl.status = p_status)
      AND (p_since IS NULL OR cl.created_at >= p_since)
    LIMIT 50;

    RETURN jsonb_build_object(
        'total', v_total,
        'compliant', v_compliant,
        'non_compliant', v_non_comp,
        'pending_review', v_pending,
        'items', v_items
    );
END;
$$;

CREATE OR REPLACE FUNCTION audit_api.purge_audit_logs(
    p_retention_days INT DEFAULT 90
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_access_audit INT;
    v_access_log   INT;
    v_context_audit INT;
    v_compliance   INT;
BEGIN
    DELETE FROM entity_access_audit
    WHERE accessed_at < CURRENT_TIMESTAMP - (p_retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS v_access_audit = ROW_COUNT;

    DELETE FROM workspace_context_audit
    WHERE created_at < CURRENT_TIMESTAMP - (p_retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS v_context_audit = ROW_COUNT;

    DELETE FROM compliance_log
    WHERE created_at < CURRENT_TIMESTAMP - (p_retention_days || ' days')::INTERVAL
      AND status IN ('COMPLIANT','REMEDIATED');
    GET DIAGNOSTICS v_compliance = ROW_COUNT;

    DELETE FROM entity_access_log
    WHERE accessed_at < CURRENT_TIMESTAMP - (p_retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS v_access_log = ROW_COUNT;

    RETURN v_access_audit + v_context_audit + v_compliance + v_access_log;
END;
$$;


-- ============================================================
-- 15. Schema: skill_token_api [ENT]
-- ============================================================

CREATE SCHEMA IF NOT EXISTS skill_token_api;

CREATE OR REPLACE FUNCTION skill_token_api.request_access(
    p_skill_id    BIGINT,
    p_agent_id    VARCHAR,
    p_session_id  BIGINT  DEFAULT NULL,
    p_resource_url VARCHAR DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_token_id     BIGINT;
    v_token_value  VARCHAR;
    v_ttl_min      INT;
BEGIN
    SELECT config_value::INT INTO v_ttl_min
    FROM system_config WHERE config_key = 'skill_token_ttl_min';

    v_token_value := encode(gen_random_bytes(32), 'hex');

    INSERT INTO skill_access_token (skill_id, agent_id, session_id, resource_url,
        token_value, expires_at)
    VALUES (p_skill_id, p_agent_id, p_session_id, p_resource_url,
        v_token_value, CURRENT_TIMESTAMP + (COALESCE(v_ttl_min, 5) || ' minutes')::INTERVAL)
    RETURNING token_id INTO v_token_id;

    RETURN v_token_id;
END;
$$;

CREATE OR REPLACE FUNCTION skill_token_api.verify_token(
    p_token_value VARCHAR
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'token_id', token_id,
        'skill_id', skill_id,
        'agent_id', agent_id,
        'resource_url', resource_url,
        'is_consumed', is_consumed,
        'expires_at', to_char(expires_at, 'YYYY-MM-DD"T"HH24:MI:SS'),
        'valid', (NOT is_consumed AND expires_at > CURRENT_TIMESTAMP)
    ) INTO v_result
    FROM skill_access_token
    WHERE token_value = p_token_value;

    RETURN COALESCE(v_result, jsonb_build_object('found', FALSE));
EXCEPTION
    WHEN OTHERS THEN
        RETURN jsonb_build_object('found', FALSE);
END;
$$;

CREATE OR REPLACE FUNCTION skill_token_api.consume_token(
    p_token_value VARCHAR
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_rec     RECORD;
    v_result  JSONB;
BEGIN
    SELECT * INTO v_rec FROM skill_access_token
    WHERE token_value = p_token_value
      AND NOT is_consumed
      AND expires_at > CURRENT_TIMESTAMP;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('consumed', FALSE, 'reason', 'token_not_found_or_expired');
    END IF;

    UPDATE skill_access_token
    SET is_consumed = TRUE, consumed_at = CURRENT_TIMESTAMP
    WHERE token_id = v_rec.token_id;

    RETURN jsonb_build_object(
        'consumed', TRUE,
        'token_id', v_rec.token_id,
        'skill_id', v_rec.skill_id,
        'resource_url', v_rec.resource_url
    );
END;
$$;

CREATE OR REPLACE FUNCTION skill_token_api.cleanup_expired()
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected INT;
BEGIN
    DELETE FROM skill_access_token
    WHERE (is_consumed = TRUE OR expires_at < CURRENT_TIMESTAMP)
      AND created_at < CURRENT_TIMESTAMP - INTERVAL '7 days';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;


-- ============================================================
-- 16. Schema: ldap_auth [ENT]
-- ============================================================

CREATE SCHEMA IF NOT EXISTS ldap_auth;

CREATE OR REPLACE FUNCTION ldap_auth.configure(
    p_server_url         VARCHAR,
    p_base_dn            VARCHAR,
    p_bind_dn            VARCHAR DEFAULT NULL,
    p_bind_credential    TEXT    DEFAULT NULL,
    p_user_filter        VARCHAR DEFAULT '(uid={username})',
    p_group_filter       VARCHAR DEFAULT '(memberUid={username})',
    p_use_tls            BOOLEAN DEFAULT TRUE,
    p_sync_interval_min  INT     DEFAULT 60,
    p_group_role_mapping JSONB   DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_config_id BIGINT;
BEGIN
    INSERT INTO ldap_config (config_name, server_url, search_base, bind_dn, bind_password,
        search_filter, group_filter, use_ssl, port, sync_interval_min, group_role_mapping)
    VALUES ('ldap-' || gen_random_uuid()::text, p_server_url, p_base_dn, p_bind_dn, p_bind_credential,
        p_user_filter, p_group_filter, p_use_tls, CASE WHEN p_use_tls THEN 636 ELSE 389 END,
        p_sync_interval_min, p_group_role_mapping)
    RETURNING config_id INTO v_config_id;

    RETURN v_config_id;
END;
$$;

CREATE OR REPLACE FUNCTION ldap_auth.get_config(
    p_config_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'config_id', config_id,
        'server_url', server_url,
        'base_dn', search_base,
        'bind_dn', bind_dn,
        'user_filter', search_filter,
        'group_filter', group_filter,
        'use_tls', use_ssl,
        'status', CASE WHEN is_active THEN 'ACTIVE' ELSE 'INACTIVE' END,
        'sync_interval_min', sync_interval_min,
        'last_sync_at', to_char(last_sync_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) INTO v_result
    FROM ldap_config WHERE config_id = p_config_id;

    RETURN COALESCE(v_result, jsonb_build_object('found', FALSE));
END;
$$;

CREATE OR REPLACE FUNCTION ldap_auth.test_connection(
    p_config_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'config_id', config_id,
        'server_url', server_url,
        'reachable', 'UNKNOWN',
        'message', 'Python-side ldap3 test required for actual connection verification'
    ) INTO v_result
    FROM ldap_config WHERE config_id = p_config_id;

    RETURN COALESCE(v_result, jsonb_build_object('found', FALSE));
END;
$$;

CREATE OR REPLACE FUNCTION ldap_auth.deactivate(
    p_config_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE ldap_config
    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
    WHERE config_id = p_config_id;

    RETURN FOUND;
END;
$$;


-- ============================================================
-- 17. loop_manager schema [NEW v3.7.5]
-- ============================================================

CREATE SCHEMA IF NOT EXISTS loop_manager;

-- Check stop conditions for a run
CREATE OR REPLACE FUNCTION loop_manager.check_stop_conditions(p_run_id BIGINT)
RETURNS VARCHAR
LANGUAGE plpgsql
AS $$
DECLARE
    v_run        RECORD;
    v_stop       JSONB;
    v_max_iter   INT;
    v_max_tokens BIGINT;
    v_max_dur    INT;
    v_elapsed    DOUBLE PRECISION;
BEGIN
    SELECT * INTO v_run FROM loop_runs WHERE run_id = p_run_id;
    IF NOT FOUND THEN RETURN 'STOP'; END IF;
    SELECT m.stop_conditions INTO v_stop
    FROM loop_meta m WHERE m.entity_id = v_run.loop_id;
    IF NOT FOUND THEN RETURN 'STOP'; END IF;
    v_max_iter   := (v_stop->>'max_iterations')::INT;
    v_max_tokens := (v_stop->>'max_tokens')::BIGINT;
    v_max_dur    := (v_stop->>'max_duration_seconds')::INT;
    IF v_max_iter IS NOT NULL AND v_run.iteration_count >= v_max_iter THEN
        RETURN 'STOP';
    END IF;
    IF v_max_tokens IS NOT NULL AND v_run.total_tokens >= v_max_tokens THEN
        RETURN 'STOP';
    END IF;
    IF v_max_dur IS NOT NULL THEN
        v_elapsed := EXTRACT(EPOCH FROM (NOW() - v_run.started_at));
        IF v_elapsed >= v_max_dur THEN
            RETURN 'TIMEOUT';
        END IF;
    END IF;
    RETURN 'CONTINUE';
END;
$$;

-- Process scheduled triggers (called by pg_cron)
CREATE OR REPLACE FUNCTION loop_manager.process_scheduled_triggers()
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    rec RECORD;
    v_run_id BIGINT;
BEGIN
    FOR rec IN (
        SELECT e.entity_id AS loop_id, e.owned_by_agent
        FROM entities e
        JOIN loop_meta m ON e.entity_id = m.entity_id
        WHERE e.entity_type = 'LOOP_DEFINITION'
          AND e.status = 'ACTIVE'
          AND m.trigger_config IS NOT NULL
          AND m.trigger_config->>'trigger_type' = 'SCHEDULE'
          AND NOT EXISTS (
              SELECT 1 FROM loop_runs lr
              WHERE lr.loop_id = e.entity_id AND lr.status IN ('RUNNING','PAUSED')
          )
    ) LOOP
        INSERT INTO loop_runs (loop_id, agent_id, trigger_type, trigger_source, status, started_at)
        VALUES (rec.loop_id, COALESCE(rec.owned_by_agent, 'system'), 'SCHEDULE', 'cron', 'RUNNING', NOW())
        RETURNING run_id INTO v_run_id;
        PERFORM loop_manager.log_audit(rec.loop_id, v_run_id, 'START_RUN', 'cron', jsonb_build_object('trigger_type', 'SCHEDULE'));
    END LOOP;
END;
$$;

-- Check for stuck runs (called by pg_cron)
CREATE OR REPLACE FUNCTION loop_manager.check_stuck_runs()
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    rec RECORD;
    v_max_dur INT;
    v_stop    JSONB;
BEGIN
    FOR rec IN (
        SELECT r.run_id, r.loop_id, r.started_at
        FROM loop_runs r
        WHERE r.status = 'RUNNING'
    ) LOOP
        BEGIN
            SELECT m.stop_conditions INTO v_stop
            FROM loop_meta m WHERE m.entity_id = rec.loop_id;
            v_max_dur := (v_stop->>'max_duration_seconds')::INT;
            IF v_max_dur IS NOT NULL THEN
                IF EXTRACT(EPOCH FROM (NOW() - rec.started_at)) >= v_max_dur THEN
                    UPDATE loop_runs SET status = 'TIMEOUT', completed_at = NOW(),
                        error_message = 'Run timed out'
                    WHERE run_id = rec.run_id;
                    PERFORM loop_manager.log_audit(rec.loop_id, rec.run_id, 'TIMEOUT', 'cron', NULL);
                END IF;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            CONTINUE;
        END;
    END LOOP;
END;
$$;

-- Cleanup old runs (called by pg_cron)
CREATE OR REPLACE FUNCTION loop_manager.cleanup_old_runs(p_days_threshold INT DEFAULT 90)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INT;
    v_temp  INT;
BEGIN
    DELETE FROM loop_iterations
    WHERE run_id IN (
        SELECT run_id FROM loop_runs
        WHERE status IN ('COMPLETED','STOPPED','FAILED','TIMEOUT')
          AND completed_at < NOW() - (p_days_threshold || ' days')::INTERVAL
    );
    GET DIAGNOSTICS v_count = ROW_COUNT;
    DELETE FROM loop_runs
    WHERE status IN ('COMPLETED','STOPPED','FAILED','TIMEOUT')
      AND completed_at < NOW() - (p_days_threshold || ' days')::INTERVAL;
    GET DIAGNOSTICS v_temp = ROW_COUNT;
    v_count := v_count + v_temp;
    PERFORM loop_manager.log_audit(NULL, NULL, 'CLEANUP', 'cron', jsonb_build_object('days_threshold', p_days_threshold, 'rows_removed', v_count));
    RETURN v_count;
END;
$$;

-- Log an audit entry for a loop lifecycle action [ENT-ONLY v3.7.5]
CREATE OR REPLACE FUNCTION loop_manager.log_audit(p_loop_id BIGINT, p_run_id BIGINT, p_action_type VARCHAR, p_action_by VARCHAR, p_action_detail JSONB DEFAULT NULL)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE v_id BIGINT;
BEGIN
    INSERT INTO loop_audit (loop_id, run_id, action_type, action_by, action_detail)
    VALUES (p_loop_id, p_run_id, p_action_type, p_action_by, p_action_detail)
    RETURNING audit_id INTO v_id;
    RETURN v_id;
END;
$$;


-- ============================================================
-- AI Agent Infra v5.0.0 - PostgreSQL 18.3 API Deployment Complete
-- ============================================================

-- v3.10.0: Create AGE graph if not exists
DO $$
BEGIN
    PERFORM * FROM ag_catalog.graph WHERE name = 'oracle_memory_graph';
EXCEPTION WHEN OTHERS THEN
    BEGIN
        PERFORM ag_catalog.create_graph('oracle_memory_graph');
    EXCEPTION WHEN OTHERS THEN
        -- AGE extension not available or graph already exists, continue with SQL fallback
    END;
END $$;
