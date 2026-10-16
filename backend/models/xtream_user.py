from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from backend.extensions import db


class XtreamUser(db.Model):
    """Usuário para autenticação Xtream Codes API."""
    
    __tablename__ = "xtream_users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    max_connections = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def set_password(self, password):
        """Define a senha do usuário (hash)."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifica se a senha está correta."""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Retorna dados do usuário para API."""
        return {
            "id": self.id,
            "username": self.username,
            "is_active": self.is_active,
            "max_connections": self.max_connections,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
