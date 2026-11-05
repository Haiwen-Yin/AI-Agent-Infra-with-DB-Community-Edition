-- v5.0.4: retain migration 119; recognize both exact native array cast forms.
DO $cx120$
DECLARE r RECORD;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='cx_agent_sources'::regclass AND conname='cx119_source_kind') THEN
    ALTER TABLE CX_AGENT_SOURCES ADD CONSTRAINT CX119_SOURCE_KIND CHECK (SOURCE_KIND IN ('DOCUMENT','GITHUB','STATUSPAGE'));
  END IF;
  FOR r IN SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint
    WHERE conrelid='cx_agent_sources'::regclass AND contype='c' AND conname<>'cx119_source_kind'
    AND conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid='cx_agent_sources'::regclass AND attname='source_kind')]::smallint[]
  LOOP
    IF regexp_replace(r.definition,'[[:space:]()]','','g') IN (
      'CHECKsource_kind::text=ANYARRAY[''DOCUMENT''::charactervarying::text,''GITHUB''::charactervarying::text]',
      'CHECKsource_kind::text=ANYARRAY[''DOCUMENT''::charactervarying,''GITHUB''::charactervarying]::text[]') THEN
      EXECUTE format('ALTER TABLE CX_AGENT_SOURCES DROP CONSTRAINT %I',r.conname);
    END IF;
  END LOOP;
END;
$cx120$;
