import unittest

from flask import Flask

from backend.extensions import db
from backend.models import Video
from backend.services.kodi_m3u_service import import_playlist_content, parse_m3u


SAMPLE_M3U = """#EXTM3U
#EXTINF:-1 tvg-logo="https://img.example/logo.png" group-title="Esportes",Canal Um
https://stream.example/canal-um.m3u8

#EXTINF:-1 group-title="Filmes",Filme Dois
https://stream.example/filme-dois.m3u8
#EXTINF:-1 group-title="Invalido",Sem HTTP
plugin://plugin.video.foo/item
"""


class KodiM3UServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_parse_m3u_reads_extinf_metadata_and_skips_non_http_urls(self):
        items = parse_m3u(SAMPLE_M3U, default_category="Kodi")

        self.assertEqual(2, len(items))
        self.assertEqual("Canal Um", items[0].title)
        self.assertEqual("Esportes", items[0].category)
        self.assertEqual("https://img.example/logo.png", items[0].thumbnail_url)
        self.assertEqual("Filme Dois", items[1].title)
        self.assertEqual("Filmes", items[1].category)

    def test_import_playlist_content_creates_kodi_videos_and_skips_duplicates(self):
        stats = import_playlist_content(SAMPLE_M3U)
        videos = Video.query.order_by(Video.title).all()

        self.assertEqual({"created": 2, "updated": 0, "skipped": 0, "invalid": 0, "total": 2}, stats)
        self.assertEqual(2, len(videos))
        self.assertEqual("kodi_m3u", videos[0].external_provider)
        self.assertEqual("embed", videos[0].source_type)

        stats = import_playlist_content(SAMPLE_M3U)

        self.assertEqual(0, stats["created"])
        self.assertEqual(2, stats["skipped"])

    def test_import_playlist_content_overwrites_existing_video(self):
        db.session.add(
            Video(
                title="Titulo antigo",
                source_url="https://stream.example/canal-um.m3u8",
                source_type="embed",
                external_provider="embed",
            )
        )
        db.session.commit()

        stats = import_playlist_content(SAMPLE_M3U, overwrite=True)
        video = Video.query.filter_by(source_url="https://stream.example/canal-um.m3u8").one()

        self.assertEqual(1, stats["updated"])
        self.assertEqual("Canal Um", video.title)
        self.assertEqual("kodi_m3u", video.external_provider)
        self.assertEqual("Esportes", video.category)


if __name__ == "__main__":
    unittest.main()
