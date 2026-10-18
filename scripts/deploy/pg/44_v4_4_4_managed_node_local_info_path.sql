-- v4.4.4 correction: local Agent files belong to the managed node, not shared storage.
ALTER TABLE cx_managed_nodes ADD COLUMN IF NOT EXISTS agent_info_path varchar(512);
UPDATE cx_managed_node_storage_bindings b
SET status='REMOVED', reason='Obsolete local-directory profile; local path is now stored on the managed node'
WHERE b.storage_id IN (SELECT storage_id FROM cx_shared_storage_profiles WHERE storage_purpose IN ('ADMIN_AGENT_RUNTIME','AGENT_POOL_AGENT_RUNTIME'))
  AND b.status <> 'REMOVED';
UPDATE cx_shared_storage_profiles
SET status='REMOVED', validation_state='DEPRECATED', reason='Local directory is now configured on the managed node'
WHERE storage_purpose IN ('ADMIN_AGENT_RUNTIME','AGENT_POOL_AGENT_RUNTIME');
