import os

from flask import Flask
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from backend.database import DEFAULT_DATABASE_URL
from backend.extensions import db
from backend.routes.admin import admin_bp
from backend.routes.admin_xtream import admin_xtream_bp
from backend.routes.client import client_bp
from backend.routes.xtream import xtream_bp

try:
    from backend.routes.admin_youtube import admin_youtube_bp
except ImportError:
    admin_youtube_bp = None


def _ensure_lightweight_schema_updates(app):
    """Apply minimal additive updates for deployments that use db.create_all()."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if "videos" not in table_names:
        return
    columns = {column["name"] for column in inspector.get_columns("videos")}
    statements = []
    if "source_type" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN source_type VARCHAR(50) NOT NULL DEFAULT 'hls'")
    if "source_url" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN source_url VARCHAR(1000)")
    if "jellyfin_server_id" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN jellyfin_server_id INTEGER")
    if "jellyfin_item_id" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN jellyfin_item_id VARCHAR(120)")
    if "external_provider" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN external_provider VARCHAR(80)")
    if "category" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN category VARCHAR(100)")
    if "thumbnail_url" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN thumbnail_url VARCHAR(1000)")
    if "youtube_video_id" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN youtube_video_id VARCHAR(20)")
    if "synopsis" not in columns:
        statements.append("ALTER TABLE videos ADD COLUMN synopsis TEXT")

    schema_changed = bool(statements)
    for statement in statements:
        db.session.execute(text(statement))
    if "app_settings" not in table_names:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key VARCHAR(120) PRIMARY KEY,
                value VARCHAR(500),
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        schema_changed = True
    if "watch_progress" not in table_names:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS watch_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                position_seconds FLOAT NOT NULL DEFAULT 0,
                duration_seconds FLOAT NOT NULL DEFAULT 0,
                progress_percent FLOAT NOT NULL DEFAULT 0,
                completed BOOLEAN NOT NULL DEFAULT 0,
                last_watched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_watch_progress_user_video UNIQUE (user_id, video_id),
                FOREIGN KEY(user_id) REFERENCES xtream_users (id),
                FOREIGN KEY(video_id) REFERENCES videos (id)
            )
        """))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_watch_progress_user_id ON watch_progress (user_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_watch_progress_video_id ON watch_progress (video_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_watch_progress_last_watched_at ON watch_progress (last_watched_at)"))
        schema_changed = True
    if "kodi_sources" in table_names:
        kodi_columns = {column["name"] for column in inspector.get_columns("kodi_sources")}
        kodi_statements = []
        if "source_kind" not in kodi_columns:
            kodi_statements.append("ALTER TABLE kodi_sources ADD COLUMN source_kind VARCHAR(30) NOT NULL DEFAULT 'm3u'")
        if "source_url" not in kodi_columns:
            kodi_statements.append("ALTER TABLE kodi_sources ADD COLUMN source_url VARCHAR(1000)")
        if "addon_id" not in kodi_columns:
            kodi_statements.append("ALTER TABLE kodi_sources ADD COLUMN addon_id VARCHAR(160)")
        if "entry_path" not in kodi_columns:
            kodi_statements.append("ALTER TABLE kodi_sources ADD COLUMN entry_path VARCHAR(500)")
        if "sync_interval_minutes" not in kodi_columns:
            kodi_statements.append("ALTER TABLE kodi_sources ADD COLUMN sync_interval_minutes INTEGER")
        if "last_scan_depth" not in kodi_columns:
            kodi_statements.append("ALTER TABLE kodi_sources ADD COLUMN last_scan_depth INTEGER")
        for statement in kodi_statements:
            db.session.execute(text(statement))
        schema_changed = schema_changed or bool(kodi_statements)
    if schema_changed:
        db.session.commit()


def _create_flask_sqlalchemy_tables():
    try:
        db.create_all()
    except OperationalError as exc:
        if "already exists" not in str(exc).lower():
            raise
        db.session.rollback()
        db.create_all()


def _seed_media_servers():
    from backend.models import MediaServer

    def env_value(new_name, old_name, default=""):
        return os.getenv(new_name) or os.getenv(old_name) or default

    names = [v.strip() for v in env_value("MEDIA_SERVER_SEED_NAMES", "MEDIA_SEED_NAMES").split(",")]
    types = [v.strip() for v in env_value("MEDIA_SERVER_SEED_TYPES", "MEDIA_SEED_TYPES").split(",")]
    public_urls = [
        v.strip()
        for v in env_value("MEDIA_SERVER_SEED_PUBLIC_URLS", "MEDIA_SEED_PUBLIC_URLS").split(",")
        if v.strip()
    ]
    internal_urls = [
        v.strip()
        for v in env_value("MEDIA_SERVER_SEED_INTERNAL_URLS", "MEDIA_SEED_INTERNAL_URLS").split(",")
    ]
    api_keys = [v.strip() for v in env_value("MEDIA_SERVER_SEED_API_KEYS", "MEDIA_SEED_API_KEYS").split(",")]
    priorities = [
        v.strip()
        for v in env_value("MEDIA_SERVER_SEED_PRIORITIES", "MEDIA_SEED_PRIORITIES").split(",")
    ]
    for i, public_url in enumerate(public_urls):
        normalized_public_url = public_url.rstrip("/")
        exists = MediaServer.query.filter_by(public_url=public_url.rstrip("/")).first()
        internal = internal_urls[i] if i < len(internal_urls) and internal_urls[i] else None
        priority = int(priorities[i]) if i < len(priorities) and priorities[i].isdigit() else 100
        server_name = names[i] if i < len(names) and names[i] else f"Media Server {i + 1}"
        server_type = types[i] if i < len(types) and types[i] else "go-engine"
        seed_values = {
            "name": server_name,
            "public_url": normalized_public_url,
            "internal_url": internal.rstrip("/") if internal else None,
            "api_key": api_keys[i] if i < len(api_keys) else "",
            "server_type": server_type,
            "priority": priority,
        }
        if not exists:
            exists = MediaServer.query.filter_by(name=server_name, server_type=server_type).first()
        if exists:
            for key, value in seed_values.items():
                setattr(exists, key, value)
            continue
        db.session.add(
            MediaServer(
                **seed_values,
                weight=1,
                max_connections=0,
                is_active=True,
            )
        )
    db.session.commit()


def _seed_jellyfin_servers():
    from backend.models import JellyfinServer
    urls = [u.strip() for u in os.getenv("JELLYFIN_SEED_URLS", "").split(",") if u.strip()]
    usernames = [u.strip() for u in os.getenv("JELLYFIN_SEED_USERNAMES", "").split(",")]
    passwords = [u.strip() for u in os.getenv("JELLYFIN_SEED_PASSWORDS", "").split(",")]
    api_keys = [u.strip() for u in os.getenv("JELLYFIN_SEED_API_KEYS", "").split(",")]
    for i, url in enumerate(urls):
        exists = JellyfinServer.query.filter_by(base_url=url.rstrip("/")).first()
        if exists:
            continue
        server = JellyfinServer(
            name=f"Jellyfin {i + 1}",
            base_url=url.rstrip("/"),
            api_key=api_keys[i] if i < len(api_keys) else "",
            admin_username=usernames[i] if i < len(usernames) else None,
            priority=100 + i * 10,
            is_active=True,
        )
        db.session.add(server)
    db.session.commit()


def _seed_xtream_users():
    """Cria usuários Xtream Codes padrão do ambiente."""
    from backend.models import XtreamUser
    
    users_env = os.getenv("XTREAM_SEED_USERS", "")
    print(f"[DEBUG] XTREAM_SEED_USERS env: {users_env}")
    if not users_env:
        print("[DEBUG] Nenhum usuário para seed")
        return
    
    pairs = [p.strip() for p in users_env.split(",") if p.strip()]
    print(f"[DEBUG] Pares encontrados: {pairs}")
    
    created_count = 0
    for pair in pairs:
        if ":" not in pair:
            print(f"[DEBUG] Par inválido (sem :): {pair}")
            continue
        username, password = pair.split(":", 1)
        username = username.strip()
        password = password.strip()
        
        if not username or not password:
            print(f"[DEBUG] Username ou password vazio")
            continue
        
        # Verificar se já existe
        exists = XtreamUser.query.filter_by(username=username).first()
        if exists:
            print(f"[DEBUG] Usuário {username} já existe")
            continue
        
        user = XtreamUser(
            username=username,
            is_active=True,
            max_connections=1,
        )
        user.set_password(password)
        db.session.add(user)
        created_count += 1
        print(f"[DEBUG] Usuário {username} criado")
    
    db.session.commit()
    print(f"[DEBUG] Total de usuários criados: {created_count}")


def _seed_youtube_channels():
    """Cria canais YouTube padrão se a tabela estiver vazia."""
    from backend.models import YouTubeChannel

    inspector = inspect(db.engine)
    if "youtube_channels" not in inspector.get_table_names():
        return

    if YouTubeChannel.query.first():
        return

    default_channels = [
        {"name": "Movie Central Português", "handle": "@MovieCentralPortugues1"},
        {"name": "Film+ BR", "handle": "@filmplusbr"},
        {"name": "Netmovies", "handle": "@netmovies"},
    ]
    for ch in default_channels:
        channel = YouTubeChannel(
            name=ch["name"],
            handle=ch["handle"],
            channel_url=f"https://www.youtube.com/{ch['handle']}/videos",
            is_active=True,
        )
        db.session.add(channel)
    db.session.commit()
    print(f"[DB] {len(default_channels)} canais YouTube seed criados")


def _init_app_state(app):
    db.init_app(app)
    with app.app_context():
        # Inicialização do banco (igual resoluta_pront)
        from backend.extensions import init_database
        init_database()
        # Also create tables for Flask-SQLAlchemy models (db.Model)
        # init_database() only covers the standalone Base metadata
        _create_flask_sqlalchemy_tables()
        _ensure_lightweight_schema_updates(app)

        # Seeds adicionais
        _seed_media_servers()
        _seed_jellyfin_servers()
        _seed_xtream_users()
        _seed_youtube_channels()


def _register_admin_routes(app):
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_xtream_bp)
    if admin_youtube_bp:
        app.register_blueprint(admin_youtube_bp)


def _register_client_routes(app):
    app.register_blueprint(client_bp)
    app.register_blueprint(xtream_bp)


def create_app(mode="full"):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret"),
        JWT_SECRET=os.getenv("JWT_SECRET", "dev-jwt-secret"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SERVER_SELECTION_STRATEGY=os.getenv("SERVER_SELECTION_STRATEGY", "priority_fallback"),
        VIDEO_TOKEN_TTL_SECONDS=int(os.getenv("VIDEO_TOKEN_TTL_SECONDS", "3600")),
        PANEL_PUBLIC_URL=os.getenv("PANEL_PUBLIC_URL", "").rstrip("/"),
        CLIENT_PUBLIC_URL=os.getenv("CLIENT_PUBLIC_URL", "http://localhost:5000").rstrip("/"),
        ENGINE_INTERNAL_URL=os.getenv("ENGINE_INTERNAL_URL", "http://go-engine:8080").rstrip("/"),
        STREAM_PUBLIC_URL=(os.getenv("ENGINE_PUBLIC_URL") or os.getenv("STREAM_PUBLIC_URL", "http://localhost:8080")).rstrip("/"),
        KODI_RESOLVER_URL=os.getenv("KODI_RESOLVER_URL", "http://kodi-resolver:8090").rstrip("/"),
    )
    _init_app_state(app)

    if mode not in {"admin", "client", "full"}:
        raise ValueError("mode must be 'admin', 'client', or 'full'")
    if mode in {"admin", "full"}:
        _register_admin_routes(app)
    if mode in {"client", "full"}:
        _register_client_routes(app)

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": f"panel-{mode}"}

    return app


app = None if os.getenv("TRIBBLE_SKIP_AUTO_APP") == "1" else create_app()
