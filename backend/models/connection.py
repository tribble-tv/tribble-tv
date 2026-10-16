"""Modelo para conexões ativas de clientes (tracking de viewers)."""
from datetime import datetime
from backend.extensions import db


class Connection(db.Model):
    """Conexão ativa de um cliente assistindo VOD ou Live."""
    
    __tablename__ = "connections"
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(100), nullable=False, index=True)
    
    # Servidor utilizado
    server_id = db.Column(db.Integer, db.ForeignKey("streaming_servers.id"), nullable=False)
    
    # Tipo de conteúdo (VOD ou Live)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=True)
    live_stream_id = db.Column(db.Integer, db.ForeignKey("live_streams.id"), nullable=True)
    
    # Timestamps
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    last_activity_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Métricas
    bytes_transferred = db.Column(db.BigInteger, default=0, nullable=False)
    segments_downloaded = db.Column(db.Integer, default=0, nullable=False)
    
    # Informações do cliente
    user_agent = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    country = db.Column(db.String(2), nullable=True)  # Código do país
    city = db.Column(db.String(100), nullable=True)
    
    # Player info
    player_type = db.Column(db.String(50), nullable=True)  # vlc/xciptv/browser/etc
    device_type = db.Column(db.String(50), nullable=True)  # mobile/desktop/tv
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    def __repr__(self):
        content = f"video={self.video_id}" if self.video_id else f"live={self.live_stream_id}"
        return f"<Connection {self.client_id} {content} server={self.server_id}>"
    
    def to_dict(self):
        """Serializa conexão para API."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "server_id": self.server_id,
            "video_id": self.video_id,
            "live_stream_id": self.live_stream_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "bytes_transferred": self.bytes_transferred,
            "ip_address": self.ip_address,
            "country": self.country,
            "device_type": self.device_type,
            "player_type": self.player_type,
            "is_active": self.is_active,
        }
    
    @property
    def duration_seconds(self):
        """Duração da conexão em segundos."""
        end = self.ended_at or datetime.utcnow()
        return int((end - self.started_at).total_seconds())
    
    def end(self):
        """Marca conexão como encerrada."""
        self.is_active = False
        self.ended_at = datetime.utcnow()
    
    def touch(self):
        """Atualiza última atividade."""
        self.last_activity_at = datetime.utcnow()
