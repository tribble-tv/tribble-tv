"""Modelo para servidores de streaming no balanceador de carga."""
from datetime import datetime
from backend.extensions import db


class StreamingServer(db.Model):
    """Servidor de streaming para distribuição de carga."""
    
    __tablename__ = "streaming_servers"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, default=8080, nullable=False)
    protocol = db.Column(db.String(10), default="http", nullable=False)  # http/https
    
    # Status e capacidade
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    max_connections = db.Column(db.Integer, default=100, nullable=False)
    current_connections = db.Column(db.Integer, default=0, nullable=False)
    
    # Balanceamento
    priority = db.Column(db.Integer, default=100, nullable=False)  # Peso para weighted round robin
    region = db.Column(db.String(50), nullable=True)  # Para geo-routing (BR, US, EU, etc)
    
    # Health check
    health_status = db.Column(db.String(20), default="unknown", nullable=False)  # healthy/unreachable/maintenance
    last_health_check = db.Column(db.DateTime, nullable=True)
    health_check_failures = db.Column(db.Integer, default=0, nullable=False)
    latency_ms = db.Column(db.Integer, nullable=True)  # Latência da última checagem
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relacionamentos
    live_streams = db.relationship("LiveStream", backref="server", lazy=True)
    connections = db.relationship("Connection", backref="server", lazy=True)
    
    def __repr__(self):
        return f"<StreamingServer {self.name} ({self.host}:{self.port}) - {self.health_status}>"
    
    def to_dict(self):
        """Serializa servidor para API."""
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "is_active": self.is_active,
            "max_connections": self.max_connections,
            "current_connections": self.current_connections,
            "available_slots": self.max_connections - self.current_connections,
            "priority": self.priority,
            "region": self.region,
            "health_status": self.health_status,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @property
    def url(self):
        """URL base do servidor."""
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @property
    def is_available(self):
        """Verifica se servidor está disponível para novas conexões."""
        return (
            self.is_active and 
            self.health_status == "healthy" and
            self.current_connections < self.max_connections
        )
    
    @property
    def load_percentage(self):
        """Percentual de carga do servidor."""
        if self.max_connections == 0:
            return 0
        return (self.current_connections / self.max_connections) * 100
