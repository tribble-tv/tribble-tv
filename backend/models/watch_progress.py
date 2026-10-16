from datetime import datetime

from backend.extensions import db


class WatchProgress(db.Model):
    __tablename__ = "watch_progress"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("xtream_users.id"), nullable=False, index=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False, index=True)
    position_seconds = db.Column(db.Float, nullable=False, default=0)
    duration_seconds = db.Column(db.Float, nullable=False, default=0)
    progress_percent = db.Column(db.Float, nullable=False, default=0)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    last_watched_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("XtreamUser", backref=db.backref("watch_progress", lazy="dynamic"))
    video = db.relationship("Video", backref=db.backref("watch_progress", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("user_id", "video_id", name="uq_watch_progress_user_video"),
    )

    def to_dict(self):
        return {
            "video_id": self.video_id,
            "position_seconds": float(self.position_seconds or 0),
            "duration_seconds": float(self.duration_seconds or 0),
            "progress_percent": round(float(self.progress_percent or 0), 2),
            "completed": bool(self.completed),
            "last_watched_at": self.last_watched_at.isoformat() if self.last_watched_at else None,
        }
