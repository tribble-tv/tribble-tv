"""Serviço de configurações key/value persistidas em `AppSetting`."""
from typing import Optional

from sqlalchemy.exc import OperationalError

from backend.extensions import db
from backend.models import AppSetting


# Chaves padronizadas para evitar typos espalhados pelo código.
KEY_VOD_STRATEGY = "load_balancer.vod_strategy"
KEY_LIVE_STRATEGY = "load_balancer.live_strategy"


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Lê uma configuração persistida. Retorna `default` se ausente ou em erro."""
    try:
        record = AppSetting.query.get(key)
    except OperationalError:
        # Tabela ainda não existe (deploy antigo) — usa default.
        db.session.rollback()
        return default
    if record is None or record.value is None:
        return default
    return record.value


def set_setting(key: str, value: Optional[str]) -> AppSetting:
    """Cria ou atualiza uma configuração key/value."""
    record = AppSetting.query.get(key)
    if record is None:
        record = AppSetting(key=key, value=value)
        db.session.add(record)
    else:
        record.value = value
    db.session.commit()
    return record
