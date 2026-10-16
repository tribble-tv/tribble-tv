from datetime import datetime

from backend.extensions import db


class JellyfinLibrary(db.Model):
    __tablename__ = "jellyfin_libraries"

    id = db.Column(db.Integer, primary_key=True)
    jellyfin_server_id = db.Column(db.Integer, db.ForeignKey("jellyfin_servers.id"), nullable=False, index=True)
    jellyfin_library_id = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    jellyfin_server = db.relationship("JellyfinServer", back_populates="libraries")

    __table_args__ = (
        db.UniqueConstraint("jellyfin_server_id", "jellyfin_library_id", name="uq_jellyfin_library_server_item"),
    )
