-- v5.0.2 PostgreSQL-only repair of the historical duplicate approval enum.
-- Keep migrations 1 and 60 immutable. Preserve status, privileges and rows.
DO $$
DECLARE
    v_table regclass;
    v_check record;
    v_expected text;
    v_expression text;
    v_column text;
    v_token text[];
    v_found integer := 0;
BEGIN
    v_table := to_regclass(format('%I.approval_requests', current_schema()));
    IF v_table IS NULL OR NOT EXISTS (
        SELECT 1 FROM pg_class WHERE oid = v_table AND relkind = 'r' AND relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
    ) THEN
        RAISE EXCEPTION 'v502 approval repair requires the current owner schema table';
    END IF;
    EXECUTE format('LOCK TABLE %s IN ACCESS EXCLUSIVE MODE', v_table);
    FOR v_check IN
        SELECT c.conname, c.convalidated, c.connoinherit, c.conislocal, c.coninhcount,
               pg_get_expr(c.conbin, c.conrelid) AS expression,
               ARRAY(SELECT upper(a.attname) FROM unnest(c.conkey) WITH ORDINALITY k(num, ord)
                     JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num ORDER BY k.ord) AS columns
        FROM pg_constraint c WHERE c.conrelid = v_table AND c.contype = 'c'
    LOOP
        IF v_check.conname = 'ck_ar_entity' THEN
            v_column := 'ENTITY_TYPE';
            v_expected := 'ENTITY_TYPE=ANYARRAY[''STEP'',''LOOP'',''TOOL'']';
        ELSIF v_check.conname = 'ck_approval_entity' THEN
            v_column := 'ENTITY_TYPE';
            v_expected := 'ENTITY_TYPE=ANYARRAY[''STEP'',''LOOP'',''TOOL'',''ORGANIZATION_CHANGE'']';
            v_found := v_found + 1;
        ELSIF v_check.conname = 'ck_ar_status' THEN
            v_column := 'APPROVAL_STATUS';
            v_expected := 'APPROVAL_STATUS=ANYARRAY[''PENDING'',''APPROVED'',''REJECTED'']';
            v_found := v_found + 1;
        ELSE
            IF v_check.columns && ARRAY['ENTITY_TYPE','APPROVAL_STATUS'] THEN
                RAISE EXCEPTION 'v502 approval repair found an unknown enum CHECK: %', v_check.conname;
            END IF;
            CONTINUE;
        END IF;
        v_expression := '';
        FOR v_token IN SELECT regexp_matches(v_check.expression, '(''([^'']|'''')*''|[^'']+)', 'g') LOOP
            IF left(v_token[1], 1) = '''' THEN
                v_expression := v_expression || v_token[1];
            ELSE
                v_expression := v_expression || upper(regexp_replace(
                    regexp_replace(v_token[1], '::(character varying|text)(\[\])?', '', 'g'), '[[:space:]()"]', '', 'g'));
            END IF;
        END LOOP;
        IF v_check.columns <> ARRAY[v_column] OR NOT v_check.convalidated OR v_check.connoinherit
           OR NOT v_check.conislocal OR v_check.coninhcount <> 0 OR v_expression <> v_expected THEN
            RAISE EXCEPTION 'v502 approval repair found an unknown CHECK definition: %', v_check.conname;
        END IF;
    END LOOP;
    IF v_found <> 2 THEN
        RAISE EXCEPTION 'v502 approval repair requires the existing canonical entity and status CHECKs';
    END IF;
    -- Remove only the exact known legacy restriction, after all checks passed.
    EXECUTE format('ALTER TABLE %s DROP CONSTRAINT IF EXISTS ck_ar_entity', v_table);
END;
$$;
