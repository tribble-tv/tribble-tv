from datetime import datetime

from backend.extensions import db


class MediaServer(db.Model):
    __tablename__ = "media_servers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    public_url = db.Column(db.String(500), nullable=False)
    internal_url = db.Column(db.String(500), nullable=True)
    region = db.Column(db.String(80), nullable=True)
    provider = db.Column(db.String(80), nullable=True)
    server_type = db.Column(db.String(50), nullable=False, default="go-engine")
    api_key = db.Column(db.String(255), nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=100, index=True)
    weight = db.Column(db.Integer, nullable=False, default=1)
    max_connections = db.Column(db.Integer, nullable=False, default=0)
    current_connections = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    health_status = db.Column(db.String(30), nullable=False, default="unknown")
    last_health_check = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    locations = db.relationship(
        "VideoLocation",
        back_populates="media_server",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    @property
    def normalized_public_url(self):
        return (self.public_url or "").rstrip("/")

    @property
    def is_stream_capable(self):
        return (self.server_type or "go-engine") == "go-engine"

    def has_capacity(self):
        return self.max_connections <= 0 or self.current_connections < self.max_connections
