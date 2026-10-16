from datetime import datetime

from backend.extensions import db


class AppSetting(db.Model):
    """Configurações key/value persistidas (ex.: estratégia do balanceador)."""

    __tablename__ = "app_settings"

    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.String(500), nullable=True)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AppSetting {self.key}={self.value!r}>"
