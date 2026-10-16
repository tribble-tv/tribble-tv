import unittest

from flask import Flask

from backend.extensions import db
from backend.models import KodiSource, Video
from backend.services import kodi_addon_service
from backend.services.kodi_addon_service import import_resolved_items, sync_source


class KodiAddonServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            KODI_RESOLVER_URL="http://resolver.test",
        )
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.source = KodiSource(
            name="Addon",
            playlist_url="https://repo.example/repository.zip",
            source_url="https://repo.example/repository.zip",
            source_kind=KodiSource.KIND_ADDON,
            addon_id="plugin.video.demo",
            default_category="Kodi",
            is_active=True,
        )
        db.session.add(self.source)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_import_resolved_items_creates_videos_and_skips_plugin_urls(self):
        stats = import_resolved_items(
            [
                {
                    "title": "Filme Um",
                    "stream_url": "https://stream.example/filme-um.m3u8",
                    "category": "Filmes",
                    "thumbnail_url": "https://img.example/poster.jpg",
                },
                {"title": "Plugin cru", "stream_url": "plugin://plugin.video.demo/item"},
                {"title": "Duplicado", "stream_url": "https://stream.example/filme-um.m3u8"},
            ],
            self.source,
        )

        self.assertEqual({"created": 1, "updated": 0, "skipped": 1, "invalid": 1, "total": 3}, stats)
        video = Video.query.one()
        self.assertEqual("Filme Um", video.title)
        self.assertEqual("embed", video.source_type)
        self.assertEqual("kodi_addon", video.external_provider)
        self.assertEqual("Filmes", video.category)
        self.assertEqual("https://img.example/poster.jpg", video.thumbnail_url)

    def test_import_resolved_items_overwrites_existing_video(self):
        db.session.add(
            Video(
                title="Antigo",
                source_url="https://stream.example/filme-um.m3u8",
                source_type="embed",
                external_provider="embed",
            )
        )
        db.session.commit()

        stats = import_resolved_items(
            [{"title": "Novo", "stream_url": "https://stream.example/filme-um.m3u8", "category": "Aventura"}],
            self.source,
            overwrite=True,
        )

        self.assertEqual(1, stats["updated"])
        video = Video.query.one()
        self.assertEqual("Novo", video.title)
        self.assertEqual("kodi_addon", video.external_provider)
        self.assertEqual("Aventura", video.category)

    def test_sync_source_marks_needs_config_without_importing(self):
        original = kodi_addon_service.resolve_source
        kodi_addon_service.resolve_source = lambda *args, **kwargs: {
            "status": "needs_config",
            "error": "Login pendente",
            "items": [],
        }
        try:
            stats = sync_source(self.source)
        finally:
            kodi_addon_service.resolve_source = original

        self.assertEqual("needs_config", self.source.last_status)
        self.assertEqual("Login pendente", self.source.last_error)
        self.assertEqual(0, stats["total"])
        self.assertEqual(0, Video.query.count())

    def test_sync_source_records_resolver_errors(self):
        original = kodi_addon_service.resolve_source

        def fail(*args, **kwargs):
            raise kodi_addon_service.KodiAddonError("Resolver offline")

        kodi_addon_service.resolve_source = fail
        try:
            with self.assertRaises(kodi_addon_service.KodiAddonError):
                sync_source(self.source)
        finally:
            kodi_addon_service.resolve_source = original

        self.assertEqual("error", self.source.last_status)
        self.assertEqual("Resolver offline", self.source.last_error)


if __name__ == "__main__":
    unittest.main()
