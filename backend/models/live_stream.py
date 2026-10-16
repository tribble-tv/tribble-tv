"""Modelo para transmissões ao vivo (Live Streaming)."""
from datetime import datetime
import secrets
import string
from backend.extensions import db


# Importação adiada para evitar circular imports
def _get_connection_model():
    from backend.models.connection import Connection
    return Connection


class LiveStream(db.Model):
    """Transmissão ao vivo com ingest RTMP/HLS e playback."""
    
    __tablename__ = "live_streams"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Chave única para ingest (RTMP/WebRTC)
    stream_key = db.Column(db.String(100), unique=True, nullable=False)
    
    # Status da transmissão
    status = db.Column(db.String(20), default="offline", nullable=False)  # offline/starting/live/ended/error
    
    # Servidor atual
    server_id = db.Column(db.Integer, db.ForeignKey("streaming_servers.id"), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    
    # Métricas
    viewer_count = db.Column(db.Integer, default=0, nullable=False)
    peak_viewers = db.Column(db.Integer, default=0, nullable=False)
    total_bytes_streamed = db.Column(db.BigInteger, default=0, nullable=False)
    
    # URLs
    ingest_url = db.Column(db.String(500), nullable=True)  # RTMP/WebRTC endpoint para OBS/FFmpeg
    playback_url = db.Column(db.String(500), nullable=True)  # HLS endpoint para viewers
    
    # Configurações
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_public = db.Column(db.Boolean, default=True, nullable=False)  # Stream público ou privado
    password = db.Column(db.String(100), nullable=True)  # Senha para streams privados
    
    # Qualidade (para transcodificação futura)
    quality_settings = db.Column(db.JSON, nullable=True)  # {"resolution": "1080p", "bitrate": "4500k"}
    
    # Relacionamentos - usando lambda para evitar conflito com sqlalchemy.engine.Connection
    connections = db.relationship(
        lambda: _get_connection_model(),
        backref="live_stream",
        lazy=True
    )
    
    def __repr__(self):
        return f"<LiveStream {self.name} ({self.status})>"
    
    @staticmethod
    def generate_stream_key(length=16):
        """Gera chave de stream aleatória segura."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def to_dict(self, include_private=False):
        """Serializa stream para API."""
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "server_id": self.server_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "viewer_count": self.viewer_count,
            "peak_viewers": self.peak_viewers,
            "playback_url": self.playback_url,
            "is_active": self.is_active,
            "is_public": self.is_public,
            "quality_settings": self.quality_settings,
        }
        
        if include_private:
            data.update({
                "stream_key": self.stream_key,
                "ingest_url": self.ingest_url,
            })
        
        return data
    
    def start(self, server):
        """Inicia a transmissão em um servidor."""
        self.status = "live"
        self.server_id = server.id
        self.started_at = datetime.utcnow()
        self.ended_at = None
        self.ingest_url = f"rtmp://{server.host}:1935/live/{self.stream_key}"
        self.playback_url = f"{server.url}/live/{self.stream_key}/playlist.m3u8"
    
    def stop(self):
        """Para a transmissão."""
        self.status = "ended"
        self.ended_at = datetime.utcnow()
        self.viewer_count = 0
