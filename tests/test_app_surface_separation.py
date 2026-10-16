import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy.engine import make_url

os.environ["TRIBBLE_SKIP_AUTO_APP"] = "1"

from backend.app import create_app
from backend.database import DEFAULT_DATABASE_URL
from backend.extensions import db


class AppSurfaceSeparationTest(unittest.TestCase):
    def test_default_database_url_uses_project_database_file(self):
        database_path = Path(make_url(DEFAULT_DATABASE_URL).database)
        expected_path = Path(__file__).resolve().parent.parent / "tribble_tv.db"

        self.assertEqual(database_path, expected_path)

    def _make_app(self, mode):
        db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_file.close()
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
        os.environ.setdefault("SECRET_KEY", "test-secret")
        os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
        os.environ["CLIENT_PUBLIC_URL"] = "http://localhost:5000"
        try:
            app = create_app(mode=mode)
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url
        app.config.update(TESTING=True)
        self.addCleanup(self._cleanup_app, app, db_file.name)
        return app

    def _cleanup_app(self, app, db_path):
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_client_app_exposes_public_surface_only(self):
        client = self._make_app("client").test_client()

        self.assertEqual(client.get("/").status_code, 302)
        self.assertEqual(client.get("/client/login").status_code, 200)
        self.assertEqual(client.get("/client/").status_code, 302)
        self.assertEqual(client.get("/client/api/videos").status_code, 401)
        self.assertEqual(client.get("/playlist.m3u").status_code, 302)
        self.assertEqual(client.get("/player_api.php").status_code, 200)
        self.assertEqual(client.get("/admin/media-servers").status_code, 404)

    def test_admin_app_exposes_admin_surface_only(self):
        client = self._make_app("admin").test_client()

        self.assertEqual(client.get("/admin/").status_code, 302)
        self.assertEqual(client.get("/admin/media-servers").status_code, 200)
        self.assertEqual(client.get("/client/").status_code, 404)
        self.assertEqual(client.get("/playlist.m3u").status_code, 404)
        self.assertEqual(client.get("/player_api.php").status_code, 404)


if __name__ == "__main__":
    unittest.main()
