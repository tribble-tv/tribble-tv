from datetime import datetime

from backend.extensions import db


class VideoLocation(db.Model):
    __tablename__ = "video_locations"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False, index=True)
    media_server_id = db.Column(db.Integer, db.ForeignKey("media_servers.id"), nullable=False, index=True)
    storage_path = db.Column(db.String(1000), nullable=False)
    source_type = db.Column(db.String(50), nullable=False, default="hls")
    is_primary = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    video = db.relationship("Video", back_populates="locations")
    media_server = db.relationship("MediaServer", back_populates="locations")

    __table_args__ = (
        db.UniqueConstraint("video_id", "media_server_id", "storage_path", name="uq_video_location_path"),
    )
