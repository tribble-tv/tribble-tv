"""
Configuração do banco de dados SQLAlchemy.

SQLite para desenvolvimento local.
"""
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

# Configuração - simulando get_settings()
import os
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "tribble_tv.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

database_url = make_url(DATABASE_URL)
dialect_name = database_url.get_backend_name()


def is_sqlite() -> bool:
    return dialect_name == "sqlite"


def _ensure_sqlite_directory():
    """Cria o diretório do arquivo SQLite antes do engine abrir conexão."""
    if not is_sqlite() or not database_url.database:
        return

    if database_url.database in {":memory:", ""}:
        return

    db_path = Path(database_url.database)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_directory()

connect_args = {}
if is_sqlite():
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _import_models():
    """Importa todos os modelos para registrar as tabelas no metadata."""
    from backend.models.jellyfin_item import JellyfinItem  # noqa: F401
    from backend.models.jellyfin_library import JellyfinLibrary  # noqa: F401
    from backend.models.jellyfin_server import JellyfinServer  # noqa: F401
    from backend.models.live_stream import LiveStream  # noqa: F401
    from backend.models.media_server import MediaServer  # noqa: F401
    from backend.models.streaming_server import StreamingServer  # noqa: F401
    from backend.models.video import Video  # noqa: F401
    from backend.models.video_location import VideoLocation  # noqa: F401
    from backend.models.watch_progress import WatchProgress  # noqa: F401
    from backend.models.xtream_user import XtreamUser  # noqa: F401
    from backend.models.youtube_channel import YouTubeChannel  # noqa: F401
    from backend.models.youtube_import_job import YouTubeImportJob  # noqa: F401


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, connection_record):
    """Aplica configurações específicas para SQLite."""
    if not is_sqlite():
        return

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA busy_timeout=30000")
    if database_url.database not in {None, ":memory:", ""}:
        cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_db():
    """Generator para obter sessão do banco."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Verifica se uma coluna existe na tabela."""
    if is_sqlite():
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        return any(row[1] == column_name for row in result)
    return False  # MySQL não implementado


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    """Verifica se um índice existe na tabela."""
    if is_sqlite():
        result = conn.execute(text(f"PRAGMA index_list({table_name})"))
        return any(row[1] == index_name for row in result)
    return False


def _table_exists(conn, table_name: str) -> bool:
    """Verifica se uma tabela existe no banco."""
    if is_sqlite():
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name}
        )
        return result.first() is not None
    return False


def ensure_xtream_users_table():
    """Cria tabela de usuários Xtream se não existir (migration automática)."""
    with engine.connect() as conn:
        if not _table_exists(conn, "xtream_users"):
            conn.execute(text("""
                CREATE TABLE xtream_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN DEFAULT 1 NOT NULL,
                    max_connections INTEGER DEFAULT 1 NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_xtream_users_username ON xtream_users(username)"))
            conn.commit()
            print("[DB] Tabela xtream_users criada")


def seed_default_xtream_user():
    """Cria usuário padrão se não existir nenhum."""
    from werkzeug.security import generate_password_hash
    from datetime import datetime
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM xtream_users"))
        if result.scalar() == 0:
            now = datetime.utcnow().isoformat()
            conn.execute(
                text("""
                    INSERT INTO xtream_users (username, password_hash, is_active, max_connections, created_at, updated_at)
                    VALUES (:username, :password_hash, 1, 1, :created_at, :updated_at)
                """),
                {
                    "username": "admin",
                    "password_hash": generate_password_hash("admin123"),
                    "created_at": now,
                    "updated_at": now
                }
            )
            conn.commit()
            print("[DB] Usuário Xtream padrão criado: admin/admin123")


def init_database():
    """Inicializa o banco de dados (igual resoluta_pront)."""
    # Importa todos os modelos para registrar no metadata
    _import_models()
    
    # Cria todas as tabelas dos modelos
    Base.metadata.create_all(bind=engine)
    
    # Migrations automáticas (tabelas/colunas adicionais)
    ensure_xtream_users_table()
    
    # Seed dados padrão
    seed_default_xtream_user()
    
    print("[DB] Banco de dados inicializado")


if __name__ == "__main__":
    init_database()
