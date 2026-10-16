import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["TRIBBLE_SKIP_AUTO_APP"] = "1"

from backend.app import create_app
from backend.services import torrent_indexer_service as svc

H1 = "a" * 40
SOURCES = {"sources": [{
    "id": "api", "name": "API", "type": "json", "search_url": "https://api.test/?q={query}",
    "results_path": "items", "fields": {"title": "n", "info_hash": "h", "seeds": "s"},
}]}


class _SourcesFileCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sources.json"
        self.path.write_text(json.dumps(SOURCES))
        self.env = mock.patch.dict(os.environ, {
            "TORRENT_SOURCES_FILE": str(self.path),
            "TORRENT_INDEXER_TRACKER_SCRAPE": "0",
            "DATABASE_URL": "sqlite://",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


def _fake_fetch(url, headers=None, timeout=15.0):
    return json.dumps({"items": [{"n": "Matrix 1999", "h": H1, "s": 7}]})


class TorrentIndexerServiceTest(_SourcesFileCase):
    def test_configured_and_listing(self):
        self.assertTrue(svc.is_configured())
        self.assertEqual(svc.indexers(), {"api": "API"})

    def test_not_configured_without_file(self):
        self.path.unlink()
        self.assertFalse(svc.is_configured())
        self.assertFalse(svc.health_check())

    def test_invalid_config_is_reported(self):
        self.path.write_text("{nao json")
        self.assertFalse(svc.is_configured())
        with self.assertRaises(svc.TorrentIndexerError):
            svc.search_all("matrix")

    def test_search_and_search_all(self):
        with mock.patch("backend.services.torrent_indexer_service.Engine") as engine_cls:
            engine = engine_cls.return_value
            engine.search_source.return_value = [{"title": "A"}]
            engine.search.return_value = {"results": [], "errors": {}}
            self.assertEqual(svc.search("matrix", "api", 500), [{"title": "A"}])
            engine.search_source.assert_called_once_with("api", "matrix", svc.MAX_LIMIT)
            self.assertEqual(svc.search_all("matrix", 5), {"results": [], "errors": {}})

    def test_search_requires_query_and_known_source(self):
        with self.assertRaises(svc.TorrentIndexerError):
            svc.search_all("  ")
        with self.assertRaises(svc.TorrentIndexerError):
            svc.search("x", "../admin")
        with self.assertRaises(svc.TorrentIndexerError):
            svc.search("  ", "api")


class TorrentIndexerRoutesTest(_SourcesFileCase):
    def setUp(self):
        super().setUp()
        os.environ.setdefault("SECRET_KEY", "test-secret")
        os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
        self.app = create_app(mode="admin")
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def test_search_requires_query(self):
        self.assertEqual(self.client.get("/admin/torrent-indexer/search").status_code, 400)

    def test_search_returns_json(self):
        with mock.patch.object(svc, "search_all", return_value={"results": [], "errors": {}}):
            resp = self.client.get("/admin/torrent-indexer/search?q=matrix")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"results": [], "errors": {}})

    def test_end_to_end_with_fake_http(self):
        with mock.patch("backend.services.torrent_index.engine.Engine._get",
                        lambda self, url, source: _fake_fetch(url)):
            resp = self.client.get("/admin/torrent-indexer/search?q=matrix&indexer=api")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["results"][0]["info_hash"], H1)

    def test_unknown_indexer_is_bad_gateway(self):
        resp = self.client.get("/admin/torrent-indexer/search?q=x&indexer=nope")
        self.assertEqual(resp.status_code, 502)

    def test_unconfigured_is_503(self):
        self.path.unlink()
        self.assertEqual(self.client.get("/admin/torrent-indexer/search?q=x").status_code, 503)

    def test_page_renders_and_form_prefill_rejects_non_magnet(self):
        self.assertEqual(self.client.get("/admin/torrent-indexer").status_code, 200)
        ok = self.client.get("/admin/videos/torrent/create?title=T&magnet=magnet:?xt=urn:btih:abc")
        self.assertIn(b"magnet:?xt=urn:btih:abc", ok.data)
        bad = self.client.get("/admin/videos/torrent/create?title=T&magnet=javascript:alert(1)")
        self.assertNotIn(b"javascript:alert", bad.data)


if __name__ == "__main__":
    unittest.main()
