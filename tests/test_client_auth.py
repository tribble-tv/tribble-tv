import os
import tempfile
import unittest

os.environ["TRIBBLE_SKIP_AUTO_APP"] = "1"

from backend.app import create_app
from backend.extensions import db
from backend.models import Video, WatchProgress, XtreamUser


class ClientAuthTest(unittest.TestCase):
    def setUp(self):
        db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_file.close()
        self.db_path = db_file.name
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ.setdefault("SECRET_KEY", "test-secret")
        os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
        os.environ["CLIENT_PUBLIC_URL"] = "http://localhost:5000"
        self.app = create_app(mode="client")
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

        with self.app.app_context():
            user = XtreamUser(username="client1", is_active=True, max_connections=1)
            user.set_password("secret123")
            inactive = XtreamUser(username="inactive", is_active=False, max_connections=1)
            inactive.set_password("secret123")
            user2 = XtreamUser(username="client2", is_active=True, max_connections=1)
            user2.set_password("secret456")
            db.session.add_all([user, inactive, user2])
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def login(self, username="client1", password="secret123", next_url="/client/"):
        return self.client.post(
            "/client/login",
            data={"username": username, "password": password, "next": next_url},
            follow_redirects=False,
        )

    def create_video(self, title="Movie One", category="Filmes"):
        with self.app.app_context():
            video = Video(
                title=title,
                source_url="http://media.local/video.m3u8",
                source_type="hls",
                category=category,
            )
            db.session.add(video)
            db.session.commit()
            return video.id

    def test_client_login_unlocks_catalog(self):
        self.assertEqual(self.client.get("/client/").status_code, 302)

        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/client/")

        self.assertEqual(self.client.get("/client/").status_code, 200)

    def test_invalid_login_stays_on_login(self):
        response = self.login(password="wrong")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Usuario ou senha invalidos", response.data)
        self.assertEqual(self.client.get("/client/").status_code, 302)

    def test_inactive_user_cannot_login(self):
        response = self.login(username="inactive")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Usuario ou senha invalidos", response.data)

    def test_logout_blocks_client_again(self):
        self.login()
        self.assertEqual(self.client.get("/client/").status_code, 200)

        response = self.client.get("/client/logout", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/client/login", response.headers["Location"])
        self.assertEqual(self.client.get("/client/").status_code, 302)

    def test_client_apis_require_login(self):
        self.assertEqual(self.client.get("/client/api/videos").status_code, 401)
        self.assertEqual(self.client.get("/client/api/series").status_code, 401)
        self.assertEqual(self.client.get("/client/series/demo/episodes").status_code, 401)

        self.login()

        self.assertEqual(self.client.get("/client/api/videos").status_code, 200)
        self.assertEqual(self.client.get("/client/api/series").status_code, 200)

    def test_client_series_groups_megaembed_episode_titles(self):
        with self.app.app_context():
            db.session.add_all([
                Video(
                    title="Demo Show T01E01 - Piloto",
                    source_url="https://mgeb.top/embed/123/1/1",
                    source_type="embed",
                    external_provider="megaembed",
                    category="Series",
                ),
                Video(
                    title="Demo Show T01E02 - Segundo",
                    source_url="https://mgeb.top/embed/123/1/2",
                    source_type="embed",
                    external_provider="megaembed",
                    category="Series",
                ),
                Video(
                    title="Demo Show T01E03",
                    source_url="https://mgeb.top/embed/123/1/3",
                    source_type="embed",
                    external_provider="megaembed",
                    category="Series",
                ),
                Video(
                    title="Demo Show T02E01 - Retorno",
                    source_url="https://mgeb.top/embed/123/2/1",
                    source_type="embed",
                    external_provider="megaembed",
                    category="Series",
                ),
            ])
            db.session.commit()

        self.login()

        series_response = self.client.get("/client/api/series")
        self.assertEqual(series_response.status_code, 200)
        series_payload = series_response.get_json()
        self.assertEqual(series_payload["total"], 1)
        self.assertEqual(series_payload["series"][0]["slug"], "demo-show")
        self.assertEqual(series_payload["series"][0]["season_count"], 2)
        self.assertEqual(series_payload["series"][0]["episode_count"], 4)

        episodes_response = self.client.get("/client/series/demo-show/episodes")
        self.assertEqual(episodes_response.status_code, 200)
        episodes_payload = episodes_response.get_json()
        self.assertEqual(episodes_payload["title"], "Demo Show")
        self.assertEqual(sorted(episodes_payload["seasons"].keys()), ["1", "2"])
        self.assertEqual(
            [episode["episode"] for episode in episodes_payload["seasons"]["1"]],
            [1, 2, 3],
        )
        self.assertEqual(
            [episode["episode"] for episode in episodes_payload["seasons"]["2"]],
            [1],
        )

    def test_watch_progress_requires_login(self):
        video_id = self.create_video()

        self.assertEqual(self.client.get(f"/client/api/videos/{video_id}/progress").status_code, 401)
        response = self.client.post(
            f"/client/api/videos/{video_id}/progress",
            json={"position_seconds": 10, "duration_seconds": 100},
        )
        self.assertEqual(response.status_code, 401)

    def test_watch_progress_create_update_and_get(self):
        video_id = self.create_video()
        self.login()

        response = self.client.post(
            f"/client/api/videos/{video_id}/progress",
            json={"position_seconds": 60, "duration_seconds": 300},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["position_seconds"], 60.0)
        self.assertEqual(payload["duration_seconds"], 300.0)
        self.assertEqual(payload["progress_percent"], 20.0)
        self.assertFalse(payload["completed"])

        response = self.client.post(
            f"/client/api/videos/{video_id}/progress",
            json={"position_seconds": 280, "duration_seconds": 300},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["completed"])
        self.assertEqual(payload["progress_percent"], 100.0)

        with self.app.app_context():
            self.assertEqual(WatchProgress.query.filter_by(video_id=video_id).count(), 1)

        response = self.client.get(f"/client/api/videos/{video_id}/progress")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["position_seconds"], 280.0)
        self.assertTrue(payload["completed"])

    def test_watch_progress_is_isolated_by_client_user(self):
        video_id = self.create_video()
        self.login()
        self.client.post(
            f"/client/api/videos/{video_id}/progress",
            json={"position_seconds": 40, "duration_seconds": 100},
        )
        self.client.get("/client/logout")

        self.login(username="client2", password="secret456")
        response = self.client.get(f"/client/api/videos/{video_id}/progress")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["position_seconds"], 0.0)
        self.assertEqual(payload["progress_percent"], 0.0)
        self.assertFalse(payload["completed"])

    def test_client_lists_include_watch_progress(self):
        movie_id = self.create_video(title="Movie Progress", category="Filmes")
        episode_id = self.create_video(title="Demo Show T01E01 - Piloto", category="Series")
        self.login()
        self.client.post(
            f"/client/api/videos/{movie_id}/progress",
            json={"position_seconds": 25, "duration_seconds": 100},
        )
        self.client.post(
            f"/client/api/videos/{episode_id}/progress",
            json={"position_seconds": 50, "duration_seconds": 100},
        )

        videos_response = self.client.get("/client/api/videos?category=Filmes")
        self.assertEqual(videos_response.status_code, 200)
        videos_payload = videos_response.get_json()
        movie_payload = next(video for video in videos_payload["videos"] if video["id"] == movie_id)
        self.assertEqual(movie_payload["progress_percent"], 25.0)
        self.assertFalse(movie_payload["completed"])

        series_response = self.client.get("/client/api/series")
        self.assertEqual(series_response.status_code, 200)
        series_payload = series_response.get_json()["series"][0]
        self.assertEqual(series_payload["progress_percent"], 50.0)
        self.assertEqual(series_payload["completed_episodes"], 0)

        episodes_response = self.client.get("/client/series/demo-show/episodes")
        self.assertEqual(episodes_response.status_code, 200)
        episode_payload = episodes_response.get_json()["seasons"]["1"][0]
        self.assertEqual(episode_payload["progress_percent"], 50.0)
        self.assertFalse(episode_payload["completed"])

    def test_playlist_requires_session_or_credentials(self):
        self.assertEqual(self.client.get("/playlist.m3u").status_code, 302)
        self.assertEqual(self.client.get("/playlist.m3u?username=client1&password=bad").status_code, 401)
        self.assertEqual(self.client.get("/playlist.m3u?username=client1&password=secret123").status_code, 200)

        self.login()

        self.assertEqual(self.client.get("/playlist.m3u").status_code, 200)


if __name__ == "__main__":
    unittest.main()
