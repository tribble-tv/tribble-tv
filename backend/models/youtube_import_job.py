from datetime import datetime

from backend.extensions import db


class YouTubeImportJob(db.Model):
    __tablename__ = "youtube_import_jobs"

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(
        db.Integer, db.ForeignKey("youtube_channels.id"), nullable=False, index=True
    )
    status = db.Column(db.String(20), nullable=False, default="pending")
    total_found = db.Column(db.Integer, nullable=False, default=0)
    total_imported = db.Column(db.Integer, nullable=False, default=0)
    total_skipped = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    channel = db.relationship("YouTubeChannel", back_populates="import_jobs")
