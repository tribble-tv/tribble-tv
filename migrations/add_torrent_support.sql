-- Migration: add torrent support
-- source_type = 'torrent' is already supported by the VARCHAR column.
-- source_url stores the magnet link or .torrent URL.
-- No schema change required; this migration documents the convention.

-- Optional: index para buscas por source_type='torrent'
CREATE INDEX IF NOT EXISTS idx_videos_source_type_torrent
    ON videos (source_type)
    WHERE source_type = 'torrent';
