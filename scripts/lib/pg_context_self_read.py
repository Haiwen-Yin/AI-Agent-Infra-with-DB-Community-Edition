"""Restore native reads of an Agent's own context without opening shared data."""
import re

SCRIPT = '121_v5_0_5_pg_context_self_read.sql'
PREDICATE = """agent_id = public.current_agent_identity() AND EXISTS (
  SELECT 1 FROM public.cx_principals p
  WHERE p.principal_id = public.current_agent_identity() AND p.status = 'ACTIVE'
)"""


def render():
    sql = ('-- v5.0.5 native own-context reads; no public/shared or write permission.\n'
           'ALTER TABLE public.workspace_context ENABLE ROW LEVEL SECURITY;\n')
    for name, mode in [('cx505_context_self_read', 'PERMISSIVE'),
                       ('cx505_context_self_bound', 'RESTRICTIVE')]:
        sql += (f'DROP POLICY IF EXISTS {name} ON public.workspace_context;\n'
                f'CREATE POLICY {name} ON public.workspace_context AS {mode} '
                f'FOR SELECT TO ai_agent_runtime USING ({PREDICATE});\n')
    return SCRIPT, sql, dict(schema='v505-pg-context-self-read/v1', database='pg',
        table='workspace_context', policies=['cx505_context_self_read', 'cx505_context_self_bound'],
        authenticated_identity='SESSION_USER_AND_REGISTERED_AGENT_CONTEXT',
        reads='ACTIVE_PRINCIPAL_OWN_CONTEXT_ONLY', data_mutation=False,
        additional_write_permissions=False, historical_sql='UNCHANGED')


def _canonical(value):
    value = value.replace('public.', '')
    value = re.sub(r'::(?:text|character varying)', '', value)
    return re.sub(r'[\s()]', '', value)


def errors(cursor):
    cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.workspace_context'::regclass")
    failures = [] if cursor.fetchone() == (True,) else ['workspace_context RLS disabled']
    cursor.execute("SELECT polname,polcmd,polpermissive,"
        "ARRAY(SELECT rolname::text FROM pg_roles WHERE oid=ANY(polroles) ORDER BY rolname),"
        "pg_get_expr(polqual,polrelid),polwithcheck IS NULL FROM pg_policy "
        "WHERE polrelid='public.workspace_context'::regclass AND polname IN "
        "('cx505_context_self_read','cx505_context_self_bound') ORDER BY polname")
    rows = cursor.fetchall()
    expected = {'cx505_context_self_read': True, 'cx505_context_self_bound': False}
    if {row[0] for row in rows} != set(expected):
        failures.append('missing context self-read policy')
    for name, command, permissive, roles, predicate, no_write in rows:
        if (command != 'r' or permissive != expected[name] or roles != ['ai_agent_runtime']
                or not no_write or _canonical(predicate) != _canonical(PREDICATE)):
            failures.append('unexpected context policy: ' + name)
    return failures
