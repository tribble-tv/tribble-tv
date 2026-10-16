from datetime import datetime

from backend.extensions import db


class JellyfinServer(db.Model):
    __tablename__ = "jellyfin_servers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    base_url = db.Column(db.String(500), nullable=False)
    internal_url = db.Column(db.String(500), nullable=True)
    api_key = db.Column(db.String(255), nullable=False)
    admin_username = db.Column(db.String(120), nullable=True)
    region = db.Column(db.String(80), nullable=True)
    priority = db.Column(db.Integer, nullable=False, default=100, index=True)
    weight = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    health_status = db.Column(db.String(30), nullable=False, default="unknown")
    last_health_check = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    libraries = db.relationship(
        "JellyfinLibrary",
        back_populates="jellyfin_server",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    items = db.relationship(
        "JellyfinItem",
        back_populates="jellyfin_server",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    videos = db.relationship("Video", back_populates="jellyfin_server", lazy="dynamic")

    @property
    def normalized_base_url(self):
        return (self.base_url or "").rstrip("/")

    @property
    def normalized_internal_url(self):
        return (self.internal_url or self.base_url or "").rstrip("/")
