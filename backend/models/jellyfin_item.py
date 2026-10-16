from datetime import datetime

from backend.extensions import db


class JellyfinItem(db.Model):
    __tablename__ = "jellyfin_items"

    id = db.Column(db.Integer, primary_key=True)
    jellyfin_server_id = db.Column(db.Integer, db.ForeignKey("jellyfin_servers.id"), nullable=False, index=True)
    jellyfin_item_id = db.Column(db.String(120), nullable=False)
    event_id = db.Column(db.Integer, nullable=True, index=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    media_type = db.Column(db.String(80), nullable=True)
    path = db.Column(db.String(1000), nullable=True)
    runtime_ticks = db.Column(db.BigInteger, nullable=True)
    image_tag = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    jellyfin_server = db.relationship("JellyfinServer", back_populates="items")
    video = db.relationship("Video", back_populates="jellyfin_items")

    __table_args__ = (
        db.UniqueConstraint("jellyfin_server_id", "jellyfin_item_id", name="uq_jellyfin_item_server_item"),
    )
