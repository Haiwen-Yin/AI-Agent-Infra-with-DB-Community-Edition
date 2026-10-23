-- ============================================================
-- AI Agent Infra v5.0.1 - Phase 2: PL/SQL API Packages
-- ============================================================

WHENEVER SQLERROR CONTINUE;
WHENEVER OSERROR CONTINUE;

CREATE OR REPLACE PACKAGE MEMORY_FUSION_ENGINE AS
    PROCEDURE fuse_similar_memories(
        p_category       IN VARCHAR2 DEFAULT NULL,
        p_min_similarity IN NUMBER   DEFAULT 0.85,
        p_dry_run        IN VARCHAR2 DEFAULT 'Y'
    );
    PROCEDURE extract_knowledge_from_memories(
        p_category  IN VARCHAR2 DEFAULT NULL,
        p_min_count IN NUMBER   DEFAULT 3
    );
    PROCEDURE decay_old_memories(
        p_days_threshold IN NUMBER DEFAULT 90,
        p_decay_factor   IN NUMBER DEFAULT 0.5
    );
    FUNCTION get_fusion_stats RETURN JSON;
END MEMORY_FUSION_ENGINE;
/

-- YashanDB JSON compatibility: JSON_OBJECT replaced with JSON('{}')
-- Real JSON generation handled by Python API layer


CREATE OR REPLACE PACKAGE BODY MEMORY_FUSION_ENGINE AS

    PROCEDURE fuse_similar_memories(
        p_category       IN VARCHAR2 DEFAULT NULL,
        p_min_similarity IN NUMBER   DEFAULT 0.85,
        p_dry_run        IN VARCHAR2 DEFAULT 'Y'
    ) IS
        v_fused_count NUMBER := 0;
    BEGIN
        FOR pair IN (
            SELECT
                e1.ENTITY_ID AS id1, e1.ENTITY_TYPE AS type1,
                e2.ENTITY_ID AS id2, e2.ENTITY_TYPE AS type2,
                e1.CATEGORY AS cat
            FROM ENTITIES e1
            JOIN ENTITIES e2
                ON e1.ENTITY_TYPE = 'MEMORY'
               AND e2.ENTITY_TYPE = 'MEMORY'
               AND e1.ENTITY_ID < e2.ENTITY_ID
               AND (p_category IS NULL OR e1.CATEGORY = p_category)
               AND e1.CATEGORY = e2.CATEGORY
               AND e1.STATUS = 'ACTIVE'
               AND e2.STATUS = 'ACTIVE'
            WHERE DBMS_LOB.SUBSTR(e1.CONTENT, 4000) LIKE '%' || SUBSTR(e2.TITLE, 1, 20) || '%'
               OR DBMS_LOB.SUBSTR(e2.CONTENT, 4000) LIKE '%' || SUBSTR(e1.TITLE, 1, 20) || '%'
        ) LOOP
            IF p_dry_run = 'N' THEN
                INSERT INTO ENTITY_EDGES (
                    EDGE_ID, SOURCE_ID, SOURCE_TYPE, TARGET_ID,
                    EDGE_TYPE, STRENGTH, CONFIDENCE, METADATA, CREATED_AT
                ) VALUES (
                    'E_' || RAWTOHEX(SYS_GUID()),
                    pair.id1, pair.type1, pair.id2,
                    'SIMILAR_TO', p_min_similarity, 0.9,
                    JSON('{}'),
                    SYSTIMESTAMP
                );

                UPDATE ENTITIES
                SET STATUS = 'ARCHIVED', UPDATED_AT = SYSTIMESTAMP
                WHERE ENTITY_ID = pair.id2
                  AND ENTITY_TYPE = pair.type2;

                v_fused_count := v_fused_count + 1;
            END IF;
        END LOOP;

        MERGE INTO SYSTEM_CONFIG t
        USING (SELECT 'fusion.last_run' AS CONFIG_KEY FROM DUAL) s
        ON (t.CONFIG_KEY = s.CONFIG_KEY)
        WHEN MATCHED THEN UPDATE
            SET CONFIG_VALUE = TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
                DESCRIPTION  = 'Last fusion run: ' || v_fused_count || ' memories fused',
                UPDATED_AT   = SYSTIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT)
            VALUES (
                'fusion.last_run',
                TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
                'Last fusion run: ' || v_fused_count || ' memories fused',
                SYSTIMESTAMP
            );

        COMMIT;
    END fuse_similar_memories;

    PROCEDURE extract_knowledge_from_memories(
        p_category  IN VARCHAR2 DEFAULT NULL,
        p_min_count IN NUMBER   DEFAULT 3
    ) IS
        v_new_id    VARCHAR2(64);
        v_extracted NUMBER := 0;
    BEGIN
        FOR grp IN (
            SELECT CATEGORY, COUNT(*) AS cnt
            FROM ENTITIES
            WHERE ENTITY_TYPE = 'MEMORY'
              AND STATUS = 'ACTIVE'
              AND (p_category IS NULL OR CATEGORY = p_category)
            GROUP BY CATEGORY
            HAVING COUNT(*) >= p_min_count
        ) LOOP
            v_new_id := RAWTOHEX(SYS_GUID());

            INSERT INTO ENTITIES (
                ENTITY_ID, ENTITY_TYPE, TITLE, SUMMARY, CATEGORY,
                STATUS, OWNED_BY_AGENT, SOURCE_AGENT, VISIBILITY,
                IMPORTANCE, RETRIEVAL_COUNT, CREATED_AT, UPDATED_AT
            ) VALUES (
                v_new_id, 'KNOWLEDGE',
                'Extracted: ' || grp.CATEGORY || ' patterns',
                'Auto-extracted knowledge from ' || grp.cnt || ' memories in category ' || grp.CATEGORY,
                grp.CATEGORY,
                'ACTIVE', 'SYSTEM', 'SYSTEM', 'SHARED',
                5, 0, SYSTIMESTAMP, SYSTIMESTAMP
            );

            INSERT INTO KNOWLEDGE_META (
                ENTITY_ID, ENTITY_TYPE, DOMAIN, TOPIC,
                DIFFICULTY, REVIEW_COUNT, NEXT_REVIEW
            ) VALUES (
                v_new_id, 'KNOWLEDGE',
                grp.CATEGORY, grp.CATEGORY,
                'INTERMEDIATE', 0,
                SYSTIMESTAMP + NUMTODSINTERVAL(7, 'DAY')
            );

            v_extracted := v_extracted + 1;
        END LOOP;

        MERGE INTO SYSTEM_CONFIG t
        USING (SELECT 'knowledge.last_extraction' AS CONFIG_KEY FROM DUAL) s
        ON (t.CONFIG_KEY = s.CONFIG_KEY)
        WHEN MATCHED THEN UPDATE
            SET CONFIG_VALUE = TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
                DESCRIPTION  = 'Last extraction: ' || v_extracted || ' knowledge items created',
                UPDATED_AT   = SYSTIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT)
            VALUES (
                'knowledge.last_extraction',
                TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
                'Last extraction: ' || v_extracted || ' knowledge items created',
                SYSTIMESTAMP
            );

        COMMIT;
    END extract_knowledge_from_memories;

    PROCEDURE decay_old_memories(
        p_days_threshold IN NUMBER DEFAULT 90,
        p_decay_factor   IN NUMBER DEFAULT 0.5
    ) IS
    BEGIN
        UPDATE ENTITIES
        SET IMPORTANCE = GREATEST(1, ROUND(IMPORTANCE * p_decay_factor)),
            UPDATED_AT = SYSTIMESTAMP
        WHERE ENTITY_TYPE = 'MEMORY'
          AND STATUS = 'ACTIVE'
          AND CREATED_AT < SYSTIMESTAMP - p_days_threshold;

        COMMIT;
    END decay_old_memories;

    FUNCTION get_fusion_stats RETURN JSON IS
        v_stats JSON;
    BEGIN
        SELECT JSON('{}') INTO v_stats FROM DUAL;
        RETURN v_stats;
    END get_fusion_stats;

END MEMORY_FUSION_ENGINE;
/

CREATE OR REPLACE PACKAGE KNOWLEDGE_BASE_API AS
    PROCEDURE schedule_review(
        p_entity_id   IN VARCHAR2,
        p_entity_type IN VARCHAR2
    );
    PROCEDURE record_review(
        p_entity_id   IN VARCHAR2,
        p_entity_type IN VARCHAR2
    );
    FUNCTION get_due_reviews RETURN SYS_REFCURSOR;
    FUNCTION get_concept_lineage(
        p_entity_id   IN VARCHAR2,
        p_entity_type IN VARCHAR2
    ) RETURN JSON;
END KNOWLEDGE_BASE_API;
/

CREATE OR REPLACE PACKAGE BODY KNOWLEDGE_BASE_API AS

    PROCEDURE schedule_review(
        p_entity_id   IN VARCHAR2,
        p_entity_type IN VARCHAR2
    ) IS
    BEGIN
        UPDATE KNOWLEDGE_META
        SET NEXT_REVIEW = SYSTIMESTAMP +
            NUMTODSINTERVAL(LEAST(POWER(2, NVL(REVIEW_COUNT, 0)), 30), 'DAY')
        WHERE ENTITY_ID = p_entity_id
          AND ENTITY_TYPE = p_entity_type;

        COMMIT;
    END schedule_review;

    PROCEDURE record_review(
        p_entity_id   IN VARCHAR2,
        p_entity_type IN VARCHAR2
    ) IS
    BEGIN
        UPDATE KNOWLEDGE_META
        SET REVIEW_COUNT  = REVIEW_COUNT + 1,
            LAST_REVIEWED = SYSTIMESTAMP,
            NEXT_REVIEW   = SYSTIMESTAMP +
                NUMTODSINTERVAL(LEAST(POWER(2, REVIEW_COUNT + 1), 30), 'DAY')
        WHERE ENTITY_ID = p_entity_id
          AND ENTITY_TYPE = p_entity_type;

        COMMIT;
    END record_review;

    FUNCTION get_due_reviews RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT
                e.ENTITY_ID, e.ENTITY_TYPE, e.TITLE, e.CATEGORY,
                km.DOMAIN, km.TOPIC, km.DIFFICULTY,
                km.REVIEW_COUNT, km.LAST_REVIEWED, km.NEXT_REVIEW
            FROM ENTITIES e
            JOIN KNOWLEDGE_META km
                ON km.ENTITY_ID = e.ENTITY_ID
               AND km.ENTITY_TYPE = e.ENTITY_TYPE
            WHERE e.STATUS = 'ACTIVE'
              AND km.NEXT_REVIEW <= SYSTIMESTAMP
            ORDER BY km.NEXT_REVIEW;

        RETURN v_cur;
    END get_due_reviews;

    FUNCTION get_concept_lineage(
        p_entity_id   IN VARCHAR2,
        p_entity_type IN VARCHAR2
    ) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON('{}') INTO v_result FROM DUAL;

        RETURN v_result;
    END get_concept_lineage;

END KNOWLEDGE_BASE_API;
/

CREATE OR REPLACE PACKAGE AGENT_PERMISSION_MANAGER AS
    FUNCTION check_entity_access(
        p_agent_id  IN VARCHAR2,
        p_entity_id IN VARCHAR2
    ) RETURN VARCHAR2;
    FUNCTION check_workspace_access(
        p_agent_id  IN VARCHAR2,
        p_entity_id IN VARCHAR2
    ) RETURN VARCHAR2;
    PROCEDURE log_access(
        p_agent_id    IN VARCHAR2,
        p_entity_id   IN VARCHAR2,
        p_access_type IN VARCHAR2,
        p_session_id  IN VARCHAR2 DEFAULT NULL
    );
    PROCEDURE cleanup_expired_sessions;
    PROCEDURE process_collaboration_requests;
END AGENT_PERMISSION_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY AGENT_PERMISSION_MANAGER AS

    FUNCTION check_workspace_access(
        p_agent_id  IN VARCHAR2,
        p_entity_id IN VARCHAR2
    ) RETURN VARCHAR2 IS
        v_workspace_id  VARCHAR2(64);
        v_session_count NUMBER;
    BEGIN
        SELECT WORKSPACE_ID
        INTO v_workspace_id
        FROM ENTITIES
        WHERE ENTITY_ID = p_entity_id;

        SELECT COUNT(*)
        INTO v_session_count
        FROM AGENT_SESSION
        WHERE AGENT_ID = p_agent_id
          AND WORKSPACE_ID = v_workspace_id
          AND IS_ACTIVE = 'Y';

        IF v_session_count > 0 THEN
            RETURN 'GRANTED';
        ELSE
            RETURN 'DENIED';
        END IF;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN 'DENIED';
    END check_workspace_access;

    FUNCTION check_entity_access(
        p_agent_id  IN VARCHAR2,
        p_entity_id IN VARCHAR2
    ) RETURN VARCHAR2 IS
        v_visibility    VARCHAR2(16);
        v_owner         VARCHAR2(64);
        v_workspace_id  VARCHAR2(64);
    BEGIN
        SELECT VISIBILITY, OWNED_BY_AGENT, WORKSPACE_ID
        INTO v_visibility, v_owner, v_workspace_id
        FROM ENTITIES
        WHERE ENTITY_ID = p_entity_id;

        IF v_visibility = 'PRIVATE' AND v_owner = p_agent_id THEN
            IF v_workspace_id IS NOT NULL THEN
                RETURN check_workspace_access(p_agent_id, p_entity_id);
            END IF;
            RETURN 'GRANTED';
        ELSIF v_visibility = 'SHARED' THEN
            IF v_workspace_id IS NOT NULL THEN
                RETURN check_workspace_access(p_agent_id, p_entity_id);
            END IF;
            RETURN 'GRANTED';
        ELSE
            RETURN 'DENIED';
        END IF;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN 'DENIED';
    END check_entity_access;

    PROCEDURE log_access(
        p_agent_id    IN VARCHAR2,
        p_entity_id   IN VARCHAR2,
        p_access_type IN VARCHAR2,
        p_session_id  IN VARCHAR2 DEFAULT NULL
    ) IS
    BEGIN
        INSERT INTO ENTITY_ACCESS_LOG (
            LOG_ID, ENTITY_ID, AGENT_ID,
            ACCESS_TYPE, ACCESS_TIME, SESSION_ID, CONTEXT
        ) VALUES (
            'LOG_' || RAWTOHEX(SYS_GUID()),
            p_entity_id, p_agent_id,
            p_access_type, SYSTIMESTAMP, p_session_id, NULL
        );

        COMMIT;
    END log_access;

    PROCEDURE cleanup_expired_sessions IS
    BEGIN
        UPDATE AGENT_SESSION
        SET IS_ACTIVE = 'N',
            END_TIME  = SYSTIMESTAMP
        WHERE IS_ACTIVE = 'Y'
          AND START_TIME < SYSTIMESTAMP - NUMTODSINTERVAL(300, 'MINUTE');

        COMMIT;
    END cleanup_expired_sessions;

    PROCEDURE process_collaboration_requests IS
    BEGIN
        NULL;
    END process_collaboration_requests;

END AGENT_PERMISSION_MANAGER;
/

CREATE OR REPLACE PACKAGE SESSION_CLEANUP AS
    PROCEDURE purge_access_logs(p_days_to_keep IN NUMBER DEFAULT 90);
    PROCEDURE purge_inactive_sessions(p_days_to_keep IN NUMBER DEFAULT 30);
    PROCEDURE archive_old_entities(p_days_threshold IN NUMBER DEFAULT 180);
    PROCEDURE update_tag_counts;
END SESSION_CLEANUP;
/

CREATE OR REPLACE PACKAGE BODY SESSION_CLEANUP AS

    PROCEDURE purge_access_logs(p_days_to_keep IN NUMBER DEFAULT 90) IS
    BEGIN
        DELETE FROM ENTITY_ACCESS_LOG
        WHERE ACCESS_TIME < SYSTIMESTAMP - p_days_to_keep;

        COMMIT;
    END purge_access_logs;

    PROCEDURE purge_inactive_sessions(p_days_to_keep IN NUMBER DEFAULT 30) IS
    BEGIN
        DELETE FROM AGENT_SESSION
        WHERE IS_ACTIVE = 'N'
          AND END_TIME < SYSTIMESTAMP - p_days_to_keep;

        COMMIT;
    END purge_inactive_sessions;

    PROCEDURE archive_old_entities(p_days_threshold IN NUMBER DEFAULT 180) IS
    BEGIN
        UPDATE ENTITIES
        SET STATUS = 'ARCHIVED', UPDATED_AT = SYSTIMESTAMP
        WHERE ENTITY_TYPE = 'MEMORY'
          AND STATUS = 'ACTIVE'
          AND CREATED_AT < SYSTIMESTAMP - p_days_threshold
          AND IMPORTANCE <= 1;

        COMMIT;
    END archive_old_entities;

    PROCEDURE update_tag_counts IS
    BEGIN
        NULL;
    END update_tag_counts;

END SESSION_CLEANUP;
/

CREATE OR REPLACE PACKAGE WORKSPACE_MANAGER AS
    PROCEDURE create_workspace(
        p_workspace_id   IN VARCHAR2,
        p_owner_user_id  IN VARCHAR2,
        p_workspace_name IN VARCHAR2,
        p_workspace_type IN VARCHAR2 DEFAULT 'CONVERSATION',
        p_isolation_mode IN VARCHAR2 DEFAULT 'SHARED',
        p_metadata       IN JSON DEFAULT NULL
    );
    PROCEDURE update_workspace(
        p_workspace_id   IN VARCHAR2,
        p_workspace_name IN VARCHAR2 DEFAULT NULL,
        p_status         IN VARCHAR2 DEFAULT NULL,
        p_isolation_mode IN VARCHAR2 DEFAULT NULL,
        p_current_agent  IN VARCHAR2 DEFAULT NULL,
        p_summary        IN VARCHAR2 DEFAULT NULL,
        p_metadata       IN JSON DEFAULT NULL
    );
    PROCEDURE pause_workspace(p_workspace_id IN VARCHAR2);
    PROCEDURE complete_workspace(p_workspace_id IN VARCHAR2);
    PROCEDURE save_context(
        p_context_id   IN VARCHAR2,
        p_workspace_id IN VARCHAR2,
        p_agent_id     IN VARCHAR2,
        p_context_type IN VARCHAR2,
        p_context_data IN JSON,
        p_session_id   IN VARCHAR2 DEFAULT NULL,
        p_parent_ctx   IN VARCHAR2 DEFAULT NULL
    );
    FUNCTION get_latest_context(p_workspace_id IN VARCHAR2) RETURN JSON;
    FUNCTION get_context_chain(p_workspace_id IN VARCHAR2, p_limit IN NUMBER DEFAULT 10) RETURN JSON;
    PROCEDURE link_task(
        p_workspace_id IN VARCHAR2,
        p_plan_id      IN VARCHAR2
    );
    PROCEDURE unlink_task(
        p_workspace_id IN VARCHAR2,
        p_plan_id      IN VARCHAR2
    );
    PROCEDURE cleanup_abandoned(p_days_threshold IN NUMBER DEFAULT 30);
END WORKSPACE_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY WORKSPACE_MANAGER AS

    PROCEDURE create_workspace(
        p_workspace_id   IN VARCHAR2,
        p_owner_user_id  IN VARCHAR2,
        p_workspace_name IN VARCHAR2,
        p_workspace_type IN VARCHAR2 DEFAULT 'CONVERSATION',
        p_isolation_mode IN VARCHAR2 DEFAULT 'SHARED',
        p_metadata       IN JSON DEFAULT NULL
    ) IS
    BEGIN
        INSERT INTO WORKSPACES (
            WORKSPACE_ID, OWNER_USER_ID, WORKSPACE_NAME,
            WORKSPACE_TYPE, ISOLATION_MODE, METADATA
        ) VALUES (
            p_workspace_id, p_owner_user_id, p_workspace_name,
            p_workspace_type, p_isolation_mode, p_metadata
        );

        COMMIT;
    END create_workspace;

    PROCEDURE update_workspace(
        p_workspace_id   IN VARCHAR2,
        p_workspace_name IN VARCHAR2 DEFAULT NULL,
        p_status         IN VARCHAR2 DEFAULT NULL,
        p_isolation_mode IN VARCHAR2 DEFAULT NULL,
        p_current_agent  IN VARCHAR2 DEFAULT NULL,
        p_summary        IN VARCHAR2 DEFAULT NULL,
        p_metadata       IN JSON DEFAULT NULL
    ) IS
    BEGIN
        UPDATE WORKSPACES
        SET WORKSPACE_NAME   = COALESCE(p_workspace_name, WORKSPACE_NAME),
            STATUS           = COALESCE(p_status, STATUS),
            ISOLATION_MODE   = COALESCE(p_isolation_mode, ISOLATION_MODE),
            CURRENT_AGENT_ID = COALESCE(p_current_agent, CURRENT_AGENT_ID),
            SUMMARY          = COALESCE(p_summary, SUMMARY),
            METADATA         = COALESCE(p_metadata, METADATA),
            UPDATED_AT       = SYSTIMESTAMP
        WHERE WORKSPACE_ID = p_workspace_id;

        COMMIT;
    END update_workspace;

    PROCEDURE pause_workspace(p_workspace_id IN VARCHAR2) IS
    BEGIN
        UPDATE WORKSPACES
        SET STATUS    = 'PAUSED',
            UPDATED_AT = SYSTIMESTAMP
        WHERE WORKSPACE_ID = p_workspace_id;

        COMMIT;
    END pause_workspace;

    PROCEDURE complete_workspace(p_workspace_id IN VARCHAR2) IS
    BEGIN
        UPDATE WORKSPACES
        SET STATUS    = 'COMPLETED',
            UPDATED_AT = SYSTIMESTAMP
        WHERE WORKSPACE_ID = p_workspace_id;

        COMMIT;
    END complete_workspace;

    PROCEDURE save_context(
        p_context_id   IN VARCHAR2,
        p_workspace_id IN VARCHAR2,
        p_agent_id     IN VARCHAR2,
        p_context_type IN VARCHAR2,
        p_context_data IN JSON,
        p_session_id   IN VARCHAR2 DEFAULT NULL,
        p_parent_ctx   IN VARCHAR2 DEFAULT NULL
    ) IS
    BEGIN
        INSERT INTO WORKSPACE_CONTEXT (
            CONTEXT_ID, WORKSPACE_ID, AGENT_ID,
            SESSION_ID, CONTEXT_TYPE, CONTEXT_DATA, PARENT_CONTEXT_ID
        ) VALUES (
            p_context_id, p_workspace_id, p_agent_id,
            p_session_id, p_context_type, p_context_data, p_parent_ctx
        );

        COMMIT;
    END save_context;

    FUNCTION get_latest_context(p_workspace_id IN VARCHAR2) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON('{}')
        INTO v_result
        FROM WORKSPACE_CONTEXT
        WHERE WORKSPACE_ID = p_workspace_id
        ORDER BY CREATED_AT DESC
        FETCH FIRST 1 ROW ONLY;

        RETURN v_result;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN NULL;
    END get_latest_context;

    FUNCTION get_context_chain(
        p_workspace_id IN VARCHAR2,
        p_limit        IN NUMBER DEFAULT 10
    ) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON(
            CASE WHEN COUNT(*) = 0 THEN '[]'
                 ELSE '[' || LISTAGG('{}', ',')
                      WITHIN GROUP (ORDER BY CREATED_AT DESC) || ']'
            END
        )
        INTO v_result
        FROM (
            SELECT *
            FROM WORKSPACE_CONTEXT
            WHERE WORKSPACE_ID = p_workspace_id
            ORDER BY CREATED_AT DESC
            FETCH FIRST p_limit ROWS ONLY
        );

        RETURN v_result;
    END get_context_chain;

    PROCEDURE link_task(
        p_workspace_id IN VARCHAR2,
        p_plan_id      IN VARCHAR2
    ) IS
    BEGIN
        MERGE INTO WORKSPACE_TASKS t
        USING (SELECT p_workspace_id AS WORKSPACE_ID, p_plan_id AS PLAN_ID FROM DUAL) s
        ON (t.WORKSPACE_ID = s.WORKSPACE_ID AND t.PLAN_ID = s.PLAN_ID)
        WHEN NOT MATCHED THEN INSERT
            (WORKSPACE_ID, PLAN_ID, ASSIGNED_AT)
            VALUES (s.WORKSPACE_ID, s.PLAN_ID, SYSTIMESTAMP);

        COMMIT;
    END link_task;

    PROCEDURE unlink_task(
        p_workspace_id IN VARCHAR2,
        p_plan_id      IN VARCHAR2
    ) IS
    BEGIN
        DELETE FROM WORKSPACE_TASKS
        WHERE WORKSPACE_ID = p_workspace_id
          AND PLAN_ID = p_plan_id;

        COMMIT;
    END unlink_task;

    PROCEDURE cleanup_abandoned(p_days_threshold IN NUMBER DEFAULT 30) IS
    BEGIN
        DELETE FROM WORKSPACES
        WHERE STATUS = 'ABANDONED'
          AND UPDATED_AT < SYSTIMESTAMP - p_days_threshold;

        COMMIT;
    END cleanup_abandoned;

END WORKSPACE_MANAGER;
/


CREATE OR REPLACE PACKAGE SPEC_MANAGER AS
    FUNCTION create_spec(p_title VARCHAR2, p_content CLOB DEFAULT NULL, 
        p_summary VARCHAR2 DEFAULT NULL, p_category VARCHAR2 DEFAULT NULL,
        p_importance NUMBER DEFAULT 5, p_owned_by_agent VARCHAR2 DEFAULT NULL,
        p_visibility VARCHAR2 DEFAULT 'SHARED', p_workspace_id VARCHAR2 DEFAULT NULL,
        p_spec_scope VARCHAR2 DEFAULT NULL, p_complexity VARCHAR2 DEFAULT 'MEDIUM',
        p_acceptance_criteria JSON DEFAULT NULL, p_constraints JSON DEFAULT NULL,
        p_parent_spec_id VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;
    
    FUNCTION update_spec(p_entity_id VARCHAR2, p_title VARCHAR2 DEFAULT NULL,
        p_content CLOB DEFAULT NULL, p_summary VARCHAR2 DEFAULT NULL,
        p_category VARCHAR2 DEFAULT NULL, p_importance NUMBER DEFAULT NULL,
        p_visibility VARCHAR2 DEFAULT NULL, p_spec_status VARCHAR2 DEFAULT NULL,
        p_spec_scope VARCHAR2 DEFAULT NULL, p_complexity VARCHAR2 DEFAULT NULL,
        p_acceptance_criteria JSON DEFAULT NULL, p_constraints JSON DEFAULT NULL) RETURN NUMBER;
    
    FUNCTION get_spec(p_entity_id VARCHAR2) RETURN JSON;
    
    FUNCTION list_specs(p_spec_scope VARCHAR2 DEFAULT NULL, 
        p_spec_status VARCHAR2 DEFAULT NULL, p_limit NUMBER DEFAULT 50) RETURN SYS_REFCURSOR;
    
    FUNCTION link_spec_to_plan(p_spec_id VARCHAR2, p_plan_id VARCHAR2,
        p_link_type VARCHAR2, p_link_strength NUMBER DEFAULT 1.0) RETURN VARCHAR2;
    
    FUNCTION validate_spec(p_spec_id VARCHAR2, p_plan_id VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;
    
    FUNCTION derive_spec(p_parent_spec_id VARCHAR2, p_title VARCHAR2,
        p_content CLOB DEFAULT NULL, p_summary VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;
    
    PROCEDURE delete_spec(p_entity_id VARCHAR2);
END SPEC_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY SPEC_MANAGER AS

    FUNCTION create_spec(p_title VARCHAR2, p_content CLOB DEFAULT NULL, 
        p_summary VARCHAR2 DEFAULT NULL, p_category VARCHAR2 DEFAULT NULL,
        p_importance NUMBER DEFAULT 5, p_owned_by_agent VARCHAR2 DEFAULT NULL,
        p_visibility VARCHAR2 DEFAULT 'SHARED', p_workspace_id VARCHAR2 DEFAULT NULL,
        p_spec_scope VARCHAR2 DEFAULT NULL, p_complexity VARCHAR2 DEFAULT 'MEDIUM',
        p_acceptance_criteria JSON DEFAULT NULL, p_constraints JSON DEFAULT NULL,
        p_parent_spec_id VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
        v_entity_id VARCHAR2(64);
    BEGIN
        v_entity_id := RAWTOHEX(SYS_GUID());

        INSERT INTO ENTITIES (
            ENTITY_ID, ENTITY_TYPE, TITLE, CONTENT, SUMMARY, CATEGORY,
            STATUS, OWNED_BY_AGENT, SOURCE_AGENT, VISIBILITY,
            IMPORTANCE, RETRIEVAL_COUNT, WORKSPACE_ID, CREATED_AT, UPDATED_AT
        ) VALUES (
            v_entity_id, 'SPEC', p_title, p_content, p_summary, p_category,
            'DRAFT', p_owned_by_agent, p_owned_by_agent, p_visibility,
            p_importance, 0, p_workspace_id, SYSTIMESTAMP, SYSTIMESTAMP
        );

        INSERT INTO SPEC_META (
            ENTITY_ID, ENTITY_TYPE, SPEC_VERSION, SPEC_STATUS,
            ACCEPTANCE_CRITERIA, "CONSTRAINTS", SPEC_SCOPE,
            COMPLEXITY, PARENT_SPEC_ID
        ) VALUES (
            v_entity_id, 'SPEC', 1, 'DRAFT',
            p_acceptance_criteria, p_constraints, p_spec_scope,
            p_complexity, p_parent_spec_id
        );

        COMMIT;
        RETURN v_entity_id;
    END create_spec;

    FUNCTION update_spec(p_entity_id VARCHAR2, p_title VARCHAR2 DEFAULT NULL,
        p_content CLOB DEFAULT NULL, p_summary VARCHAR2 DEFAULT NULL,
        p_category VARCHAR2 DEFAULT NULL, p_importance NUMBER DEFAULT NULL,
        p_visibility VARCHAR2 DEFAULT NULL, p_spec_status VARCHAR2 DEFAULT NULL,
        p_spec_scope VARCHAR2 DEFAULT NULL, p_complexity VARCHAR2 DEFAULT NULL,
        p_acceptance_criteria JSON DEFAULT NULL, p_constraints JSON DEFAULT NULL) RETURN NUMBER IS
        v_rows NUMBER;
    BEGIN
        UPDATE ENTITIES
        SET TITLE       = COALESCE(p_title, TITLE),
            CONTENT     = COALESCE(p_content, CONTENT),
            SUMMARY     = COALESCE(p_summary, SUMMARY),
            CATEGORY    = COALESCE(p_category, CATEGORY),
            IMPORTANCE  = COALESCE(p_importance, IMPORTANCE),
            VISIBILITY  = COALESCE(p_visibility, VISIBILITY),
            UPDATED_AT  = SYSTIMESTAMP
        WHERE ENTITY_ID = p_entity_id
          AND ENTITY_TYPE = 'SPEC';

        v_rows := SQL%ROWCOUNT;

        UPDATE SPEC_META
        SET SPEC_STATUS         = COALESCE(p_spec_status, SPEC_STATUS),
            SPEC_SCOPE          = COALESCE(p_spec_scope, SPEC_SCOPE),
            COMPLEXITY          = COALESCE(p_complexity, COMPLEXITY),
            ACCEPTANCE_CRITERIA = COALESCE(p_acceptance_criteria, ACCEPTANCE_CRITERIA),
            "CONSTRAINTS"         = COALESCE(p_constraints, "CONSTRAINTS")
        WHERE ENTITY_ID = p_entity_id
          AND ENTITY_TYPE = 'SPEC';

        COMMIT;
        RETURN v_rows;
    END update_spec;

    FUNCTION get_spec(p_entity_id VARCHAR2) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON('{}') INTO v_result
        FROM ENTITIES e
        JOIN SPEC_META sm
            ON sm.ENTITY_ID = e.ENTITY_ID
           AND sm.ENTITY_TYPE = e.ENTITY_TYPE
        WHERE e.ENTITY_ID = p_entity_id
          AND e.ENTITY_TYPE = 'SPEC';

        RETURN v_result;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN NULL;
    END get_spec;

    FUNCTION list_specs(p_spec_scope VARCHAR2 DEFAULT NULL, 
        p_spec_status VARCHAR2 DEFAULT NULL, p_limit NUMBER DEFAULT 50) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT
                e.ENTITY_ID, e.TITLE, e.SUMMARY, e.CATEGORY,
                e.STATUS, e.OWNED_BY_AGENT, e.IMPORTANCE,
                sm.SPEC_VERSION, sm.SPEC_STATUS, sm.SPEC_SCOPE,
                sm.COMPLEXITY, sm.PARENT_SPEC_ID,
                e.CREATED_AT, e.UPDATED_AT
            FROM ENTITIES e
            JOIN SPEC_META sm
                ON sm.ENTITY_ID = e.ENTITY_ID
               AND sm.ENTITY_TYPE = e.ENTITY_TYPE
            WHERE e.ENTITY_TYPE = 'SPEC'
              AND (p_spec_scope IS NULL OR sm.SPEC_SCOPE = p_spec_scope)
              AND (p_spec_status IS NULL OR sm.SPEC_STATUS = p_spec_status)
            ORDER BY e.UPDATED_AT DESC
            FETCH FIRST p_limit ROWS ONLY;

        RETURN v_cur;
    END list_specs;

    FUNCTION link_spec_to_plan(p_spec_id VARCHAR2, p_plan_id VARCHAR2,
        p_link_type VARCHAR2, p_link_strength NUMBER DEFAULT 1.0) RETURN VARCHAR2 IS
        v_link_id VARCHAR2(64);
    BEGIN
        v_link_id := RAWTOHEX(SYS_GUID());

        INSERT INTO SPEC_PLAN_LINKS (
            LINK_ID, SPEC_ID, PLAN_ID, LINK_TYPE, LINK_STRENGTH
        ) VALUES (
            v_link_id, p_spec_id, p_plan_id, p_link_type, p_link_strength
        );

        COMMIT;
        RETURN v_link_id;
    END link_spec_to_plan;

    FUNCTION validate_spec(p_spec_id VARCHAR2, p_plan_id VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
        v_criteria    JSON;
        v_spec_title  VARCHAR2(512);
        v_total       NUMBER := 0;
        v_passed      NUMBER := 0;
        v_rate        NUMBER := 0;
        v_status_str  VARCHAR2(16) := 'FAIL';
    BEGIN
        SELECT sm.ACCEPTANCE_CRITERIA, e.TITLE
        INTO v_criteria, v_spec_title
        FROM SPEC_META sm
        JOIN ENTITIES e ON e.ENTITY_ID = sm.ENTITY_ID AND e.ENTITY_TYPE = sm.ENTITY_TYPE
        WHERE sm.ENTITY_ID = p_spec_id
          AND sm.ENTITY_TYPE = 'SPEC';

        SELECT COUNT(*), COUNT(CASE WHEN ts.STATUS = 'SUCCESS' THEN 1 END)
        INTO v_total, v_passed
        FROM TASK_STEPS ts
        WHERE ts.PLAN_ID = COALESCE(p_plan_id, (
            SELECT spl.PLAN_ID FROM SPEC_PLAN_LINKS spl
            WHERE spl.SPEC_ID = p_spec_id AND spl.LINK_TYPE = 'VALIDATES'
            FETCH FIRST 1 ROW ONLY
        ));

        IF v_total > 0 THEN
            v_rate := ROUND(v_passed / v_total, 4);
            IF v_passed = v_total THEN
                v_status_str := 'PASS';
            END IF;
        END IF;

        RETURN JSON('{}');
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN JSON('{}');
    END validate_spec;

    FUNCTION derive_spec(p_parent_spec_id VARCHAR2, p_title VARCHAR2,
        p_content CLOB DEFAULT NULL, p_summary VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
        v_entity_id    VARCHAR2(64);
        v_parent_scope VARCHAR2(64);
        v_new_version  NUMBER;
    BEGIN
        SELECT sm.SPEC_SCOPE, sm.SPEC_VERSION + 1
        INTO v_parent_scope, v_new_version
        FROM SPEC_META sm
        WHERE sm.ENTITY_ID = p_parent_spec_id
          AND sm.ENTITY_TYPE = 'SPEC';

        v_entity_id := RAWTOHEX(SYS_GUID());

        INSERT INTO ENTITIES (
            ENTITY_ID, ENTITY_TYPE, TITLE, CONTENT, SUMMARY, CATEGORY,
            STATUS, OWNED_BY_AGENT, SOURCE_AGENT, VISIBILITY,
            IMPORTANCE, RETRIEVAL_COUNT, CREATED_AT, UPDATED_AT
        ) SELECT
            v_entity_id, 'SPEC', p_title, COALESCE(p_content, e.CONTENT),
            COALESCE(p_summary, e.SUMMARY), e.CATEGORY,
            'DRAFT', e.OWNED_BY_AGENT, e.OWNED_BY_AGENT, e.VISIBILITY,
            e.IMPORTANCE, 0, SYSTIMESTAMP, SYSTIMESTAMP
        FROM ENTITIES e
        WHERE e.ENTITY_ID = p_parent_spec_id
          AND e.ENTITY_TYPE = 'SPEC';

        INSERT INTO SPEC_META (
            ENTITY_ID, ENTITY_TYPE, SPEC_VERSION, SPEC_STATUS,
            ACCEPTANCE_CRITERIA, "CONSTRAINTS", SPEC_SCOPE,
            COMPLEXITY, PARENT_SPEC_ID
        ) SELECT
            v_entity_id, 'SPEC', v_new_version, 'DRAFT',
            sm.ACCEPTANCE_CRITERIA, sm."CONSTRAINTS", v_parent_scope,
            sm.COMPLEXITY, p_parent_spec_id
        FROM SPEC_META sm
        WHERE sm.ENTITY_ID = p_parent_spec_id
          AND sm.ENTITY_TYPE = 'SPEC';

        COMMIT;
        RETURN v_entity_id;
    END derive_spec;

    PROCEDURE delete_spec(p_entity_id VARCHAR2) IS
    BEGIN
        DELETE FROM SPEC_PLAN_LINKS
        WHERE SPEC_ID = p_entity_id;

        DELETE FROM SPEC_META
        WHERE ENTITY_ID = p_entity_id
          AND ENTITY_TYPE = 'SPEC';

        DELETE FROM ENTITIES
        WHERE ENTITY_ID = p_entity_id
          AND ENTITY_TYPE = 'SPEC';

        COMMIT;
    END delete_spec;

END SPEC_MANAGER;
/


CREATE OR REPLACE PACKAGE COLLAB_GROUP_MANAGER AS
    FUNCTION create_group(p_group_name VARCHAR2, p_group_type VARCHAR2,
        p_description VARCHAR2 DEFAULT NULL, p_coordinator_agent_id VARCHAR2 DEFAULT NULL,
        p_sharing_policy VARCHAR2 DEFAULT 'OPEN', p_metadata JSON DEFAULT NULL) RETURN VARCHAR2;
    
    FUNCTION update_group(p_group_id VARCHAR2, p_group_name VARCHAR2 DEFAULT NULL,
        p_description VARCHAR2 DEFAULT NULL, p_coordinator_agent_id VARCHAR2 DEFAULT NULL,
        p_sharing_policy VARCHAR2 DEFAULT NULL, p_status VARCHAR2 DEFAULT NULL,
        p_metadata JSON DEFAULT NULL) RETURN NUMBER;
    
    FUNCTION get_group(p_group_id VARCHAR2) RETURN JSON;
    
    FUNCTION add_member(p_group_id VARCHAR2, p_agent_id VARCHAR2,
        p_role VARCHAR2 DEFAULT 'MEMBER') RETURN VARCHAR2;
    
    FUNCTION remove_member(p_group_id VARCHAR2, p_agent_id VARCHAR2) RETURN NUMBER;
    
    PROCEDURE archive_group(p_group_id VARCHAR2);
END COLLAB_GROUP_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY COLLAB_GROUP_MANAGER AS

    FUNCTION create_group(p_group_name VARCHAR2, p_group_type VARCHAR2,
        p_description VARCHAR2 DEFAULT NULL, p_coordinator_agent_id VARCHAR2 DEFAULT NULL,
        p_sharing_policy VARCHAR2 DEFAULT 'OPEN', p_metadata JSON DEFAULT NULL) RETURN VARCHAR2 IS
        v_group_id     VARCHAR2(64);
        v_workspace_id VARCHAR2(64);
    BEGIN
        v_group_id := RAWTOHEX(SYS_GUID());
        v_workspace_id := 'WS_CG_' || RAWTOHEX(SYS_GUID());

        INSERT INTO WORKSPACES (
            WORKSPACE_ID, OWNER_USER_ID, WORKSPACE_NAME,
            WORKSPACE_TYPE, ISOLATION_MODE, METADATA
        ) VALUES (
            v_workspace_id, p_coordinator_agent_id,
            'Collab: ' || p_group_name,
            'COLLAB_GROUP', 'SHARED', p_metadata
        );

        INSERT INTO COLLAB_GROUPS (
            GROUP_ID, GROUP_NAME, GROUP_TYPE, DESCRIPTION,
            WORKSPACE_ID, COORDINATOR_AGENT_ID, SHARING_POLICY,
            STATUS, METADATA
        ) VALUES (
            v_group_id, p_group_name, p_group_type, p_description,
            v_workspace_id, p_coordinator_agent_id, p_sharing_policy,
            'ACTIVE', p_metadata
        );

        COMMIT;
        RETURN v_group_id;
    END create_group;

    FUNCTION update_group(p_group_id VARCHAR2, p_group_name VARCHAR2 DEFAULT NULL,
        p_description VARCHAR2 DEFAULT NULL, p_coordinator_agent_id VARCHAR2 DEFAULT NULL,
        p_sharing_policy VARCHAR2 DEFAULT NULL, p_status VARCHAR2 DEFAULT NULL,
        p_metadata JSON DEFAULT NULL) RETURN NUMBER IS
        v_rows NUMBER;
    BEGIN
        UPDATE COLLAB_GROUPS
        SET GROUP_NAME           = COALESCE(p_group_name, GROUP_NAME),
            DESCRIPTION          = COALESCE(p_description, DESCRIPTION),
            COORDINATOR_AGENT_ID = COALESCE(p_coordinator_agent_id, COORDINATOR_AGENT_ID),
            SHARING_POLICY       = COALESCE(p_sharing_policy, SHARING_POLICY),
            STATUS               = COALESCE(p_status, STATUS),
            METADATA             = COALESCE(p_metadata, METADATA),
            UPDATED_AT           = SYSTIMESTAMP
        WHERE GROUP_ID = p_group_id;

        v_rows := SQL%ROWCOUNT;
        COMMIT;
        RETURN v_rows;
    END update_group;

    FUNCTION get_group(p_group_id VARCHAR2) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON('{}') INTO v_result
        FROM COLLAB_GROUPS g
        WHERE g.GROUP_ID = p_group_id;

        RETURN v_result;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN NULL;
    END get_group;

    FUNCTION add_member(p_group_id VARCHAR2, p_agent_id VARCHAR2,
        p_role VARCHAR2 DEFAULT 'MEMBER') RETURN VARCHAR2 IS
        v_member_id         VARCHAR2(64);
        v_personal_ws_id    VARCHAR2(64);
    BEGIN
        v_member_id := RAWTOHEX(SYS_GUID());

        IF p_role IN ('LEAD', 'CONTRIBUTOR') THEN
            v_personal_ws_id := 'WS_PG_' || RAWTOHEX(SYS_GUID());

            INSERT INTO WORKSPACES (
                WORKSPACE_ID, OWNER_USER_ID, WORKSPACE_NAME,
                WORKSPACE_TYPE, ISOLATION_MODE, METADATA
            ) VALUES (
                v_personal_ws_id, p_agent_id,
                'Personal: ' || p_agent_id || ' in ' || p_group_id,
                'PERSONAL_IN_GROUP', 'ISOLATED', NULL
            );
        END IF;

        INSERT INTO COLLAB_GROUP_MEMBERS (
            MEMBER_ID, GROUP_ID, AGENT_ID, ROLE,
            PERSONAL_WORKSPACE_ID, STATUS
        ) VALUES (
            v_member_id, p_group_id, p_agent_id, p_role,
            v_personal_ws_id, 'ACTIVE'
        );

        COMMIT;
        RETURN v_member_id;
    END add_member;

    FUNCTION remove_member(p_group_id VARCHAR2, p_agent_id VARCHAR2) RETURN NUMBER IS
    BEGIN
        UPDATE COLLAB_GROUP_MEMBERS
        SET STATUS = 'LEFT'
        WHERE GROUP_ID = p_group_id
          AND AGENT_ID = p_agent_id
          AND STATUS = 'ACTIVE';

        COMMIT;
        RETURN SQL%ROWCOUNT;
    END remove_member;

    PROCEDURE archive_group(p_group_id VARCHAR2) IS
    BEGIN
        UPDATE COLLAB_GROUPS
        SET STATUS    = 'ARCHIVED',
            UPDATED_AT = SYSTIMESTAMP
        WHERE GROUP_ID = p_group_id;

        UPDATE COLLAB_GROUP_MEMBERS
        SET STATUS = 'REMOVED'
        WHERE GROUP_ID = p_group_id
          AND STATUS = 'ACTIVE';

        COMMIT;
    END archive_group;

END COLLAB_GROUP_MANAGER;
/

-- ============================================================
-- EMBEDDING_MANAGER Package [NEW v2.3.2]
-- In-database embedding generation via UTL_HTTP, vector storage, similarity search
-- ============================================================

CREATE OR REPLACE PACKAGE EMBEDDING_MANAGER AS
    FUNCTION generate_embedding(p_text IN VARCHAR2) RETURN CLOB;
    FUNCTION generate_and_store(p_entity_id IN VARCHAR2, p_entity_type IN VARCHAR2, p_text IN VARCHAR2) RETURN NUMBER;
    FUNCTION cosine_similarity(p_id1 IN VARCHAR2, p_type1 IN VARCHAR2, p_id2 IN VARCHAR2, p_type2 IN VARCHAR2) RETURN NUMBER;
    PROCEDURE batch_embed_entities(p_entity_type IN VARCHAR2, p_limit IN NUMBER DEFAULT 100);
    FUNCTION get_stats RETURN VARCHAR2;
END EMBEDDING_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY EMBEDDING_MANAGER AS
    FUNCTION generate_embedding(p_text IN VARCHAR2) RETURN CLOB IS
    BEGIN
        RETURN NULL;
    END generate_embedding;

    FUNCTION generate_and_store(p_entity_id IN VARCHAR2, p_entity_type IN VARCHAR2, p_text IN VARCHAR2) RETURN NUMBER IS
    BEGIN
        -- YashanDB HTTP embedding generation is implemented by embedding_api.py.
        RETURN -1;
    END generate_and_store;

    FUNCTION cosine_similarity(p_id1 IN VARCHAR2, p_type1 IN VARCHAR2, p_id2 IN VARCHAR2, p_type2 IN VARCHAR2) RETURN NUMBER IS
        l_dist NUMBER;
    BEGIN
        SELECT VECTOR_DISTANCE(
            (SELECT EMBEDDING FROM ENTITY_EMBEDDINGS WHERE ENTITY_ID = p_id1 AND ENTITY_TYPE = p_type1),
            (SELECT EMBEDDING FROM ENTITY_EMBEDDINGS WHERE ENTITY_ID = p_id2 AND ENTITY_TYPE = p_type2),
            COSINE
        ) INTO l_dist FROM dual;
        RETURN ROUND(1 - l_dist, 4);
    EXCEPTION WHEN OTHERS THEN RETURN -1;
    END cosine_similarity;

    PROCEDURE batch_embed_entities(p_entity_type IN VARCHAR2, p_limit IN NUMBER DEFAULT 100) IS
        l_count NUMBER := 0;
    BEGIN
        MERGE INTO SYSTEM_CONFIG d
        USING (SELECT 'last_batch_embed' AS k FROM dual) s
        ON (d.CONFIG_KEY = s.k)
        WHEN MATCHED THEN UPDATE SET d.CONFIG_VALUE = TO_CHAR(l_count)
        WHEN NOT MATCHED THEN INSERT (CONFIG_KEY, CONFIG_VALUE) VALUES ('last_batch_embed', TO_CHAR(l_count));
        COMMIT;
    END batch_embed_entities;

    FUNCTION get_stats RETURN VARCHAR2 IS
        l_total NUMBER;
        l_with_vec NUMBER;
        l_models VARCHAR2(4000);
    BEGIN
        SELECT COUNT(*), COUNT(CASE WHEN EMBEDDING IS NOT NULL THEN 1 END)
        INTO l_total, l_with_vec FROM ENTITY_EMBEDDINGS;
        SELECT LISTAGG(DISTINCT EMBEDDING_MODEL, ',') WITHIN GROUP (ORDER BY EMBEDDING_MODEL)
        INTO l_models FROM ENTITY_EMBEDDINGS WHERE EMBEDDING_MODEL IS NOT NULL;
        RETURN JSON('{}');
    END get_stats;

END EMBEDDING_MANAGER;
/

PROMPT ============================================================
PROMPT LDAP_AUTH_MANAGER Package [NEW v3.3.0 ENT]
PROMPT ============================================================

CREATE OR REPLACE PACKAGE LDAP_AUTH_MANAGER AS
    FUNCTION authenticate_ldap(
        p_username IN VARCHAR2,
        p_password IN VARCHAR2
    ) RETURN JSON;
    PROCEDURE sync_ldap_users(
        p_config_id IN VARCHAR2,
        p_sync_type IN VARCHAR2 DEFAULT 'INCREMENTAL'
    );
    FUNCTION get_ldap_config(
        p_config_id IN VARCHAR2
    ) RETURN JSON;
    PROCEDURE update_ldap_config(
        p_config_id  IN VARCHAR2,
        p_server_url IN VARCHAR2 DEFAULT NULL,
        p_base_dn    IN VARCHAR2 DEFAULT NULL,
        p_bind_dn    IN VARCHAR2 DEFAULT NULL,
        p_bind_credential IN VARCHAR2 DEFAULT NULL,
        p_user_filter     IN VARCHAR2 DEFAULT NULL,
        p_group_filter    IN VARCHAR2 DEFAULT NULL,
        p_use_tls         IN VARCHAR2 DEFAULT NULL,
        p_status          IN VARCHAR2 DEFAULT NULL
    );
    FUNCTION test_ldap_connection(
        p_config_id IN VARCHAR2
    ) RETURN JSON;
    PROCEDURE log_ldap_sync(
        p_sync_type    IN VARCHAR2,
        p_status       IN VARCHAR2,
        p_users_synced IN NUMBER DEFAULT 0,
        p_groups_synced IN NUMBER DEFAULT 0,
        p_error_message IN VARCHAR2 DEFAULT NULL,
        p_duration_sec  IN NUMBER DEFAULT NULL
    );
END LDAP_AUTH_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY LDAP_AUTH_MANAGER AS

    FUNCTION authenticate_ldap(
        p_username IN VARCHAR2,
        p_password IN VARCHAR2
    ) RETURN JSON IS
        v_auth_source VARCHAR2(20);
        v_user_id VARCHAR2(64);
        v_role VARCHAR2(32);
        v_ldap_dn VARCHAR2(512);
        v_result CLOB;
    BEGIN
        SELECT AUTH_SOURCE, USER_ID, ROLE, LDAP_DN
        INTO v_auth_source, v_user_id, v_role, v_ldap_dn
        FROM SYSTEM_USERS WHERE USERNAME = p_username AND STATUS = 'ACTIVE';

        IF v_auth_source = 'LDAP' THEN
            SELECT JSON('{}') INTO v_result FROM DUAL;
        ELSE
            SELECT JSON('{}') INTO v_result FROM DUAL;
        END IF;

        RETURN JSON(v_result);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            SELECT JSON('{}') INTO v_result FROM DUAL;
            RETURN JSON(v_result);
    END authenticate_ldap;

    PROCEDURE sync_ldap_users(
        p_config_id IN VARCHAR2,
        p_sync_type IN VARCHAR2 DEFAULT 'INCREMENTAL'
    ) IS
        v_start TIMESTAMP := SYSTIMESTAMP;
    BEGIN
        UPDATE LDAP_CONFIG SET LAST_SYNC_AT = SYSTIMESTAMP
        WHERE CONFIG_ID = p_config_id;

        INSERT INTO LDAP_SYNC_LOG (LOG_ID, SYNC_TYPE, STATUS, USERS_SYNCED, GROUPS_SYNCED, SYNC_TIME, DURATION_SEC)
        VALUES ('LSL_' || RAWTOHEX(SYS_GUID()), p_sync_type, 'SUCCESS', 0, 0, SYSTIMESTAMP,
                (CAST(SYSTIMESTAMP AS DATE) - CAST(v_start AS DATE)) * 86400);

        COMMIT;
    END sync_ldap_users;

    FUNCTION get_ldap_config(
        p_config_id IN VARCHAR2
    ) RETURN JSON IS
        v_result CLOB;
    BEGIN
        SELECT JSON('{}') INTO v_result FROM LDAP_CONFIG WHERE CONFIG_ID = p_config_id;
        RETURN JSON(v_result);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            SELECT JSON('{}') INTO v_result FROM DUAL;
            RETURN JSON(v_result);
    END get_ldap_config;

    PROCEDURE update_ldap_config(
        p_config_id  IN VARCHAR2,
        p_server_url IN VARCHAR2 DEFAULT NULL,
        p_base_dn    IN VARCHAR2 DEFAULT NULL,
        p_bind_dn    IN VARCHAR2 DEFAULT NULL,
        p_bind_credential IN VARCHAR2 DEFAULT NULL,
        p_user_filter     IN VARCHAR2 DEFAULT NULL,
        p_group_filter    IN VARCHAR2 DEFAULT NULL,
        p_use_tls         IN VARCHAR2 DEFAULT NULL,
        p_status          IN VARCHAR2 DEFAULT NULL
    ) IS
    BEGIN
        UPDATE LDAP_CONFIG SET
            SERVER_URL      = COALESCE(p_server_url, SERVER_URL),
            BASE_DN         = COALESCE(p_base_dn, BASE_DN),
            BIND_DN         = COALESCE(p_bind_dn, BIND_DN),
            BIND_CREDENTIAL = COALESCE(p_bind_credential, BIND_CREDENTIAL),
            USER_FILTER     = COALESCE(p_user_filter, USER_FILTER),
            GROUP_FILTER    = COALESCE(p_group_filter, GROUP_FILTER),
            USE_TLS         = COALESCE(p_use_tls, USE_TLS),
            STATUS          = COALESCE(p_status, STATUS),
            UPDATED_AT      = SYSTIMESTAMP
        WHERE CONFIG_ID = p_config_id;
        COMMIT;
    END update_ldap_config;

    FUNCTION test_ldap_connection(
        p_config_id IN VARCHAR2
    ) RETURN JSON IS
        v_result CLOB;
    BEGIN
        SELECT JSON('{}') INTO v_result FROM LDAP_CONFIG WHERE CONFIG_ID = p_config_id;
        RETURN JSON(v_result);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            SELECT JSON('{}') INTO v_result FROM DUAL;
            RETURN JSON(v_result);
    END test_ldap_connection;

    PROCEDURE log_ldap_sync(
        p_sync_type    IN VARCHAR2,
        p_status       IN VARCHAR2,
        p_users_synced IN NUMBER DEFAULT 0,
        p_groups_synced IN NUMBER DEFAULT 0,
        p_error_message IN VARCHAR2 DEFAULT NULL,
        p_duration_sec  IN NUMBER DEFAULT NULL
    ) IS
    BEGIN
        INSERT INTO LDAP_SYNC_LOG (LOG_ID, SYNC_TYPE, STATUS, USERS_SYNCED, GROUPS_SYNCED, ERROR_MESSAGE, SYNC_TIME, DURATION_SEC)
        VALUES ('LSL_' || RAWTOHEX(SYS_GUID()), p_sync_type, p_status, p_users_synced, p_groups_synced, p_error_message, SYSTIMESTAMP, p_duration_sec);
        COMMIT;
    END log_ldap_sync;

END LDAP_AUTH_MANAGER;
/

PROMPT ============================================================
PROMPT SKILL_MANAGER Package [NEW v3.3.0]
PROMPT ============================================================

CREATE OR REPLACE PACKAGE SKILL_MANAGER AS
    FUNCTION create_skill(
        p_title       IN VARCHAR2,
        p_skill_name  IN VARCHAR2,
        p_skill_version IN VARCHAR2 DEFAULT '1.0.0',
        p_skill_type  IN VARCHAR2 DEFAULT 'CUSTOM',
        p_skill_format IN VARCHAR2 DEFAULT 'TEXT',
        p_text_content IN CLOB DEFAULT NULL,
        p_resource_uri IN VARCHAR2 DEFAULT NULL,
        p_resource_filename IN VARCHAR2 DEFAULT NULL,
        p_resource_size IN NUMBER DEFAULT NULL,
        p_resource_mime_type IN VARCHAR2 DEFAULT NULL,
        p_resource_checksum IN VARCHAR2 DEFAULT NULL,
        p_resource_server_host IN VARCHAR2 DEFAULT NULL,
        p_skill_description IN CLOB DEFAULT NULL,
        p_runtime     IN VARCHAR2 DEFAULT 'PYTHON',
        p_parameters  IN JSON DEFAULT NULL,
        p_dependencies IN JSON DEFAULT NULL,
        p_category    IN VARCHAR2 DEFAULT NULL,
        p_owned_by_agent IN VARCHAR2 DEFAULT NULL,
        p_visibility  IN VARCHAR2 DEFAULT 'SHARED',
        p_workspace_id IN VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2;
    FUNCTION get_skill(
        p_skill_id IN VARCHAR2
    ) RETURN JSON;
    PROCEDURE update_skill(
        p_skill_id    IN VARCHAR2,
        p_skill_name  IN VARCHAR2 DEFAULT NULL,
        p_skill_version IN VARCHAR2 DEFAULT NULL,
        p_text_content IN CLOB DEFAULT NULL,
        p_resource_uri IN VARCHAR2 DEFAULT NULL,
        p_resource_filename IN VARCHAR2 DEFAULT NULL,
        p_resource_size IN NUMBER DEFAULT NULL,
        p_resource_mime_type IN VARCHAR2 DEFAULT NULL,
        p_resource_checksum IN VARCHAR2 DEFAULT NULL,
        p_resource_server_host IN VARCHAR2 DEFAULT NULL,
        p_skill_description IN CLOB DEFAULT NULL,
        p_parameters  IN JSON DEFAULT NULL,
        p_dependencies IN JSON DEFAULT NULL,
        p_skill_status IN VARCHAR2 DEFAULT NULL
    );
    FUNCTION resolve_dependencies(
        p_skill_id IN VARCHAR2
    ) RETURN JSON;
    FUNCTION validate_skill(
        p_skill_id IN VARCHAR2
    ) RETURN JSON;
    PROCEDURE deprecate_skill(
        p_skill_id IN VARCHAR2
    );
END SKILL_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY SKILL_MANAGER AS

    FUNCTION create_skill(
        p_title       IN VARCHAR2,
        p_skill_name  IN VARCHAR2,
        p_skill_version IN VARCHAR2 DEFAULT '1.0.0',
        p_skill_type  IN VARCHAR2 DEFAULT 'CUSTOM',
        p_skill_format IN VARCHAR2 DEFAULT 'TEXT',
        p_text_content IN CLOB DEFAULT NULL,
        p_resource_uri IN VARCHAR2 DEFAULT NULL,
        p_resource_filename IN VARCHAR2 DEFAULT NULL,
        p_resource_size IN NUMBER DEFAULT NULL,
        p_resource_mime_type IN VARCHAR2 DEFAULT NULL,
        p_resource_checksum IN VARCHAR2 DEFAULT NULL,
        p_resource_server_host IN VARCHAR2 DEFAULT NULL,
        p_skill_description IN CLOB DEFAULT NULL,
        p_runtime     IN VARCHAR2 DEFAULT 'PYTHON',
        p_parameters  IN JSON DEFAULT NULL,
        p_dependencies IN JSON DEFAULT NULL,
        p_category    IN VARCHAR2 DEFAULT NULL,
        p_owned_by_agent IN VARCHAR2 DEFAULT NULL,
        p_visibility  IN VARCHAR2 DEFAULT 'SHARED',
        p_workspace_id IN VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2 IS
        v_entity_id VARCHAR2(64);
    BEGIN
        v_entity_id := 'ENT_' || RAWTOHEX(SYS_GUID());

        INSERT INTO ENTITIES (ENTITY_ID, ENTITY_TYPE, TITLE, CATEGORY, STATUS,
                              OWNED_BY_AGENT, VISIBILITY, WORKSPACE_ID,
                              CREATED_AT, UPDATED_AT)
        VALUES (v_entity_id, 'SKILL', p_title, p_category, 'ACTIVE',
                p_owned_by_agent, p_visibility, p_workspace_id,
                SYSTIMESTAMP, SYSTIMESTAMP);

        INSERT INTO SKILL_META (ENTITY_ID, ENTITY_TYPE, SKILL_NAME, SKILL_VERSION,
                                SKILL_TYPE, SKILL_FORMAT, TEXT_CONTENT, RESOURCE_URI,
                                RESOURCE_FILENAME, RESOURCE_SIZE, RESOURCE_MIME_TYPE,
                                RESOURCE_CHECKSUM, RESOURCE_SERVER_HOST, SKILL_DESCRIPTION,
                                RUNTIME, PARAMETERS, DEPENDENCIES, SKILL_STATUS)
        VALUES (v_entity_id, 'SKILL', p_skill_name, p_skill_version,
                p_skill_type, p_skill_format, p_text_content, p_resource_uri,
                p_resource_filename, p_resource_size, p_resource_mime_type,
                p_resource_checksum, p_resource_server_host, p_skill_description,
                p_runtime, p_parameters, p_dependencies, 'ACTIVE');

        COMMIT;
        RETURN v_entity_id;
    END create_skill;

    FUNCTION get_skill(
        p_skill_id IN VARCHAR2
    ) RETURN JSON IS
        v_result CLOB;
    BEGIN
        SELECT JSON('{}') INTO v_result
        FROM ENTITIES e JOIN SKILL_META s ON e.ENTITY_ID = s.ENTITY_ID AND e.ENTITY_TYPE = s.ENTITY_TYPE
        WHERE e.ENTITY_ID = p_skill_id AND e.ENTITY_TYPE = 'SKILL';

        RETURN JSON(v_result);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN JSON(JSON('{}'));
    END get_skill;

    PROCEDURE update_skill(
        p_skill_id    IN VARCHAR2,
        p_skill_name  IN VARCHAR2 DEFAULT NULL,
        p_skill_version IN VARCHAR2 DEFAULT NULL,
        p_text_content IN CLOB DEFAULT NULL,
        p_resource_uri IN VARCHAR2 DEFAULT NULL,
        p_resource_filename IN VARCHAR2 DEFAULT NULL,
        p_resource_size IN NUMBER DEFAULT NULL,
        p_resource_mime_type IN VARCHAR2 DEFAULT NULL,
        p_resource_checksum IN VARCHAR2 DEFAULT NULL,
        p_resource_server_host IN VARCHAR2 DEFAULT NULL,
        p_skill_description IN CLOB DEFAULT NULL,
        p_parameters  IN JSON DEFAULT NULL,
        p_dependencies IN JSON DEFAULT NULL,
        p_skill_status IN VARCHAR2 DEFAULT NULL
    ) IS
    BEGIN
        UPDATE SKILL_META SET
            SKILL_NAME        = COALESCE(p_skill_name, SKILL_NAME),
            SKILL_VERSION     = COALESCE(p_skill_version, SKILL_VERSION),
            TEXT_CONTENT      = COALESCE(p_text_content, TEXT_CONTENT),
            RESOURCE_URI      = COALESCE(p_resource_uri, RESOURCE_URI),
            RESOURCE_FILENAME = COALESCE(p_resource_filename, RESOURCE_FILENAME),
            RESOURCE_SIZE     = COALESCE(p_resource_size, RESOURCE_SIZE),
            RESOURCE_MIME_TYPE = COALESCE(p_resource_mime_type, RESOURCE_MIME_TYPE),
            RESOURCE_CHECKSUM = COALESCE(p_resource_checksum, RESOURCE_CHECKSUM),
            RESOURCE_SERVER_HOST = COALESCE(p_resource_server_host, RESOURCE_SERVER_HOST),
            SKILL_DESCRIPTION = COALESCE(p_skill_description, SKILL_DESCRIPTION),
            PARAMETERS        = COALESCE(p_parameters, PARAMETERS),
            DEPENDENCIES      = COALESCE(p_dependencies, DEPENDENCIES),
            SKILL_STATUS      = COALESCE(p_skill_status, SKILL_STATUS)
        WHERE ENTITY_ID = p_skill_id AND ENTITY_TYPE = 'SKILL';

        UPDATE ENTITIES SET UPDATED_AT = SYSTIMESTAMP
        WHERE ENTITY_ID = p_skill_id AND ENTITY_TYPE = 'SKILL';

        COMMIT;
    END update_skill;

    FUNCTION resolve_dependencies(
        p_skill_id IN VARCHAR2
    ) RETURN JSON IS
        v_deps JSON;
        v_empty JSON;
    BEGIN
        SELECT JSON('[]') INTO v_empty FROM DUAL;

        SELECT DEPENDENCIES INTO v_deps
        FROM SKILL_META
        WHERE ENTITY_ID = p_skill_id AND ENTITY_TYPE = 'SKILL';

        IF v_deps IS NULL THEN
            RETURN v_empty;
        END IF;

        RETURN v_deps;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN v_empty;
    END resolve_dependencies;

    FUNCTION validate_skill(
        p_skill_id IN VARCHAR2
    ) RETURN JSON IS
        v_count NUMBER;
        v_has_name NUMBER;
        v_errors JSON;
        v_empty_arr JSON;
        v_not_found_arr JSON;
    BEGIN
        SELECT JSON('[]') INTO v_empty_arr FROM DUAL;
        SELECT JSON('["Skill not found"]') INTO v_not_found_arr FROM DUAL;

        SELECT COUNT(*) INTO v_count FROM SKILL_META
        WHERE ENTITY_ID = p_skill_id AND ENTITY_TYPE = 'SKILL';

        IF v_count = 0 THEN
            RETURN JSON(JSON('{}'));
        END IF;

        SELECT COUNT(*) INTO v_has_name FROM SKILL_META
        WHERE ENTITY_ID = p_skill_id AND SKILL_NAME IS NOT NULL;

        IF v_has_name = 0 THEN
            SELECT JSON('["SKILL_NAME is required"]') INTO v_errors FROM DUAL;
            RETURN JSON(JSON('{}'));
        ELSE
            RETURN JSON(JSON('{}'));
        END IF;
    END validate_skill;

    PROCEDURE deprecate_skill(
        p_skill_id IN VARCHAR2
    ) IS
    BEGIN
        UPDATE SKILL_META SET SKILL_STATUS = 'DEPRECATED'
        WHERE ENTITY_ID = p_skill_id AND ENTITY_TYPE = 'SKILL';

        UPDATE ENTITIES SET STATUS = 'ARCHIVED', UPDATED_AT = SYSTIMESTAMP
        WHERE ENTITY_ID = p_skill_id AND ENTITY_TYPE = 'SKILL';

        COMMIT;
    END deprecate_skill;

END SKILL_MANAGER;
/

PROMPT ============================================================
PROMPT Package: CONTEXT_AUDIT_MANAGER [NEW v3.3.0 ENT]
PROMPT ============================================================

CREATE OR REPLACE PACKAGE CONTEXT_AUDIT_MANAGER AS

    FUNCTION log_audit_event(
        p_entity_id        IN VARCHAR2,
        p_entity_type      IN VARCHAR2,
        p_audit_type       IN VARCHAR2,
        p_rule_id          IN VARCHAR2 DEFAULT NULL,
        p_similarity_score IN NUMBER   DEFAULT NULL,
        p_threshold_score  IN NUMBER   DEFAULT NULL,
        p_violation_detail IN VARCHAR2 DEFAULT NULL,
        p_agent_id         IN VARCHAR2 DEFAULT NULL,
        p_session_id       IN VARCHAR2 DEFAULT NULL,
        p_workspace_id     IN VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2;

    FUNCTION get_audit_events(
        p_resolution_status IN VARCHAR2 DEFAULT NULL,
        p_audit_type        IN VARCHAR2 DEFAULT NULL,
        p_limit             IN NUMBER   DEFAULT 100
    ) RETURN SYS_REFCURSOR;

    FUNCTION get_audit_event(
        p_audit_id IN VARCHAR2
    ) RETURN SYS_REFCURSOR;

    PROCEDURE resolve_audit_event(
        p_audit_id         IN VARCHAR2,
        p_resolution_status IN VARCHAR2,
        p_resolved_by      IN VARCHAR2
    );

    FUNCTION evaluate_rules(
        p_entity_id    IN VARCHAR2,
        p_entity_type  IN VARCHAR2,
        p_agent_id     IN VARCHAR2 DEFAULT NULL,
        p_workspace_id IN VARCHAR2 DEFAULT NULL
    ) RETURN NUMBER;

    PROCEDURE purge_audit_log(
        p_retention_days IN NUMBER DEFAULT 90
    );

    FUNCTION get_audit_stats(
        p_since IN TIMESTAMP DEFAULT NULL
    ) RETURN SYS_REFCURSOR;

END CONTEXT_AUDIT_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY CONTEXT_AUDIT_MANAGER AS

    FUNCTION log_audit_event(
        p_entity_id        IN VARCHAR2,
        p_entity_type      IN VARCHAR2,
        p_audit_type       IN VARCHAR2,
        p_rule_id          IN VARCHAR2 DEFAULT NULL,
        p_similarity_score IN NUMBER   DEFAULT NULL,
        p_threshold_score  IN NUMBER   DEFAULT NULL,
        p_violation_detail IN VARCHAR2 DEFAULT NULL,
        p_agent_id         IN VARCHAR2 DEFAULT NULL,
        p_session_id       IN VARCHAR2 DEFAULT NULL,
        p_workspace_id     IN VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2 IS
        v_audit_id VARCHAR2(64);
    BEGIN
        v_audit_id := SYS_GUID();

        INSERT INTO CONTEXT_AUDIT_LOG (
            AUDIT_ID, ENTITY_ID, ENTITY_TYPE, AUDIT_TYPE,
            RULE_ID, SIMILARITY_SCORE, THRESHOLD_SCORE, VIOLATION_DETAIL,
            AGENT_ID, SESSION_ID, WORKSPACE_ID
        ) VALUES (
            v_audit_id, p_entity_id, p_entity_type, p_audit_type,
            p_rule_id, p_similarity_score, p_threshold_score, p_violation_detail,
            p_agent_id, p_session_id, p_workspace_id
        );

        COMMIT;
        RETURN v_audit_id;
    END log_audit_event;

    FUNCTION get_audit_events(
        p_resolution_status IN VARCHAR2 DEFAULT NULL,
        p_audit_type        IN VARCHAR2 DEFAULT NULL,
        p_limit             IN NUMBER   DEFAULT 100
    ) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
        v_sql VARCHAR2(4000);
    BEGIN
        v_sql := 'SELECT AUDIT_ID, ENTITY_ID, ENTITY_TYPE, AUDIT_TYPE, RULE_ID, ' ||
                 'SIMILARITY_SCORE, THRESHOLD_SCORE, VIOLATION_DETAIL, ' ||
                 'AGENT_ID, SESSION_ID, WORKSPACE_ID, RESOLUTION_STATUS, ' ||
                 'RESOLVED_BY, RESOLVED_AT, CREATED_AT ' ||
                 'FROM CONTEXT_AUDIT_LOG WHERE 1=1';

        IF p_resolution_status IS NOT NULL THEN
            v_sql := v_sql || ' AND RESOLUTION_STATUS = :rs';
        END IF;
        IF p_audit_type IS NOT NULL THEN
            v_sql := v_sql || ' AND AUDIT_TYPE = :at';
        END IF;

        v_sql := v_sql || ' ORDER BY CREATED_AT DESC';

        IF p_limit IS NOT NULL THEN
            v_sql := v_sql || ' FETCH FIRST ' || p_limit || ' ROWS ONLY';
        END IF;

        IF p_resolution_status IS NOT NULL AND p_audit_type IS NOT NULL THEN
            OPEN v_cur FOR v_sql USING p_resolution_status, p_audit_type;
        ELSIF p_resolution_status IS NOT NULL THEN
            OPEN v_cur FOR v_sql USING p_resolution_status;
        ELSIF p_audit_type IS NOT NULL THEN
            OPEN v_cur FOR v_sql USING p_audit_type;
        ELSE
            OPEN v_cur FOR v_sql;
        END IF;

        RETURN v_cur;
    END get_audit_events;

    FUNCTION get_audit_event(
        p_audit_id IN VARCHAR2
    ) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT AUDIT_ID, ENTITY_ID, ENTITY_TYPE, AUDIT_TYPE, RULE_ID,
                   SIMILARITY_SCORE, THRESHOLD_SCORE, VIOLATION_DETAIL,
                   AGENT_ID, SESSION_ID, WORKSPACE_ID, RESOLUTION_STATUS,
                   RESOLVED_BY, RESOLVED_AT, CREATED_AT
            FROM CONTEXT_AUDIT_LOG
            WHERE AUDIT_ID = p_audit_id;
        RETURN v_cur;
    END get_audit_event;

    PROCEDURE resolve_audit_event(
        p_audit_id          IN VARCHAR2,
        p_resolution_status IN VARCHAR2,
        p_resolved_by       IN VARCHAR2
    ) IS
    BEGIN
        UPDATE CONTEXT_AUDIT_LOG
        SET RESOLUTION_STATUS = p_resolution_status,
            RESOLVED_BY       = p_resolved_by,
            RESOLVED_AT       = SYSTIMESTAMP
        WHERE AUDIT_ID = p_audit_id;

        COMMIT;
    END resolve_audit_event;

    FUNCTION evaluate_rules(
        p_entity_id    IN VARCHAR2,
        p_entity_type  IN VARCHAR2,
        p_agent_id     IN VARCHAR2 DEFAULT NULL,
        p_workspace_id IN VARCHAR2 DEFAULT NULL
    ) RETURN NUMBER IS
        v_violation_count NUMBER := 0;
        v_entity_workspace VARCHAR2(64);
        v_entity_visibility VARCHAR2(20);
        v_entity_category VARCHAR2(64);
        v_agent_workspace VARCHAR2(64);
        v_dummy VARCHAR2(64);
    BEGIN
        SELECT WORKSPACE_ID, VISIBILITY, CATEGORY
        INTO v_entity_workspace, v_entity_visibility, v_entity_category
        FROM ENTITIES
        WHERE ENTITY_ID = p_entity_id AND ENTITY_TYPE = p_entity_type;

        IF p_agent_id IS NOT NULL THEN
            v_agent_workspace := p_workspace_id;
        END IF;

        FOR r IN (
            SELECT RULE_ID, RULE_NAME, RULE_TYPE, CONDITION_EXPR, SEVERITY
            FROM CONTEXT_AUDIT_RULES
            WHERE IS_ENABLED = 'Y'
        ) LOOP
            DECLARE
                v_triggered BOOLEAN := FALSE;
            BEGIN
                IF r.RULE_TYPE = 'CROSS_BOUNDARY' AND p_agent_id IS NOT NULL THEN
                    IF v_entity_workspace IS NOT NULL
                       AND v_agent_workspace IS NOT NULL
                       AND v_entity_workspace != v_agent_workspace
                       AND v_entity_visibility = 'PRIVATE' THEN
                        v_triggered := TRUE;
                    END IF;
                END IF;

                IF v_triggered THEN
                    v_violation_count := v_violation_count + 1;
                    v_dummy := log_audit_event(
                        p_entity_id        => p_entity_id,
                        p_entity_type      => p_entity_type,
                        p_audit_type       => 'RULE_VIOLATION',
                        p_rule_id          => r.RULE_ID,
                        p_violation_detail => r.RULE_NAME || ': ' || r.CONDITION_EXPR,
                        p_agent_id         => p_agent_id,
                        p_workspace_id     => p_workspace_id
                    );
                END IF;
            END;
        END LOOP;

        RETURN v_violation_count;
    END evaluate_rules;

    PROCEDURE purge_audit_log(
        p_retention_days IN NUMBER DEFAULT 90
    ) IS
    BEGIN
        DELETE FROM CONTEXT_AUDIT_LOG
        WHERE CREATED_AT < SYSTIMESTAMP - p_retention_days;
        COMMIT;
    END purge_audit_log;

    FUNCTION get_audit_stats(
        p_since IN TIMESTAMP DEFAULT NULL
    ) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
        v_since TIMESTAMP;
    BEGIN
        v_since := NVL(p_since, SYSTIMESTAMP - 7);

        OPEN v_cur FOR
            SELECT AUDIT_TYPE,
                   RESOLUTION_STATUS,
                   COUNT(*) AS EVENT_COUNT,
                   AVG(SIMILARITY_SCORE) AS AVG_SIMILARITY,
                   MAX(CREATED_AT) AS LAST_EVENT
            FROM CONTEXT_AUDIT_LOG
            WHERE CREATED_AT >= v_since
            GROUP BY AUDIT_TYPE, RESOLUTION_STATUS
            ORDER BY AUDIT_TYPE, RESOLUTION_STATUS;
        RETURN v_cur;
    END get_audit_stats;

END CONTEXT_AUDIT_MANAGER;
/

PROMPT ============================================================

PROMPT ============================================================
PROMPT Package: DB_CRYPTO [NEW v3.3.0]
PROMPT ============================================================

BEGIN
    BEGIN
        INSERT INTO SYSTEM_CONFIG (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION)
        VALUES (
            'db_crypto_master_key',
            SUBSTR(RAWTOHEX(SYS_GUID()), 1, 16),
            'AES-128 master key for DB-side encryption (generated during deployment)'
        );
    EXCEPTION
        WHEN DUP_VAL_ON_INDEX THEN NULL;
    END;
    BEGIN
        INSERT INTO SYSTEM_CONFIG (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION)
        VALUES (
            'db_crypto_key_salt',
            RAWTOHEX(SYS_GUID()),
            'Reserved salt for DB_CRYPTO key rotation'
        );
    EXCEPTION
        WHEN DUP_VAL_ON_INDEX THEN NULL;
    END;
    COMMIT;
END;
/

CREATE OR REPLACE PACKAGE DB_CRYPTO AS
    FUNCTION encrypt(p_plaintext VARCHAR2) RETURN VARCHAR2;
    FUNCTION decrypt(p_ciphertext VARCHAR2) RETURN VARCHAR2;
    PROCEDURE rotate_key;
END DB_CRYPTO;
/

CREATE OR REPLACE PACKAGE BODY DB_CRYPTO AS
    CK_KEY VARCHAR2(128) := 'db_crypto_master_key';
    CK_SALT VARCHAR2(128) := 'db_crypto_key_salt';

    FUNCTION get_db_key RETURN VARCHAR2 IS
        v_key_hex VARCHAR2(4000);
    BEGIN
        SELECT CONFIG_VALUE INTO v_key_hex FROM SYSTEM_CONFIG WHERE CONFIG_KEY = CK_KEY;
        RETURN SUBSTR(v_key_hex, 1, 16);
    END get_db_key;

    FUNCTION encrypt(p_plaintext VARCHAR2) RETURN VARCHAR2 IS
        v_key_hex VARCHAR2(32);
    BEGIN
        v_key_hex := get_db_key;
        RETURN RAWTOHEX(UTL_RAW.CAST_TO_RAW(ENCRYPT_AES128(p_plaintext, v_key_hex)));
    END encrypt;

    FUNCTION decrypt(p_ciphertext VARCHAR2) RETURN VARCHAR2 IS
        v_key_hex VARCHAR2(32);
    BEGIN
        v_key_hex := get_db_key;
        RETURN DECRYPT_AES128(
            UTL_RAW.CAST_TO_VARCHAR2(HEXTORAW(p_ciphertext)),
            v_key_hex
        );
    END decrypt;

    PROCEDURE rotate_key IS
        v_new_key_hex VARCHAR2(32);
        v_new_salt_hex VARCHAR2(32);
    BEGIN
        v_new_key_hex := SUBSTR(RAWTOHEX(SYS_GUID()), 1, 16);
        v_new_salt_hex := RAWTOHEX(SYS_GUID());
        UPDATE SYSTEM_CONFIG SET CONFIG_VALUE = v_new_key_hex, UPDATED_AT = SYSTIMESTAMP WHERE CONFIG_KEY = CK_KEY;
        UPDATE SYSTEM_CONFIG SET CONFIG_VALUE = v_new_salt_hex, UPDATED_AT = SYSTIMESTAMP WHERE CONFIG_KEY = CK_SALT;
        COMMIT;
    END rotate_key;
END DB_CRYPTO;
/

PROMPT ============================================================
PROMPT 16. TRACE_MANAGER Package [NEW v3.7.5]
PROMPT ============================================================

CREATE OR REPLACE PACKAGE TRACE_MANAGER AS
    FUNCTION init_trace(p_source VARCHAR2 DEFAULT 'API') RETURN VARCHAR2;
    FUNCTION get_trace_tree(p_trace_id VARCHAR2) RETURN SYS_REFCURSOR;
    FUNCTION get_trace_summary(
        p_agent_id VARCHAR2 DEFAULT NULL,
        p_since    TIMESTAMP DEFAULT NULL,
        p_limit    NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR;
    FUNCTION get_span_count(p_trace_id VARCHAR2) RETURN NUMBER;
END TRACE_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY TRACE_MANAGER AS
    FUNCTION init_trace(p_source VARCHAR2 DEFAULT 'API') RETURN VARCHAR2 IS
        v_id VARCHAR2(64) := RAWTOHEX(SYS_GUID());
    BEGIN
        RETURN v_id;
    END init_trace;

    FUNCTION get_trace_tree(p_trace_id VARCHAR2) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT 'SESSION' AS span_type, SESSION_ID AS span_id, AGENT_ID, START_TIME, END_TIME, TRACE_ID
            FROM AGENT_SESSION WHERE TRACE_ID = p_trace_id
            UNION ALL
            SELECT 'PLAN', PLAN_ID, AGENT_ID, CREATED_AT, COMPLETED_AT, TRACE_ID
            FROM TASK_PLANS WHERE TRACE_ID = p_trace_id
            UNION ALL
            SELECT 'RUN', RUN_ID, AGENT_ID, STARTED_AT, COMPLETED_AT, TRACE_ID
            FROM LOOP_RUNS WHERE TRACE_ID = p_trace_id
            UNION ALL
            SELECT 'TOOL', CALL_ID, NULL, CREATED_AT, NULL, TRACE_ID
            FROM TASK_TOOL_CALLS WHERE TRACE_ID = p_trace_id
            ORDER BY 4;
        RETURN v_cur;
    END get_trace_tree;

    FUNCTION get_trace_summary(
        p_agent_id VARCHAR2 DEFAULT NULL,
        p_since    TIMESTAMP DEFAULT NULL,
        p_limit    NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT s.TRACE_ID, s.AGENT_ID, s.SESSION_ID,
                   s.START_TIME, s.END_TIME, s.IS_ACTIVE,
                   (SELECT COUNT(*) FROM TASK_PLANS p WHERE p.TRACE_ID = s.TRACE_ID) AS plan_count,
                   (SELECT COUNT(*) FROM LOOP_RUNS r WHERE r.TRACE_ID = s.TRACE_ID) AS run_count,
                   (SELECT COUNT(*) FROM TASK_TOOL_CALLS t WHERE t.TRACE_ID = s.TRACE_ID) AS tool_count
            FROM AGENT_SESSION s
            WHERE s.TRACE_ID IS NOT NULL
              AND (p_agent_id IS NULL OR s.AGENT_ID = p_agent_id)
              AND (p_since IS NULL OR s.START_TIME >= p_since)
            ORDER BY s.START_TIME DESC
            FETCH FIRST p_limit ROWS ONLY;
        RETURN v_cur;
    END get_trace_summary;

    FUNCTION get_span_count(p_trace_id VARCHAR2) RETURN NUMBER IS
        v_total NUMBER := 0;
    BEGIN
        SELECT COUNT(*) INTO v_total FROM AGENT_SESSION WHERE TRACE_ID = p_trace_id;
        SELECT COUNT(*) + v_total INTO v_total FROM TASK_PLANS WHERE TRACE_ID = p_trace_id;
        SELECT COUNT(*) + v_total INTO v_total FROM LOOP_RUNS WHERE TRACE_ID = p_trace_id;
        SELECT COUNT(*) + v_total INTO v_total FROM TASK_TOOL_CALLS WHERE TRACE_ID = p_trace_id;
        RETURN v_total;
    END get_span_count;
END TRACE_MANAGER;
/

PROMPT ============================================================
PROMPT 17. MONITOR_MANAGER Package [NEW v3.7.5]
PROMPT ============================================================

CREATE OR REPLACE PACKAGE MONITOR_MANAGER AS
    FUNCTION get_stalled_agents(p_idle_minutes NUMBER DEFAULT 10) RETURN SYS_REFCURSOR;
    FUNCTION get_active_plan_counts RETURN SYS_REFCURSOR;
    FUNCTION get_token_usage_trend(p_days NUMBER DEFAULT 7) RETURN SYS_REFCURSOR;
    FUNCTION get_loop_health RETURN SYS_REFCURSOR;
END MONITOR_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY MONITOR_MANAGER AS
    FUNCTION get_stalled_agents(p_idle_minutes NUMBER DEFAULT 10) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT a.AGENT_ID, a.AGENT_NAME, a.STATUS, a.LAST_SEEN_AT, a.LAST_ACTIVE_AT,
                   ROUND(EXTRACT(DAY FROM (SYSTIMESTAMP - NVL(a.LAST_ACTIVE_AT, a.LAST_SEEN_AT)))*24*60 +
                         EXTRACT(HOUR FROM (SYSTIMESTAMP - NVL(a.LAST_ACTIVE_AT, a.LAST_SEEN_AT)))*60 +
                         EXTRACT(MINUTE FROM (SYSTIMESTAMP - NVL(a.LAST_ACTIVE_AT, a.LAST_SEEN_AT))), 1) AS idle_minutes
            FROM AGENT_REGISTRY a
            WHERE a.STATUS IN ('ACTIVE', 'POOL')
              AND NVL(a.LAST_ACTIVE_AT, a.LAST_SEEN_AT) < SYSTIMESTAMP - NUMTODSINTERVAL(p_idle_minutes, 'MINUTE')
            ORDER BY idle_minutes DESC;
        RETURN v_cur;
    END get_stalled_agents;

    FUNCTION get_active_plan_counts RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT AGENT_ID, COUNT(*) AS plan_count, STATUS
            FROM TASK_PLANS
            WHERE STATUS IN ('PENDING', 'RUNNING', 'BLOCKED')
            GROUP BY AGENT_ID, STATUS
            ORDER BY AGENT_ID;
        RETURN v_cur;
    END get_active_plan_counts;

    FUNCTION get_token_usage_trend(p_days NUMBER DEFAULT 7) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT TRUNC(STARTED_AT) AS day, COUNT(*) AS run_count, SUM(TOTAL_TOKENS) AS total_tokens
            FROM LOOP_RUNS
            WHERE STARTED_AT >= SYSTIMESTAMP - NUMTODSINTERVAL(p_days, 'DAY')
            GROUP BY TRUNC(STARTED_AT)
            ORDER BY day;
        RETURN v_cur;
    END get_token_usage_trend;

    FUNCTION get_loop_health RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT STATUS, COUNT(*) AS cnt
            FROM LOOP_RUNS
            WHERE STARTED_AT >= SYSTIMESTAMP - NUMTODSINTERVAL(1, 'DAY')
            GROUP BY STATUS
            ORDER BY cnt DESC;
        RETURN v_cur;
    END get_loop_health;
END MONITOR_MANAGER;
/


PROMPT AI Agent Infra v5.0.1 API Deployment Complete
PROMPT ============================================================


PROMPT ============================================================
PROMPT Package: BRANCH_MANAGER [NEW v3.3.0]
PROMPT ============================================================

CREATE OR REPLACE PACKAGE BRANCH_MANAGER AS

    FUNCTION fork_branch(
        p_workspace_id    VARCHAR2,
        p_fork_context_id VARCHAR2,
        p_branch_name     VARCHAR2,
        p_branch_type     VARCHAR2,
        p_agent_id        VARCHAR2,
        p_source_agent_id VARCHAR2 DEFAULT NULL,
        p_purpose         VARCHAR2 DEFAULT NULL,
        p_fork_session_id VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2;

    FUNCTION get_branch(p_branch_id VARCHAR2) RETURN JSON;

    FUNCTION get_branch_tree(p_workspace_id VARCHAR2) RETURN SYS_REFCURSOR;

    FUNCTION get_branch_chain(
        p_branch_id VARCHAR2,
        p_limit     NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR;

    FUNCTION diff_branches(
        p_branch_a_id VARCHAR2,
        p_branch_b_id VARCHAR2
    ) RETURN SYS_REFCURSOR;

    FUNCTION detect_conflicts(
        p_source_branch_id VARCHAR2,
        p_target_branch_id VARCHAR2
    ) RETURN JSON;

    PROCEDURE merge_branch(
        p_source_branch_id VARCHAR2,
        p_target_branch_id VARCHAR2,
        p_merge_type       VARCHAR2 DEFAULT 'MERGE',
        p_merged_by_agent  VARCHAR2,
        p_conflict_resolutions JSON DEFAULT NULL
    );

    PROCEDURE abandon_branch(
        p_branch_id VARCHAR2,
        p_reason    VARCHAR2 DEFAULT NULL
    );

    PROCEDURE pause_branch(p_branch_id VARCHAR2);

    PROCEDURE resume_branch(p_branch_id VARCHAR2);

    FUNCTION get_agent_branches(
        p_agent_id VARCHAR2,
        p_status   VARCHAR2 DEFAULT 'ACTIVE'
    ) RETURN SYS_REFCURSOR;

    FUNCTION get_branch_stats(p_branch_id VARCHAR2) RETURN JSON;

    FUNCTION mark_as_lesson(
        p_branch_id       VARCHAR2,
        p_context_id      VARCHAR2,
        p_lesson_type     VARCHAR2,
        p_lesson_summary  VARCHAR2,
        p_lesson_detail   VARCHAR2 DEFAULT NULL,
        p_agent_id        VARCHAR2
    ) RETURN VARCHAR2;

    FUNCTION extract_lessons(
        p_branch_id    VARCHAR2,
        p_auto_confirm VARCHAR2 DEFAULT 'N'
    ) RETURN JSON;

    PROCEDURE cleanup_abandoned_branches(
        p_days_threshold NUMBER DEFAULT 90
    );

    FUNCTION fork_branch_for_spec(
        p_workspace_id    VARCHAR2,
        p_spec_id         VARCHAR2,
        p_branch_name     VARCHAR2,
        p_agent_id        VARCHAR2,
        p_source_agent_id VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2;

    FUNCTION validate_branch_for_spec(
        p_branch_id VARCHAR2,
        p_spec_id   VARCHAR2
    ) RETURN JSON;

    FUNCTION fork_parallel_branches(
        p_workspace_id      VARCHAR2,
        p_agent_ids         VARCHAR2,
        p_branch_name_prefix VARCHAR2 DEFAULT 'parallel',
        p_purpose           VARCHAR2 DEFAULT NULL
    ) RETURN SYS_REFCURSOR;

END BRANCH_MANAGER;
/
CREATE OR REPLACE PACKAGE BODY BRANCH_MANAGER AS

    FUNCTION fork_branch(
        p_workspace_id    VARCHAR2,
        p_fork_context_id VARCHAR2,
        p_branch_name     VARCHAR2,
        p_branch_type     VARCHAR2,
        p_agent_id        VARCHAR2,
        p_source_agent_id VARCHAR2 DEFAULT NULL,
        p_purpose         VARCHAR2 DEFAULT NULL,
        p_fork_session_id VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2 IS
        v_branch_id VARCHAR2(64);
        v_parent_branch_id VARCHAR2(64);
    BEGIN
        v_branch_id := 'BR_' || RAWTOHEX(SYS_GUID());

        SELECT MAX(b.BRANCH_ID) INTO v_parent_branch_id
        FROM CONTEXT_BRANCHES b
        WHERE b.WORKSPACE_ID = p_workspace_id
          AND b.BRANCH_STATUS = 'ACTIVE'
          AND b.AGENT_ID = p_agent_id;

        INSERT INTO CONTEXT_BRANCHES (
            BRANCH_ID, WORKSPACE_ID, PARENT_BRANCH_ID, FORK_CONTEXT_ID,
            FORK_SESSION_ID, BRANCH_NAME, BRANCH_TYPE, BRANCH_STATUS,
            AGENT_ID, SOURCE_AGENT_ID, BRANCH_PURPOSE
        ) VALUES (
            v_branch_id, p_workspace_id, v_parent_branch_id, p_fork_context_id,
            p_fork_session_id, p_branch_name, p_branch_type, 'ACTIVE',
            p_agent_id, p_source_agent_id, p_purpose
        );

        INSERT INTO WORKSPACE_CONTEXT (
            CONTEXT_ID, WORKSPACE_ID, AGENT_ID, SESSION_ID,
            CONTEXT_TYPE, CONTEXT_DATA, PARENT_CONTEXT_ID, BRANCH_ID
        ) VALUES (
            'CTX_' || RAWTOHEX(SYS_GUID()),
            p_workspace_id, p_agent_id, p_fork_session_id,
            'BRANCH_POINT',
            JSON('{}'),
            p_fork_context_id,
            v_branch_id
        );

        COMMIT;
        RETURN v_branch_id;
    END fork_branch;

    FUNCTION get_branch(p_branch_id VARCHAR2) RETURN JSON IS
        v_clob CLOB;
    BEGIN
        SELECT JSON('{}') INTO v_clob FROM CONTEXT_BRANCHES WHERE BRANCH_ID = p_branch_id;
        RETURN JSON(v_clob);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN RETURN NULL;
    END get_branch;

    FUNCTION get_branch_tree(p_workspace_id VARCHAR2) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT BRANCH_ID, PARENT_BRANCH_ID, BRANCH_NAME, BRANCH_TYPE,
                   BRANCH_STATUS, AGENT_ID, FORK_CONTEXT_ID,
                   TO_CHAR(CREATED_AT, 'YYYY-MM-DD HH24:MI:SS') AS CREATED_AT,
                   TO_CHAR(CLOSED_AT, 'YYYY-MM-DD HH24:MI:SS') AS CLOSED_AT
            FROM CONTEXT_BRANCHES
            WHERE WORKSPACE_ID = p_workspace_id
            ORDER BY CREATED_AT ASC;
        RETURN v_cur;
    END get_branch_tree;

    FUNCTION get_branch_chain(
        p_branch_id VARCHAR2,
        p_limit     NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT CONTEXT_ID, WORKSPACE_ID, AGENT_ID, SESSION_ID,
                   CONTEXT_TYPE, CONTEXT_DATA, PARENT_CONTEXT_ID, BRANCH_ID,
                   TO_CHAR(CREATED_AT, 'YYYY-MM-DD HH24:MI:SS') AS CREATED_AT
            FROM WORKSPACE_CONTEXT
            WHERE BRANCH_ID = p_branch_id
            ORDER BY CREATED_AT ASC
            FETCH FIRST p_limit ROWS ONLY;
        RETURN v_cur;
    END get_branch_chain;

    FUNCTION diff_branches(
        p_branch_a_id VARCHAR2,
        p_branch_b_id VARCHAR2
    ) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT 'ONLY_IN_A' AS diff_side, wc.CONTEXT_ID, wc.CONTEXT_TYPE,
                   wc.CONTEXT_DATA, wc.AGENT_ID,
                   TO_CHAR(wc.CREATED_AT, 'YYYY-MM-DD HH24:MI:SS') AS CREATED_AT
            FROM WORKSPACE_CONTEXT wc
            WHERE wc.BRANCH_ID = p_branch_a_id
              AND wc.CONTEXT_TYPE != 'BRANCH_POINT'
            UNION ALL
            SELECT 'ONLY_IN_B' AS diff_side, wc.CONTEXT_ID, wc.CONTEXT_TYPE,
                   wc.CONTEXT_DATA, wc.AGENT_ID,
                   TO_CHAR(wc.CREATED_AT, 'YYYY-MM-DD HH24:MI:SS') AS CREATED_AT
            FROM WORKSPACE_CONTEXT wc
            WHERE wc.BRANCH_ID = p_branch_b_id
              AND wc.CONTEXT_TYPE != 'BRANCH_POINT'
            ORDER BY diff_side, CREATED_AT ASC;
        RETURN v_cur;
    END diff_branches;

    FUNCTION detect_conflicts(
        p_source_branch_id VARCHAR2,
        p_target_branch_id VARCHAR2
    ) RETURN JSON IS
        v_clob CLOB;
    BEGIN
        SELECT '{"total_conflicts":0,"conflicts":[]}' INTO v_clob FROM DUAL;
        RETURN JSON(v_clob);
    END detect_conflicts;

    PROCEDURE merge_branch(
        p_source_branch_id VARCHAR2,
        p_target_branch_id VARCHAR2,
        p_merge_type       VARCHAR2 DEFAULT 'MERGE',
        p_merged_by_agent  VARCHAR2,
        p_conflict_resolutions JSON DEFAULT NULL
    ) IS
        v_merge_id VARCHAR2(64);
        v_conflicts JSON;
        v_result VARCHAR2(32) := 'SUCCESS';
        v_source_ws VARCHAR2(64);
        v_conflict_count NUMBER;
    BEGIN
        v_merge_id := 'MRG_' || RAWTOHEX(SYS_GUID());
        v_conflicts := detect_conflicts(p_source_branch_id, p_target_branch_id);

        SELECT jt.cv INTO v_conflict_count
        FROM JSON_TABLE(v_conflicts, '$' COLUMNS(cv NUMBER PATH '$.total_conflicts')) jt;

        IF v_conflict_count > 0 AND p_conflict_resolutions IS NULL THEN
            v_result := 'CONFLICT';
        ELSIF v_conflict_count > 0 THEN
            v_result := 'PARTIAL';
        END IF;

        SELECT WORKSPACE_ID INTO v_source_ws
        FROM CONTEXT_BRANCHES WHERE BRANCH_ID = p_source_branch_id;

        INSERT INTO BRANCH_MERGE_LOG (
            MERGE_ID, SOURCE_BRANCH_ID, TARGET_BRANCH_ID, MERGE_TYPE,
            MERGED_BY_AGENT, CONFLICTS, MERGE_RESULT
        ) VALUES (
            v_merge_id, p_source_branch_id, p_target_branch_id, p_merge_type,
            p_merged_by_agent, v_conflicts, v_result
        );

        UPDATE CONTEXT_BRANCHES
        SET BRANCH_STATUS = 'MERGED', CLOSED_AT = SYSTIMESTAMP
        WHERE BRANCH_ID = p_source_branch_id;

        INSERT INTO WORKSPACE_CONTEXT (
            CONTEXT_ID, WORKSPACE_ID, AGENT_ID, CONTEXT_TYPE, CONTEXT_DATA, BRANCH_ID
        ) VALUES (
            'CTX_' || RAWTOHEX(SYS_GUID()),
            v_source_ws, p_merged_by_agent, 'SUMMARY',
            JSON('{}'),
            p_target_branch_id
        );

        COMMIT;
    END merge_branch;

    PROCEDURE abandon_branch(
        p_branch_id VARCHAR2,
        p_reason    VARCHAR2 DEFAULT NULL
    ) IS
    BEGIN
        UPDATE CONTEXT_BRANCHES
        SET BRANCH_STATUS = 'ABANDONED',
            CLOSED_AT = SYSTIMESTAMP,
            BRANCH_PURPOSE = COALESCE(BRANCH_PURPOSE || ' | ABANDONED: ' || p_reason, 'ABANDONED: ' || p_reason)
        WHERE BRANCH_ID = p_branch_id;

        UPDATE AGENT_SESSION
        SET IS_ACTIVE = 'N', END_TIME = SYSTIMESTAMP
        WHERE BRANCH_ID = p_branch_id AND IS_ACTIVE = 'Y';

        COMMIT;
    END abandon_branch;

    PROCEDURE pause_branch(p_branch_id VARCHAR2) IS
    BEGIN
        UPDATE CONTEXT_BRANCHES
        SET BRANCH_STATUS = 'PAUSED'
        WHERE BRANCH_ID = p_branch_id;

        UPDATE AGENT_SESSION
        SET IS_ACTIVE = 'N', END_TIME = SYSTIMESTAMP
        WHERE BRANCH_ID = p_branch_id AND IS_ACTIVE = 'Y';

        COMMIT;
    END pause_branch;

    PROCEDURE resume_branch(p_branch_id VARCHAR2) IS
        v_agent_id VARCHAR2(64);
        v_workspace_id VARCHAR2(64);
    BEGIN
        UPDATE CONTEXT_BRANCHES
        SET BRANCH_STATUS = 'ACTIVE'
        WHERE BRANCH_ID = p_branch_id;

        SELECT AGENT_ID, WORKSPACE_ID INTO v_agent_id, v_workspace_id
        FROM CONTEXT_BRANCHES WHERE BRANCH_ID = p_branch_id;

        INSERT INTO AGENT_SESSION (SESSION_ID, AGENT_ID, WORKSPACE_ID, BRANCH_ID, IS_ACTIVE, START_TIME)
        VALUES ('SES_' || RAWTOHEX(SYS_GUID()), v_agent_id, v_workspace_id, p_branch_id, 'Y', SYSTIMESTAMP);

        COMMIT;
    END resume_branch;

    FUNCTION get_agent_branches(
        p_agent_id VARCHAR2,
        p_status   VARCHAR2 DEFAULT 'ACTIVE'
    ) RETURN SYS_REFCURSOR IS
        v_cur SYS_REFCURSOR;
    BEGIN
        OPEN v_cur FOR
            SELECT BRANCH_ID, WORKSPACE_ID, PARENT_BRANCH_ID, BRANCH_NAME,
                   BRANCH_TYPE, BRANCH_STATUS, FORK_CONTEXT_ID,
                   TO_CHAR(CREATED_AT, 'YYYY-MM-DD HH24:MI:SS') AS CREATED_AT,
                   TO_CHAR(CLOSED_AT, 'YYYY-MM-DD HH24:MI:SS') AS CLOSED_AT
            FROM CONTEXT_BRANCHES
            WHERE AGENT_ID = p_agent_id
              AND (p_status IS NULL OR BRANCH_STATUS = p_status)
            ORDER BY CREATED_AT DESC;
        RETURN v_cur;
    END get_agent_branches;

    FUNCTION get_branch_stats(p_branch_id VARCHAR2) RETURN JSON IS
        v_ctx_count NUMBER;
        v_session_count NUMBER;
        v_duration_min NUMBER;
        v_clob CLOB;
    BEGIN
        SELECT COUNT(*) INTO v_ctx_count
        FROM WORKSPACE_CONTEXT WHERE BRANCH_ID = p_branch_id;

        SELECT COUNT(*) INTO v_session_count
        FROM AGENT_SESSION WHERE BRANCH_ID = p_branch_id;

        SELECT NVL(ROUND(EXTRACT(DAY FROM(SYSTIMESTAMP - MIN(START_TIME)))*24*60 + EXTRACT(HOUR FROM(SYSTIMESTAMP - MIN(START_TIME)))*60 + EXTRACT(MINUTE FROM(SYSTIMESTAMP - MIN(START_TIME))), 0), 0) INTO v_duration_min
        FROM AGENT_SESSION WHERE BRANCH_ID = p_branch_id;

        SELECT JSON('{}') INTO v_clob FROM DUAL;
        RETURN JSON(v_clob);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            SELECT JSON('{}') INTO v_clob FROM DUAL;
            RETURN JSON(v_clob);
    END get_branch_stats;

    FUNCTION mark_as_lesson(
        p_branch_id       VARCHAR2,
        p_context_id      VARCHAR2,
        p_lesson_type     VARCHAR2,
        p_lesson_summary  VARCHAR2,
        p_lesson_detail   VARCHAR2 DEFAULT NULL,
        p_agent_id        VARCHAR2
    ) RETURN VARCHAR2 IS
        v_entity_id VARCHAR2(64);
        v_workspace_id VARCHAR2(64);
    BEGIN
        v_entity_id := 'ENT_' || RAWTOHEX(SYS_GUID());

        SELECT WORKSPACE_ID INTO v_workspace_id
        FROM CONTEXT_BRANCHES WHERE BRANCH_ID = p_branch_id;

        INSERT INTO ENTITIES (ENTITY_ID, ENTITY_TYPE, TITLE, CONTENT, CATEGORY, STATUS,
                              OWNED_BY_AGENT, VISIBILITY, WORKSPACE_ID)
        VALUES (v_entity_id, 'KNOWLEDGE',
                '[' || p_lesson_type || '] ' || p_lesson_summary,
                p_lesson_detail, 'LESSON_LEARNED', 'ACTIVE',
                p_agent_id, 'SHARED', v_workspace_id);

        INSERT INTO KNOWLEDGE_META (ENTITY_ID, ENTITY_TYPE, DOMAIN, TOPIC, DIFFICULTY)
        VALUES (v_entity_id, 'KNOWLEDGE', 'BRANCH_EXPERIENCE',
                SUBSTR(p_lesson_summary, 1, 50), 'INTERMEDIATE');

        IF p_context_id IS NOT NULL THEN
            INSERT INTO ENTITY_EDGES (EDGE_ID, SOURCE_ID, SOURCE_TYPE, TARGET_ID, EDGE_TYPE, STRENGTH)
            VALUES ('EDG_' || RAWTOHEX(SYS_GUID()), v_entity_id, 'KNOWLEDGE',
                    p_context_id, 'DERIVED_FROM', 1.0);
        END IF;

        COMMIT;
        RETURN v_entity_id;
    END mark_as_lesson;

    FUNCTION extract_lessons(
        p_branch_id    VARCHAR2,
        p_auto_confirm VARCHAR2 DEFAULT 'N'
    ) RETURN JSON IS
        v_clob CLOB;
        v_error_count NUMBER := 0;
        v_summary_count NUMBER := 0;
        v_workspace_id VARCHAR2(64);
        v_agent_id VARCHAR2(64);
        CURSOR c_errors IS
            SELECT CONTEXT_ID, CONTEXT_DATA
            FROM WORKSPACE_CONTEXT
            WHERE BRANCH_ID = p_branch_id AND CONTEXT_TYPE = 'ERROR_STATE';
        CURSOR c_summary IS
            SELECT CONTEXT_ID, CONTEXT_DATA
            FROM WORKSPACE_CONTEXT
            WHERE BRANCH_ID = p_branch_id AND CONTEXT_TYPE = 'SUMMARY'
            ORDER BY CREATED_AT DESC FETCH FIRST 1 ROWS ONLY;
    BEGIN
        SELECT WORKSPACE_ID, AGENT_ID INTO v_workspace_id, v_agent_id
        FROM CONTEXT_BRANCHES WHERE BRANCH_ID = p_branch_id;

        FOR r IN c_errors LOOP
            v_error_count := v_error_count + 1;
            IF p_auto_confirm = 'Y' THEN
                v_clob := NULL;
                SELECT mark_as_lesson(
                    p_branch_id, r.CONTEXT_ID, 'MISTAKE',
                    'Error in abandoned branch', NULL, v_agent_id
                ) INTO v_clob FROM DUAL;
            END IF;
        END LOOP;

        FOR r IN c_summary LOOP
            v_summary_count := v_summary_count + 1;
            IF p_auto_confirm = 'Y' THEN
                v_clob := NULL;
                SELECT mark_as_lesson(
                    p_branch_id, r.CONTEXT_ID, 'INSIGHT',
                    'Branch summary', NULL, v_agent_id
                ) INTO v_clob FROM DUAL;
            END IF;
        END LOOP;

        SELECT JSON('{}') INTO v_clob FROM DUAL;
        COMMIT;
        RETURN JSON(v_clob);
    END extract_lessons;

    PROCEDURE cleanup_abandoned_branches(
        p_days_threshold NUMBER DEFAULT 90
    ) IS
    BEGIN
        DELETE FROM BRANCH_MERGE_LOG
        WHERE SOURCE_BRANCH_ID IN (
            SELECT BRANCH_ID FROM CONTEXT_BRANCHES
            WHERE BRANCH_STATUS = 'ABANDONED'
              AND CLOSED_AT < SYSTIMESTAMP - NUMTODSINTERVAL(p_days_threshold, 'DAY')
        );

        DELETE FROM WORKSPACE_CONTEXT
        WHERE BRANCH_ID IN (
            SELECT BRANCH_ID FROM CONTEXT_BRANCHES
            WHERE BRANCH_STATUS = 'ABANDONED'
              AND CLOSED_AT < SYSTIMESTAMP - NUMTODSINTERVAL(p_days_threshold, 'DAY')
        );

        DELETE FROM AGENT_SESSION
        WHERE BRANCH_ID IN (
            SELECT BRANCH_ID FROM CONTEXT_BRANCHES
            WHERE BRANCH_STATUS = 'ABANDONED'
              AND CLOSED_AT < SYSTIMESTAMP - NUMTODSINTERVAL(p_days_threshold, 'DAY')
        );

        DELETE FROM CONTEXT_BRANCHES
        WHERE BRANCH_STATUS = 'ABANDONED'
          AND CLOSED_AT < SYSTIMESTAMP - NUMTODSINTERVAL(p_days_threshold, 'DAY');

        COMMIT;
    END cleanup_abandoned_branches;


    FUNCTION fork_branch_for_spec(
        p_workspace_id    VARCHAR2,
        p_spec_id         VARCHAR2,
        p_branch_name     VARCHAR2,
        p_agent_id        VARCHAR2,
        p_source_agent_id VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2 IS
        v_branch_id VARCHAR2(64);
        v_purpose VARCHAR2(1000);
    BEGIN
        SELECT '[' || ENTITY_TYPE || '] ' || TITLE INTO v_purpose
        FROM ENTITIES WHERE ENTITY_ID = p_spec_id AND ENTITY_TYPE = 'SPEC';
        v_purpose := 'Implement spec: ' || v_purpose;
        EXCEPTION WHEN NO_DATA_FOUND THEN
            v_purpose := 'Implement spec: ' || p_spec_id;

        v_branch_id := fork_branch(
            p_workspace_id    => p_workspace_id,
            p_fork_context_id => NULL,
            p_branch_name     => p_branch_name,
            p_branch_type     => 'EXPLORATION',
            p_agent_id        => p_agent_id,
            p_source_agent_id => p_source_agent_id,
            p_purpose         => v_purpose
        );
        RETURN v_branch_id;
    END fork_branch_for_spec;

    FUNCTION validate_branch_for_spec(
        p_branch_id VARCHAR2,
        p_spec_id   VARCHAR2
    ) RETURN JSON IS
        v_ac CLOB;
        v_ctx_count NUMBER;
        v_result JSON;
    BEGIN
        SELECT ACCEPTANCE_CRITERIA INTO v_ac
        FROM SPEC_META WHERE ENTITY_ID = p_spec_id;

        SELECT COUNT(*) INTO v_ctx_count
        FROM WORKSPACE_CONTEXT
        WHERE BRANCH_ID = p_branch_id;

        SELECT JSON('{}') INTO v_result FROM DUAL;
        RETURN v_result;
    END validate_branch_for_spec;


    FUNCTION fork_parallel_branches(
        p_workspace_id      VARCHAR2,
        p_agent_ids         VARCHAR2,
        p_branch_name_prefix VARCHAR2 DEFAULT 'parallel',
        p_purpose           VARCHAR2 DEFAULT NULL
    ) RETURN SYS_REFCURSOR IS
        v_cursor SYS_REFCURSOR;
    BEGIN
        OPEN v_cursor FOR
            SELECT b.BRANCH_ID, b.AGENT_ID, b.BRANCH_NAME, b.BRANCH_STATUS
            FROM CONTEXT_BRANCHES b
            WHERE b.WORKSPACE_ID = p_workspace_id
              AND b.BRANCH_TYPE = 'PARALLEL'
              AND b.BRANCH_STATUS = 'ACTIVE'
            ORDER BY b.CREATED_AT;
        RETURN v_cursor;
    END fork_parallel_branches;

END BRANCH_MANAGER;
/


PROMPT ============================================================
PROMPT 15. LOOP_MANAGER Package [NEW v3.7.5]
PROMPT ============================================================

CREATE OR REPLACE PACKAGE LOOP_MANAGER AS

    FUNCTION create_loop(
        p_title               VARCHAR2,
        p_summary             VARCHAR2 DEFAULT NULL,
        p_goal_definition     JSON,
        p_stop_conditions     JSON,
        p_evaluation_config   JSON,
        p_trigger_config      JSON DEFAULT NULL,
        p_harness_template_id VARCHAR2 DEFAULT NULL,
        p_workspace_id        VARCHAR2 DEFAULT NULL,
        p_branch_id           VARCHAR2 DEFAULT NULL,
        p_owned_by_agent      VARCHAR2 DEFAULT NULL,
        p_visibility          VARCHAR2 DEFAULT 'PRIVATE'
    ) RETURN VARCHAR2;

    FUNCTION get_loop(p_loop_id VARCHAR2) RETURN JSON;

    FUNCTION update_loop(
        p_loop_id            VARCHAR2,
        p_title              VARCHAR2 DEFAULT NULL,
        p_summary            VARCHAR2 DEFAULT NULL,
        p_goal_definition    JSON DEFAULT NULL,
        p_stop_conditions    JSON DEFAULT NULL,
        p_evaluation_config  JSON DEFAULT NULL,
        p_trigger_config     JSON DEFAULT NULL,
        p_visibility         VARCHAR2 DEFAULT NULL
    ) RETURN NUMBER;

    PROCEDURE delete_loop(p_loop_id VARCHAR2);

    FUNCTION list_loops(
        p_status   VARCHAR2 DEFAULT NULL,
        p_agent_id VARCHAR2 DEFAULT NULL,
        p_limit    NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR;

    FUNCTION start_run(
        p_loop_id        VARCHAR2,
        p_agent_id       VARCHAR2,
        p_trigger_type   VARCHAR2 DEFAULT 'MANUAL',
        p_trigger_source VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2;

    FUNCTION get_run(p_run_id VARCHAR2) RETURN JSON;

    FUNCTION list_runs(
        p_loop_id VARCHAR2 DEFAULT NULL,
        p_status  VARCHAR2 DEFAULT NULL,
        p_limit   NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR;

    PROCEDURE pause_run(p_run_id VARCHAR2);
    PROCEDURE resume_run(p_run_id VARCHAR2);
    PROCEDURE stop_run(p_run_id VARCHAR2, p_reason VARCHAR2 DEFAULT NULL);

    FUNCTION record_iteration(
        p_run_id            VARCHAR2,
        p_plan_data         JSON DEFAULT NULL,
        p_actions           JSON DEFAULT NULL,
        p_observations      JSON DEFAULT NULL,
        p_evaluation_result JSON DEFAULT NULL,
        p_evaluation_passed VARCHAR2 DEFAULT 'N',
        p_adjustment        JSON DEFAULT NULL,
        p_token_usage       NUMBER DEFAULT 0
    ) RETURN VARCHAR2;

    FUNCTION get_iteration(p_iteration_id VARCHAR2) RETURN JSON;

    FUNCTION list_iterations(
        p_run_id VARCHAR2,
        p_limit  NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR;

    FUNCTION add_hook(
        p_loop_id     VARCHAR2,
        p_hook_event  VARCHAR2,
        p_hook_type   VARCHAR2,
        p_hook_config JSON DEFAULT NULL,
        p_priority    NUMBER DEFAULT 5
    ) RETURN VARCHAR2;

    PROCEDURE remove_hook(p_hook_id VARCHAR2);

    FUNCTION list_hooks(p_loop_id VARCHAR2) RETURN SYS_REFCURSOR;

    FUNCTION get_loop_stats(p_loop_id VARCHAR2) RETURN JSON;

    FUNCTION check_stop_conditions(p_run_id VARCHAR2) RETURN VARCHAR2;

    PROCEDURE cleanup_old_runs(p_days_threshold NUMBER DEFAULT 90);

    PROCEDURE process_scheduled_triggers;

    PROCEDURE check_stuck_runs;

    PROCEDURE log_loop_audit(
        p_loop_id       VARCHAR2,
        p_run_id        VARCHAR2,
        p_action_type   VARCHAR2,
        p_action_by     VARCHAR2 DEFAULT NULL,
        p_action_detail JSON DEFAULT NULL
    );
END LOOP_MANAGER;
/


CREATE OR REPLACE PACKAGE BODY LOOP_MANAGER AS

FUNCTION create_loop(
        p_title               VARCHAR2,
        p_summary             VARCHAR2 DEFAULT NULL,
        p_goal_definition     JSON,
        p_stop_conditions     JSON,
        p_evaluation_config   JSON,
        p_trigger_config      JSON DEFAULT NULL,
        p_harness_template_id VARCHAR2 DEFAULT NULL,
        p_workspace_id        VARCHAR2 DEFAULT NULL,
        p_branch_id           VARCHAR2 DEFAULT NULL,
        p_owned_by_agent      VARCHAR2 DEFAULT NULL,
        p_visibility          VARCHAR2 DEFAULT 'PRIVATE'
    ) RETURN VARCHAR2 IS
        v_entity_id VARCHAR2(64);
    BEGIN
        v_entity_id := RAWTOHEX(SYS_GUID());
        INSERT INTO ENTITIES (
            ENTITY_ID, ENTITY_TYPE, TITLE, SUMMARY, STATUS,
            OWNED_BY_AGENT, SOURCE_AGENT, VISIBILITY,
            IMPORTANCE, RETRIEVAL_COUNT, WORKSPACE_ID
        ) VALUES (
            v_entity_id, 'LOOP_DEFINITION', p_title, p_summary, 'ACTIVE',
            p_owned_by_agent, p_owned_by_agent, p_visibility,
            5, 0, p_workspace_id
        );
        INSERT INTO LOOP_META (
            ENTITY_ID, ENTITY_TYPE, LOOP_VERSION,
            GOAL_DEFINITION, STOP_CONDITIONS, EVALUATION_CONFIG,
            TRIGGER_CONFIG, HARNESS_TEMPLATE_ID, WORKSPACE_ID, BRANCH_ID
        ) VALUES (
            v_entity_id, 'LOOP_DEFINITION', '1.0',
            p_goal_definition, p_stop_conditions, p_evaluation_config,
            p_trigger_config, p_harness_template_id, p_workspace_id, p_branch_id
        );
        RETURN v_entity_id;
    END create_loop;

FUNCTION get_loop(p_loop_id VARCHAR2) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON('{}') INTO v_result
        FROM ENTITIES e JOIN LOOP_META m ON e.ENTITY_ID = m.ENTITY_ID
        WHERE e.ENTITY_ID = p_loop_id AND e.ENTITY_TYPE = 'LOOP_DEFINITION';
        RETURN v_result;
    EXCEPTION WHEN NO_DATA_FOUND THEN RETURN NULL;
    END get_loop;

FUNCTION update_loop(
        p_loop_id VARCHAR2, p_title VARCHAR2 DEFAULT NULL, p_summary VARCHAR2 DEFAULT NULL,
        p_goal_definition JSON DEFAULT NULL, p_stop_conditions JSON DEFAULT NULL,
        p_evaluation_config JSON DEFAULT NULL, p_trigger_config JSON DEFAULT NULL,
        p_visibility VARCHAR2 DEFAULT NULL
    ) RETURN NUMBER IS
        v_count NUMBER := 0;
    BEGIN
        IF p_title IS NOT NULL THEN
            UPDATE ENTITIES SET TITLE = p_title, UPDATED_AT = SYSTIMESTAMP
            WHERE ENTITY_ID = p_loop_id AND ENTITY_TYPE = 'LOOP_DEFINITION';
            v_count := v_count + SQL%ROWCOUNT;
        END IF;
        IF p_summary IS NOT NULL THEN
            UPDATE ENTITIES SET SUMMARY = p_summary, UPDATED_AT = SYSTIMESTAMP
            WHERE ENTITY_ID = p_loop_id AND ENTITY_TYPE = 'LOOP_DEFINITION';
        END IF;
        IF p_visibility IS NOT NULL THEN
            UPDATE ENTITIES SET VISIBILITY = p_visibility, UPDATED_AT = SYSTIMESTAMP
            WHERE ENTITY_ID = p_loop_id AND ENTITY_TYPE = 'LOOP_DEFINITION';
        END IF;
        UPDATE LOOP_META SET
            GOAL_DEFINITION = NVL(p_goal_definition, GOAL_DEFINITION),
            STOP_CONDITIONS = NVL(p_stop_conditions, STOP_CONDITIONS),
            EVALUATION_CONFIG = NVL(p_evaluation_config, EVALUATION_CONFIG),
            TRIGGER_CONFIG = NVL(p_trigger_config, TRIGGER_CONFIG)
        WHERE ENTITY_ID = p_loop_id;
        v_count := v_count + SQL%ROWCOUNT;
        RETURN v_count;
    END update_loop;

PROCEDURE delete_loop(p_loop_id VARCHAR2) IS
    BEGIN
        DELETE FROM LOOP_HOOKS WHERE LOOP_ID = p_loop_id;
        DELETE FROM LOOP_META WHERE ENTITY_ID = p_loop_id;
        DELETE FROM ENTITIES WHERE ENTITY_ID = p_loop_id AND ENTITY_TYPE = 'LOOP_DEFINITION';
    END delete_loop;

FUNCTION list_loops(
        p_status VARCHAR2 DEFAULT NULL, p_agent_id VARCHAR2 DEFAULT NULL, p_limit NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR IS
        v_cursor SYS_REFCURSOR;
    BEGIN
        OPEN v_cursor FOR
            SELECT e.ENTITY_ID AS loop_id, e.TITLE, e.SUMMARY, e.STATUS,
                   e.VISIBILITY, e.OWNED_BY_AGENT, e.WORKSPACE_ID,
                   m.LOOP_VERSION, e.CREATED_AT, e.UPDATED_AT
            FROM ENTITIES e JOIN LOOP_META m ON e.ENTITY_ID = m.ENTITY_ID
            WHERE e.ENTITY_TYPE = 'LOOP_DEFINITION'
              AND (p_status IS NULL OR e.STATUS = p_status)
              AND (p_agent_id IS NULL OR e.OWNED_BY_AGENT = p_agent_id)
            ORDER BY e.CREATED_AT DESC FETCH FIRST p_limit ROWS ONLY;
        RETURN v_cursor;
    END list_loops;

FUNCTION start_run(
        p_loop_id        VARCHAR2,
        p_agent_id       VARCHAR2,
        p_trigger_type   VARCHAR2 DEFAULT 'MANUAL',
        p_trigger_source VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2 IS
        v_run_id VARCHAR2(64);
    BEGIN
        v_run_id := RAWTOHEX(SYS_GUID());
        INSERT INTO LOOP_RUNS (
            RUN_ID, LOOP_ID, AGENT_ID, TRIGGER_TYPE, TRIGGER_SOURCE,
            STATUS, ITERATION_COUNT, TOTAL_TOKENS, STARTED_AT
        ) VALUES (
            v_run_id, p_loop_id, p_agent_id, p_trigger_type, p_trigger_source,
            'RUNNING', 0, 0, SYSTIMESTAMP
        );
        RETURN v_run_id;
    END start_run;

FUNCTION get_run(p_run_id VARCHAR2) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON('{}') INTO v_result
        FROM LOOP_RUNS r WHERE r.RUN_ID = p_run_id;
        RETURN v_result;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN RETURN NULL;
    END get_run;

FUNCTION list_runs(
        p_loop_id VARCHAR2 DEFAULT NULL,
        p_status  VARCHAR2 DEFAULT NULL,
        p_limit   NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR IS
        v_cursor SYS_REFCURSOR;
    BEGIN
        OPEN v_cursor FOR
            SELECT RUN_ID, LOOP_ID, AGENT_ID, TRIGGER_TYPE, TRIGGER_SOURCE,
                   STATUS, ITERATION_COUNT, TOTAL_TOKENS, FINAL_RESULT,
                   STARTED_AT, COMPLETED_AT
            FROM LOOP_RUNS
            WHERE (p_loop_id IS NULL OR LOOP_ID = p_loop_id)
              AND (p_status IS NULL OR STATUS = p_status)
            ORDER BY STARTED_AT DESC
            FETCH FIRST p_limit ROWS ONLY;
        RETURN v_cursor;
    END list_runs;

PROCEDURE pause_run(p_run_id VARCHAR2) IS
    BEGIN
        UPDATE LOOP_RUNS SET STATUS = 'PAUSED'
        WHERE RUN_ID = p_run_id AND STATUS = 'RUNNING';
    END pause_run;

PROCEDURE resume_run(p_run_id VARCHAR2) IS
    BEGIN
        UPDATE LOOP_RUNS SET STATUS = 'RUNNING'
        WHERE RUN_ID = p_run_id AND STATUS = 'PAUSED';
    END resume_run;

PROCEDURE stop_run(p_run_id VARCHAR2, p_reason VARCHAR2 DEFAULT NULL) IS
    BEGIN
        UPDATE LOOP_RUNS SET
            STATUS = 'STOPPED', FINAL_RESULT = p_reason, COMPLETED_AT = SYSTIMESTAMP
        WHERE RUN_ID = p_run_id AND STATUS IN ('RUNNING','PAUSED');
    END stop_run;

FUNCTION record_iteration(
        p_run_id            VARCHAR2,
        p_plan_data         JSON DEFAULT NULL,
        p_actions           JSON DEFAULT NULL,
        p_observations      JSON DEFAULT NULL,
        p_evaluation_result JSON DEFAULT NULL,
        p_evaluation_passed VARCHAR2 DEFAULT 'N',
        p_adjustment        JSON DEFAULT NULL,
        p_token_usage       NUMBER DEFAULT 0
    ) RETURN VARCHAR2 IS
        v_iter_id    VARCHAR2(64);
        v_iter_count NUMBER;
    BEGIN
        SELECT ITERATION_COUNT INTO v_iter_count
        FROM LOOP_RUNS WHERE RUN_ID = p_run_id;
        v_iter_id := RAWTOHEX(SYS_GUID());
        INSERT INTO LOOP_ITERATIONS (
            ITERATION_ID, RUN_ID, ITERATION_ORDER,
            PLAN_DATA, ACTIONS, OBSERVATIONS,
            EVALUATION_RESULT, EVALUATION_PASSED, ADJUSTMENT,
            TOKEN_USAGE, STARTED_AT, COMPLETED_AT
        ) VALUES (
            v_iter_id, p_run_id, v_iter_count + 1,
            p_plan_data, p_actions, p_observations,
            p_evaluation_result, p_evaluation_passed, p_adjustment,
            p_token_usage, SYSTIMESTAMP, SYSTIMESTAMP
        );
        UPDATE LOOP_RUNS SET
            ITERATION_COUNT = v_iter_count + 1,
            TOTAL_TOKENS = TOTAL_TOKENS + p_token_usage
        WHERE RUN_ID = p_run_id;
        IF p_evaluation_passed = 'Y' THEN
            UPDATE LOOP_RUNS SET
                STATUS = 'COMPLETED', COMPLETED_AT = SYSTIMESTAMP,
                FINAL_RESULT = 'Goal achieved at iteration ' || (v_iter_count + 1)
            WHERE RUN_ID = p_run_id;
        END IF;
        RETURN v_iter_id;
    END record_iteration;

FUNCTION get_iteration(p_iteration_id VARCHAR2) RETURN JSON IS
        v_result JSON;
    BEGIN
        SELECT JSON('{}') INTO v_result
        FROM LOOP_ITERATIONS i WHERE i.ITERATION_ID = p_iteration_id;
        RETURN v_result;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN RETURN NULL;
    END get_iteration;

FUNCTION list_iterations(
        p_run_id VARCHAR2,
        p_limit  NUMBER DEFAULT 50
    ) RETURN SYS_REFCURSOR IS
        v_cursor SYS_REFCURSOR;
    BEGIN
        OPEN v_cursor FOR
            SELECT ITERATION_ID, RUN_ID, ITERATION_ORDER,
                   EVALUATION_PASSED, TOKEN_USAGE,
                   STARTED_AT, COMPLETED_AT
            FROM LOOP_ITERATIONS
            WHERE RUN_ID = p_run_id
            ORDER BY ITERATION_ORDER ASC
            FETCH FIRST p_limit ROWS ONLY;
        RETURN v_cursor;
    END list_iterations;

FUNCTION add_hook(
        p_loop_id     VARCHAR2,
        p_hook_event  VARCHAR2,
        p_hook_type   VARCHAR2,
        p_hook_config JSON DEFAULT NULL,
        p_priority    NUMBER DEFAULT 5
    ) RETURN VARCHAR2 IS
        v_hook_id VARCHAR2(64);
    BEGIN
        v_hook_id := RAWTOHEX(SYS_GUID());
        INSERT INTO LOOP_HOOKS (
            HOOK_ID, LOOP_ID, HOOK_EVENT, HOOK_TYPE,
            HOOK_CONFIG, PRIORITY, ENABLED, CREATED_AT
        ) VALUES (
            v_hook_id, p_loop_id, p_hook_event, p_hook_type,
            p_hook_config, p_priority, 'Y', SYSTIMESTAMP
        );
        RETURN v_hook_id;
    END add_hook;

PROCEDURE remove_hook(p_hook_id VARCHAR2) IS
    BEGIN
        DELETE FROM LOOP_HOOKS WHERE HOOK_ID = p_hook_id;
    END remove_hook;

FUNCTION list_hooks(p_loop_id VARCHAR2) RETURN SYS_REFCURSOR IS
        v_cursor SYS_REFCURSOR;
    BEGIN
        OPEN v_cursor FOR
            SELECT HOOK_ID, LOOP_ID, HOOK_EVENT, HOOK_TYPE,
                   HOOK_CONFIG, PRIORITY, ENABLED, CREATED_AT
            FROM LOOP_HOOKS
            WHERE LOOP_ID = p_loop_id
            ORDER BY PRIORITY ASC, CREATED_AT ASC;
        RETURN v_cursor;
    END list_hooks;

FUNCTION get_loop_stats(p_loop_id VARCHAR2) RETURN JSON IS
        v_result       JSON;
        v_total_runs   NUMBER;
        v_completed    NUMBER;
        v_failed       NUMBER;
        v_running      NUMBER;
        v_total_iters  NUMBER;
        v_total_tokens NUMBER;
    BEGIN
        SELECT COUNT(*) INTO v_total_runs FROM LOOP_RUNS WHERE LOOP_ID = p_loop_id;
        SELECT COUNT(*) INTO v_completed FROM LOOP_RUNS WHERE LOOP_ID = p_loop_id AND STATUS = 'COMPLETED';
        SELECT COUNT(*) INTO v_failed FROM LOOP_RUNS WHERE LOOP_ID = p_loop_id AND STATUS IN ('FAILED','STOPPED','TIMEOUT');
        SELECT COUNT(*) INTO v_running FROM LOOP_RUNS WHERE LOOP_ID = p_loop_id AND STATUS IN ('RUNNING','PAUSED');
        SELECT COUNT(*), NVL(SUM(TOKEN_USAGE),0) INTO v_total_iters, v_total_tokens
        FROM LOOP_ITERATIONS li JOIN LOOP_RUNS lr ON li.RUN_ID = lr.RUN_ID
        WHERE lr.LOOP_ID = p_loop_id;
        SELECT JSON('{}') INTO v_result FROM DUAL;
        RETURN v_result;
    END get_loop_stats;

FUNCTION check_stop_conditions(p_run_id VARCHAR2) RETURN VARCHAR2 IS
        v_run        LOOP_RUNS%ROWTYPE;
        v_stop       JSON;
        v_max_iter   NUMBER;
        v_max_tokens NUMBER;
        v_max_dur    NUMBER;
        v_elapsed    NUMBER;
    BEGIN
        SELECT * INTO v_run FROM LOOP_RUNS WHERE RUN_ID = p_run_id;
        SELECT m.STOP_CONDITIONS INTO v_stop
        FROM LOOP_META m JOIN ENTITIES e ON m.ENTITY_ID = e.ENTITY_ID
        WHERE e.ENTITY_ID = v_run.LOOP_ID;
        v_max_iter   := JSON_VALUE(v_stop, '$.max_iterations');
        v_max_tokens := JSON_VALUE(v_stop, '$.max_tokens');
        v_max_dur    := JSON_VALUE(v_stop, '$.max_duration_seconds');
        IF v_max_iter IS NOT NULL AND v_run.ITERATION_COUNT >= v_max_iter THEN
            RETURN 'STOP';
        END IF;
        IF v_max_tokens IS NOT NULL AND v_run.TOTAL_TOKENS >= v_max_tokens THEN
            RETURN 'STOP';
        END IF;
        IF v_max_dur IS NOT NULL THEN
            v_elapsed := EXTRACT(DAY FROM (SYSTIMESTAMP - v_run.STARTED_AT))*86400 + EXTRACT(HOUR FROM (SYSTIMESTAMP - v_run.STARTED_AT))*3600 + EXTRACT(MINUTE FROM (SYSTIMESTAMP - v_run.STARTED_AT))*60 + EXTRACT(SECOND FROM (SYSTIMESTAMP - v_run.STARTED_AT));
            IF v_elapsed >= v_max_dur THEN
                RETURN 'TIMEOUT';
            END IF;
        END IF;
        RETURN 'CONTINUE';
    EXCEPTION
        WHEN NO_DATA_FOUND THEN RETURN 'STOP';
    END check_stop_conditions;

PROCEDURE cleanup_old_runs(p_days_threshold NUMBER DEFAULT 90) IS
    BEGIN
        DELETE FROM LOOP_ITERATIONS
        WHERE RUN_ID IN (
            SELECT RUN_ID FROM LOOP_RUNS
            WHERE STATUS IN ('COMPLETED','STOPPED','FAILED','TIMEOUT')
              AND COMPLETED_AT < SYSTIMESTAMP - p_days_threshold
        );
        DELETE FROM LOOP_RUNS
        WHERE STATUS IN ('COMPLETED','STOPPED','FAILED','TIMEOUT')
          AND COMPLETED_AT < SYSTIMESTAMP - p_days_threshold;
    END cleanup_old_runs;

PROCEDURE process_scheduled_triggers IS
        v_run_id VARCHAR2(64);
    BEGIN
        FOR rec IN (
            SELECT e.ENTITY_ID AS loop_id, e.OWNED_BY_AGENT
            FROM ENTITIES e
            JOIN LOOP_META m ON e.ENTITY_ID = m.ENTITY_ID
            WHERE e.ENTITY_TYPE = 'LOOP_DEFINITION'
              AND e.STATUS = 'ACTIVE'
              AND m.TRIGGER_CONFIG IS NOT NULL
              AND JSON_VALUE(m.TRIGGER_CONFIG, '$.trigger_type') = 'SCHEDULE'
              AND NOT EXISTS (
                  SELECT 1 FROM LOOP_RUNS lr
                  WHERE lr.LOOP_ID = e.ENTITY_ID
                    AND lr.STATUS IN ('RUNNING','PAUSED')
              )
        ) LOOP
            v_run_id := start_run(rec.loop_id, NVL(rec.OWNED_BY_AGENT,'system'), 'SCHEDULE', 'cron');
        END LOOP;
    END process_scheduled_triggers;

PROCEDURE check_stuck_runs IS
        v_max_dur NUMBER;
        v_stop    JSON;
    BEGIN
        FOR rec IN (
            SELECT r.RUN_ID, r.LOOP_ID, r.STARTED_AT
            FROM LOOP_RUNS r
            WHERE r.STATUS = 'RUNNING'
        ) LOOP
            BEGIN
                SELECT m.STOP_CONDITIONS INTO v_stop
                FROM LOOP_META m WHERE m.ENTITY_ID = rec.LOOP_ID;
                v_max_dur := JSON_VALUE(v_stop, '$.max_duration_seconds');
                IF v_max_dur IS NOT NULL THEN
                    IF EXTRACT(DAY FROM (SYSTIMESTAMP - rec.STARTED_AT))*86400 + EXTRACT(HOUR FROM (SYSTIMESTAMP - rec.STARTED_AT))*3600 + EXTRACT(MINUTE FROM (SYSTIMESTAMP - rec.STARTED_AT))*60 + EXTRACT(SECOND FROM (SYSTIMESTAMP - rec.STARTED_AT)) >= v_max_dur THEN
                        UPDATE LOOP_RUNS SET
                            STATUS = 'TIMEOUT',
                            ERROR_MESSAGE = 'Exceeded max_duration_seconds',
                            COMPLETED_AT = SYSTIMESTAMP
                        WHERE RUN_ID = rec.RUN_ID;
                    END IF;
                END IF;
            EXCEPTION
                WHEN OTHERS THEN NULL;
            END;
        END LOOP;
    END check_stuck_runs;

    PROCEDURE log_loop_audit(
        p_loop_id       VARCHAR2,
        p_run_id        VARCHAR2,
        p_action_type   VARCHAR2,
        p_action_by     VARCHAR2 DEFAULT NULL,
        p_action_detail JSON DEFAULT NULL
    ) IS
    BEGIN
        INSERT INTO LOOP_AUDIT (AUDIT_ID, LOOP_ID, RUN_ID, ACTION_TYPE, ACTION_BY, ACTION_DETAIL, CREATED_AT)
        VALUES (RAWTOHEX(SYS_GUID()), p_loop_id, p_run_id, p_action_type, p_action_by, p_action_detail, SYSTIMESTAMP);
    END log_loop_audit;

END LOOP_MANAGER;
/


PROMPT ============================================================
PROMPT AI Agent Infra v5.0.1 API Deployment Complete
PROMPT ============================================================
