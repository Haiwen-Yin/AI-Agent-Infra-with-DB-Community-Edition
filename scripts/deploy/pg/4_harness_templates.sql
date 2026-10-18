-- AI Agent Infra v4.0.1 - PostgreSQL built-in harness templates

WITH templates(title, summary, category) AS (
    VALUES
        ('Research Analyst', 'Harness template for research and analysis tasks', 'research'),
        ('Code Assistant', 'Harness template for code generation and development tasks', 'development'),
        ('Data Analyst', 'Harness template for data analysis and reporting tasks', 'analytics'),
        ('Task Planner', 'Harness template for task decomposition and planning', 'orchestration'),
        ('Security Auditor', 'Harness template for security review and compliance auditing', 'security')
)
INSERT INTO entities (
    entity_type, title, summary, category, status, visibility,
    importance, owned_by_agent, source_agent
)
SELECT
    'HARNESS_TEMPLATE', t.title, t.summary, t.category, 'ACTIVE', 'SHARED',
    2, 'SYSTEM', 'SYSTEM'
FROM templates t
WHERE NOT EXISTS (
    SELECT 1
    FROM entities e
    WHERE e.entity_type = 'HARNESS_TEMPLATE'
      AND e.title = t.title
);

WITH templates(title, input_schema, output_schema, execution_mode) AS (
    VALUES
        ('Research Analyst', '{"role":"","domain":"","objective":"","query":""}'::jsonb,
         '{"findings":"","sources":""}'::jsonb, 'SEQUENTIAL'),
        ('Code Assistant', '{"role":"","language":"","guidelines":"","task":""}'::jsonb,
         '{"solution":"","explanation":""}'::jsonb, 'SEQUENTIAL'),
        ('Data Analyst', '{"role":"","focus_area":"","data_query":""}'::jsonb,
         '{"analysis":"","recommendations":""}'::jsonb, 'PARALLEL'),
        ('Task Planner', '{"role":"","constraints":"","objective":""}'::jsonb,
         '{"plan":"","dependencies":""}'::jsonb, 'CONDITIONAL'),
        ('Security Auditor', '{"role":"","policies":"","action":""}'::jsonb,
         '{"assessment":"","risks":"","mitigations":""}'::jsonb, 'SEQUENTIAL')
)
INSERT INTO harness_meta (
    entity_id, entity_type, template_version, input_schema,
    output_schema, execution_mode
)
SELECT
    e.entity_id, 'HARNESS_TEMPLATE', '1', t.input_schema,
    t.output_schema, t.execution_mode
FROM templates t
JOIN entities e
  ON e.entity_type = 'HARNESS_TEMPLATE'
 AND e.title = t.title
ON CONFLICT (entity_id, entity_type) DO UPDATE
SET template_version = EXCLUDED.template_version,
    input_schema = EXCLUDED.input_schema,
    output_schema = EXCLUDED.output_schema,
    execution_mode = EXCLUDED.execution_mode;

INSERT INTO system_config (config_key, config_value, description, updated_at)
VALUES (
    'harness.builtin_templates',
    '5',
    'Number of built-in harness templates',
    CURRENT_TIMESTAMP
)
ON CONFLICT (config_key) DO UPDATE
SET config_value = EXCLUDED.config_value,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;
