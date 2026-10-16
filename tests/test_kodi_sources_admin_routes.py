import os
import tempfile
import unittest

os.environ["TRIBBLE_SKIP_AUTO_APP"] = "1"

from backend.app import create_app
from backend.extensions import db
from backend.models import KodiSource, Video
from backend.services import kodi_addon_service


class KodiSourcesAdminRoutesTest(unittest.TestCase):
    def setUp(self):
        db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_file.close()
        self.db_path = db_file.name
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ.setdefault("SECRET_KEY", "test-secret")
        os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
        os.environ["KODI_RESOLVER_URL"] = "http://resolver.test"
        self.app = create_app(mode="admin")
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        self.original_resolve = kodi_addon_service.resolve_source
        kodi_addon_service.resolve_source = self.fake_resolve

    def tearDown(self):
        kodi_addon_service.resolve_source = self.original_resolve
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def fake_resolve(self, *args, **kwargs):
        return {
            "status": "success",
            "items": [
                {
                    "title": "Canal Resolvido",
                    "stream_url": "https://stream.example/canal.m3u8",
                    "category": "Kodi",
                }
            ],
        }

    def test_create_addon_source_saves_and_syncs(self):
        response = self.client.post(
            "/admin/kodi-sources/create",
            data={
                "name": "Fonte Addon",
                "source_kind": "addon",
                "source_url": "https://repo.example/repository.zip",
                "addon_id": "plugin.video.demo",
                "entry_path": "plugin://plugin.video.demo/",
                "default_category": "Kodi",
            },
            follow_redirects=False,
        )

        self.assertEqual(302, response.status_code)
        with self.app.app_context():
            source = KodiSource.query.one()
            self.assertEqual(KodiSource.KIND_ADDON, source.source_kind)
            self.assertEqual("https://repo.example/repository.zip", source.playlist_url)
            self.assertEqual("plugin.video.demo", source.addon_id)
            self.assertEqual("success", source.last_status)
            self.assertEqual(1, source.last_stats["created"])
            video = Video.query.one()
            self.assertEqual("Canal Resolvido", video.title)
            self.assertEqual("kodi_addon", video.external_provider)

    def test_sync_toggle_edit_and_delete_source(self):
        with self.app.app_context():
            source = KodiSource(
                name="Fonte",
                playlist_url="https://repo.example/repository.zip",
                source_url="https://repo.example/repository.zip",
                source_kind=KodiSource.KIND_ADDON,
                addon_id="plugin.video.demo",
                is_active=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        self.assertEqual(302, self.client.post(f"/admin/kodi-sources/{source_id}/sync").status_code)
        with self.app.app_context():
            self.assertEqual("success", KodiSource.query.get(source_id).last_status)

        self.assertEqual(302, self.client.post(f"/admin/kodi-sources/{source_id}/toggle").status_code)
        with self.app.app_context():
            self.assertFalse(KodiSource.query.get(source_id).is_active)

        self.assertEqual(
            302,
            self.client.post(
                f"/admin/kodi-sources/{source_id}/edit",
                data={
                    "name": "Fonte Editada",
                    "source_kind": "addon",
                    "source_url": "https://repo.example/repository2.zip",
                    "addon_id": "plugin.video.demo2",
                    "default_category": "Filmes",
                    "is_active": "on",
                },
            ).status_code,
        )
        with self.app.app_context():
            source = KodiSource.query.get(source_id)
            self.assertEqual("Fonte Editada", source.name)
            self.assertEqual("plugin.video.demo2", source.addon_id)
            self.assertTrue(source.is_active)

        self.assertEqual(302, self.client.post(f"/admin/kodi-sources/{source_id}/delete").status_code)
        with self.app.app_context():
            self.assertEqual(0, KodiSource.query.count())


if __name__ == "__main__":
    unittest.main()
