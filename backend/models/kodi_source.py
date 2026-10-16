from datetime import datetime

from backend.extensions import db


class KodiSource(db.Model):
    __tablename__ = "kodi_sources"

    KIND_M3U = "m3u"
    KIND_ADDON = "addon"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    playlist_url = db.Column(db.String(1000), nullable=False, unique=True)
    source_kind = db.Column(db.String(30), nullable=False, default=KIND_M3U)
    source_url = db.Column(db.String(1000), nullable=True)
    addon_id = db.Column(db.String(160), nullable=True)
    entry_path = db.Column(db.String(500), nullable=True)
    default_category = db.Column(db.String(100), nullable=True)
    sync_interval_minutes = db.Column(db.Integer, nullable=True)
    last_scan_depth = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(20), nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    last_stats = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    @property
    def effective_source_url(self):
        return (self.source_url or self.playlist_url or "").strip()

    @property
    def is_addon(self):
        return self.source_kind == self.KIND_ADDON
