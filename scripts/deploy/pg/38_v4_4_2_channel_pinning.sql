-- v4.4.2 additive governed Channel pinning.
-- Pinning changes inbox priority only.  It never changes membership, data
-- authority, Channel classification, or the message-derived activity clock.
ALTER TABLE cx_channels ADD COLUMN IF NOT EXISTS pinned boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_cx_channel_pin_activity
    ON cx_channels (pinned DESC, updated_at DESC, channel_id);
