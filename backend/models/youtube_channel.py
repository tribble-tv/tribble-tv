from datetime import datetime

from backend.extensions import db


class YouTubeChannel(db.Model):
    __tablename__ = "youtube_channels"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    handle = db.Column(db.String(255), nullable=False, unique=True)
    channel_url = db.Column(db.String(1000), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    import_jobs = db.relationship(
        "YouTubeImportJob",
        back_populates="channel",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    @property
    def videos_url(self):
        """URL pública do canal para listagem de vídeos."""
        if self.channel_url:
            return self.channel_url
        return f"https://www.youtube.com/{self.handle}/videos"
