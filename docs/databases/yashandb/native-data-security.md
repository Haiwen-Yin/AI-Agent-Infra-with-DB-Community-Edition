# Native Entity Access v5.0.0

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](native-data-security_zh.md)

The current baseline retains migration 70 and its successors. This applies to
Community and Enterprise. Independent Agent users no longer access ENTITIES,
KNOWLEDGE_META, ENTITY_EMBEDDINGS, ENTITY_EDGES or ENTITY_TAGS directly and cannot
execute legacy Owner-definer packages. Platform Owner APIs remain separate;
an Agent must never receive or fall back to Owner credentials.

## Read Interfaces

| View | Content |
|---|---|
| CX_AGENT_ENTITY_READ | Permitted entity rows |
| CX_AGENT_KNOWLEDGE_READ | Permitted knowledge entities |
| CX_AGENT_KNOWLEDGE_META_READ | Metadata of permitted entities |
| CX_AGENT_EMBEDDING_READ | Embeddings of permitted entities |
| CX_AGENT_EDGE_READ | Edges with both endpoints permitted |

The database binds SESSION_USER to CX_AGENT_DB_IDENTITIES and an active
CX_PRINCIPALS record. Knowledge policies are evaluated from current company,
principal and organization-closure facts with validity bounds. Existing policies
take precedence over legacy VISIBILITY. Without a policy, only ownership or
PUBLIC permits reading; SHARED alone is not an implicit company-wide grant.
The mapping and policy tables are not writable by independent business users.

## Native Private Writes

```sql
BEGIN
  CX_AGENT_ENTITY_API.CREATE_PRIVATE(
    'unique-client-generated-id', 'KNOWLEDGE', 'Title', 'Content');
END;
/
COMMIT;
```

CREATE_PRIVATE accepts MEMORY or KNOWLEDGE, derives ownership from the login,
and always creates PRIVATE data. UPDATE_PRIVATE accepts id, title and content;
it only modifies the caller's private entity without a governed knowledge policy.
Neither procedure commits the caller transaction. These are minimal native
entity operations, not the complete memory lifecycle or governed sharing API.
Use authenticated platform APIs for lifecycle, policy, organization and graph
mutations. Existing raw-table SQL integrations must adopt the views/procedures
or platform API; silently using Owner credentials is not a compatibility option.

## Migration Diagnostics

An early unpublished migration 70 failed with YAS-04209 because dynamic SQL
double-escaped USERENV. The corrected version uses ordinary view DDL. Revocation
suppresses only known absent-grant/absent-grantee errors; other failures block
deployment. Bootstrap reports the database error code and statement index, never
password-bearing SQL. Do not override an applied migration checksum to repair a
customer deployment.

Current validation uses explicitly classified isolated release targets, not production,
baseline or TEST PDBs. These checks establish the named entity interfaces, not
blanket isolation of all historical tables, procedures or graph algorithms.
