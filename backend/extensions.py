"""Extensões do Flask - integração com database.py (igual resoluta_pront)."""
from flask_sqlalchemy import SQLAlchemy

# Instância Flask-SQLAlchemy (compatibilidade)
db = SQLAlchemy()

# Exportar do database.py para compatibilidade
from backend.database import (
    Base,
    SessionLocal,
    engine,
    get_db,
    init_database,
)

__all__ = ["db", "Base", "SessionLocal", "engine", "get_db", "init_database"]
