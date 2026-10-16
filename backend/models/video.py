from datetime import datetime

from backend.extensions import db


class Video(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    source_url = db.Column(db.String(1000), nullable=True)
    source_type = db.Column(db.String(50), nullable=False, default="hls", index=True)
    jellyfin_server_id = db.Column(db.Integer, db.ForeignKey("jellyfin_servers.id"), nullable=True, index=True)
    jellyfin_item_id = db.Column(db.String(120), nullable=True, index=True)
    external_provider = db.Column(db.String(80), nullable=True)
    category = db.Column(db.String(100), nullable=True, default=None)
    thumbnail_url = db.Column(db.String(1000), nullable=True)
    synopsis = db.Column(db.Text, nullable=True)
    youtube_video_id = db.Column(db.String(20), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    locations = db.relationship(
        "VideoLocation",
        back_populates="video",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    jellyfin_server = db.relationship("JellyfinServer", back_populates="videos")
    jellyfin_items = db.relationship("JellyfinItem", back_populates="video", lazy="dynamic")

    @property
    def is_jellyfin(self):
        return self.source_type == "jellyfin" or self.external_provider == "jellyfin"
