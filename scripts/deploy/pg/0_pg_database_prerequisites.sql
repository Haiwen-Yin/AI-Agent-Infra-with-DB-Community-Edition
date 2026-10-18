-- PostgreSQL 18 / Apache AGE pre-deployment owner prerequisites.
-- Run as the database administrator in the dedicated application database.
-- Replace the psql variable value before execution; it must be a valid role
-- identifier and must match the owner configured for platform deployment.
\set ON_ERROR_STOP on
\if :{?schema_owner}
\else
\set schema_owner 'ai_agent_owner'
\endif

SELECT current_database() AS target_database,
       current_setting('server_version') AS server_version;
SELECT extname, extversion
  FROM pg_extension
 WHERE extname IN ('vector', 'age')
 ORDER BY extname;

-- AGE owns its catalog through the extension administrator. The bounded
-- application owner needs catalog usage and graph lifecycle access, but does
-- not need SUPERUSER or ownership of the extension itself.
GRANT USAGE ON SCHEMA ag_catalog TO :"schema_owner";
GRANT SELECT, INSERT, UPDATE, DELETE
  ON ag_catalog.ag_graph, ag_catalog.ag_label
  TO :"schema_owner";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ag_catalog
  TO :"schema_owner";
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ag_catalog
  TO :"schema_owner";

-- AGE create_graph creates a graph namespace in the current database.
GRANT CREATE ON DATABASE :"DBNAME" TO :"schema_owner";

-- The shared runtime role is cluster-scoped while platform data remains
-- database-scoped. The Schema Owner needs ADMIN OPTION to converge grants and
-- revocations and CREATEROLE to provision a distinct LOGIN for each Agent.
DO $cx_runtime_role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        CREATE ROLE ai_agent_runtime NOLOGIN NOSUPERUSER NOCREATEDB
            NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END
$cx_runtime_role$;
ALTER ROLE :"schema_owner" CREATEROLE;
GRANT ai_agent_runtime TO :"schema_owner" WITH ADMIN OPTION;

SELECT has_schema_privilege(:'schema_owner', 'ag_catalog', 'USAGE')
         AS age_schema_usage,
       has_table_privilege(:'schema_owner', 'ag_catalog.ag_graph',
                           'SELECT,INSERT,UPDATE,DELETE')
         AS age_graph_catalog_access,
       has_table_privilege(:'schema_owner', 'ag_catalog.ag_label',
                           'SELECT,INSERT,UPDATE,DELETE')
         AS age_label_catalog_access,
       has_database_privilege(:'schema_owner', current_database(), 'CREATE')
         AS age_graph_namespace_create,
       (SELECT rolcreaterole FROM pg_roles WHERE rolname = :'schema_owner')
         AS agent_login_create,
       EXISTS (
           SELECT 1
             FROM pg_auth_members membership
             JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
             JOIN pg_roles member_role ON member_role.oid = membership.member
            WHERE granted_role.rolname = 'ai_agent_runtime'
              AND member_role.rolname = :'schema_owner'
              AND membership.admin_option
       ) AS runtime_role_admin;
