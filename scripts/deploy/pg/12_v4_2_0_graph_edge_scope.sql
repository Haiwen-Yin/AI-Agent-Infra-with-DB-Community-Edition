-- v4.2.0 Graph Engineering - version-scoped Edge identity
ALTER TABLE IF EXISTS graph_edges DROP CONSTRAINT IF EXISTS graph_edges_pkey;
ALTER TABLE IF EXISTS graph_edges
    ADD CONSTRAINT graph_edges_pkey PRIMARY KEY (graph_version_id, edge_id);
