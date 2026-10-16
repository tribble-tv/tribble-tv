import json
import struct
import tempfile
import unittest
from pathlib import Path

from backend.services.torrent_index import Engine, SourceError, load_sources
from backend.services.torrent_index import magnet, text, trackers
from backend.services.torrent_index.sources import parse_source

H1 = "a" * 40
H2 = "b" * 40


class MagnetTest(unittest.TestCase):
    def test_parse_hex_and_base32(self):
        info = magnet.parse_magnet(f"magnet:?xt=urn:btih:{H1.upper()}&dn=Foo%20Bar&tr=udp%3A%2F%2Ft.test%3A80&xl=10")
        self.assertEqual(info["info_hash"], H1)
        self.assertEqual(info["name"], "Foo Bar")
        self.assertEqual(info["trackers"], ["udp://t.test:80"])
        self.assertEqual(info["size"], 10)
        b32 = "VKVKVKVKVKVKVKVKVKVKVKVKVKVKVKVK"  # 0xaa * 20
        self.assertEqual(magnet.normalize_info_hash(b32), "aa" * 20)

    def test_parse_rejects_invalid(self):
        self.assertIsNone(magnet.parse_magnet("http://x"))
        self.assertIsNone(magnet.parse_magnet("magnet:?xt=urn:btih:zzz"))
        self.assertIsNone(magnet.parse_magnet("javascript:alert(1)"))

    def test_build_roundtrip(self):
        uri = magnet.build_magnet(H1, "A B", ["udp://t.test:80"])
        self.assertEqual(magnet.parse_magnet(uri)["trackers"], ["udp://t.test:80"])
        with self.assertRaises(ValueError):
            magnet.build_magnet("nope")

    def test_find_magnets_unescapes_and_dedupes(self):
        page = f'<a href="magnet:?xt=urn:btih:{H1}&amp;dn=X">a</a> magnet:?xt=urn:btih:{H1} magnet:?xt=urn:btih:{H2}'
        found = magnet.find_magnets(page)
        self.assertEqual(len(found), 2)
        self.assertIn("&dn=X", found[0])


class TextTest(unittest.TestCase):
    def test_normalize_and_score(self):
        self.assertEqual(text.normalize("Ação & Aventura!"), "acao aventura")
        self.assertEqual(text.match_score("matrix 1999", "Matrix.1999.1080p"), 1.0)
        self.assertEqual(text.match_score("matrix reloaded", "Matrix 1999"), 0.5)
        self.assertEqual(text.match_score("", "x"), 0.0)

    def test_parsers(self):
        self.assertEqual(text.parse_year("Filme 2019 720p"), "2019")
        self.assertEqual(text.parse_quality("Filme.1080P.WEB"), "1080p")
        self.assertEqual(text.parse_size_bytes("1,5 GB"), int(1.5 * 1024**3))
        self.assertEqual(text.format_size(1024**2), "1.0 MB")
        self.assertEqual(text.clean_title("<b>A</b>  B"), "A B")


class _FakeSock:
    """Tracker UDP falso: responde connect e scrape."""

    def __init__(self, stats, error=False):
        self.stats, self.error, self.last, self.closed = stats, error, None, False

    def settimeout(self, t):
        pass

    def sendto(self, data, addr):
        self.last = data

    def close(self):
        self.closed = True

    def recvfrom(self, n):
        action, tid = struct.unpack(">II", self.last[8:16])
        if self.error:
            return struct.pack(">II", 3, tid) + b"boom", None
        if action == 0:
            return struct.pack(">IIQ", 0, tid, 99), None
        body = b"".join(struct.pack(">III", *s) for s in self.stats)
        return struct.pack(">II", 2, tid) + body, None


class TrackerTest(unittest.TestCase):
    def test_scrape(self):
        sock = _FakeSock([(5, 7, 2), (0, 0, 1)])
        out = trackers.scrape("udp://t.test:80/announce", [H1, H2], socket_factory=lambda *a: sock)
        self.assertEqual(out[H1], {"seeds": 5, "completed": 7, "leech": 2})
        self.assertEqual(out[H2]["leech"], 1)
        self.assertTrue(sock.closed)

    def test_scrape_error_and_bad_url(self):
        with self.assertRaises(trackers.TrackerError):
            trackers.scrape("udp://t.test:80", [H1], socket_factory=lambda *a: _FakeSock([], error=True))
        with self.assertRaises(trackers.TrackerError):
            trackers.parse_tracker_url("http://t.test:80")

    def test_scrape_many_ignores_failures_and_keeps_best(self):
        socks = iter([_FakeSock([], error=True), _FakeSock([(3, 0, 0)]), _FakeSock([(9, 0, 1)])])
        out = trackers.scrape_many(["udp://a:1", "udp://b:1", "udp://c:1"], [H1],
                                   socket_factory=lambda *a: next(socks))
        self.assertEqual(out[H1]["seeds"], 9)


class SourcesTest(unittest.TestCase):
    HTML = {"id": "s1", "search_url": "https://x.test/?q={query}",
            "item_pattern": r'<a href="(?P<url>[^"]+)">(?P<title>[^<]+)</a>'}

    def test_valid_sources(self):
        self.assertEqual(parse_source(self.HTML).type, "html")
        js = {"id": "j", "type": "json", "search_url": "https://x.test/{query}",
              "fields": {"title": "n", "info_hash": "h"}}
        self.assertEqual(parse_source(js).type, "json")

    def test_invalid_sources(self):
        bad = [
            {**self.HTML, "id": "../x"},
            {**self.HTML, "search_url": "https://x.test/"},
            {**self.HTML, "search_url": "file:///etc/{query}"},
            {**self.HTML, "item_pattern": "(?P<title>x"},
            {**self.HTML, "item_pattern": "(?P<title>x)"},
            {**self.HTML, "item_pattern": "(?P<title>x)(?P<url>y)(?P<evil>z)"},
            {**self.HTML, "type": "xml"},
            {"id": "j", "type": "json", "search_url": "https://x/{query}", "fields": {"title": "n"}},
        ]
        for raw in bad:
            with self.assertRaises(SourceError, msg=str(raw)):
                parse_source(raw)

    def test_load_sources(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            self.assertEqual(load_sources(path), [])
            path.write_text(json.dumps({"sources": [self.HTML, {**self.HTML, "id": "off", "enabled": False}]}))
            self.assertEqual([s.id for s in load_sources(path)], ["s1"])
            path.write_text(json.dumps({"sources": [self.HTML, self.HTML]}))
            with self.assertRaises(SourceError):
                load_sources(path)
            path.write_text("{nao json")
            with self.assertRaises(SourceError):
                load_sources(path)


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.html = parse_source({
            "id": "h", "search_url": "https://h.test/?q={query}",
            "item_pattern": r'<a href="(?P<url>[^"]+)">(?P<title>[^<]+)</a>',
        })
        self.json = parse_source({
            "id": "j", "type": "json", "search_url": "https://j.test/?q={query}",
            "results_path": "data", "fields": {"title": "n", "info_hash": "h", "seeds": "s"},
        })
        self.pages = {
            "https://h.test/?q=matrix": '<a href="/t/1">Matrix 1999</a><a href="/t/2">Outro Filme</a>',
            "https://h.test/t/1": f"x magnet:?xt=urn:btih:{H1}&tr=udp%3A%2F%2Ft.test%3A80 y",
            "https://j.test/?q=matrix": json.dumps({"data": [
                {"n": "Matrix 1999 1080p", "h": H1, "s": "4"},
                {"n": "Matrix Reloaded", "h": H2, "s": 2},
                {"n": "Matrix Sem Hash", "h": "bad", "s": 1},
            ]}),
        }
        self.calls = []

    def fetch(self, url, headers, timeout):
        self.calls.append(url)
        return self.pages[url]

    def test_html_source_filters_and_resolves_detail(self):
        eng = Engine([self.html], fetch=self.fetch, scrape=None)
        res = eng.search_source("h", "matrix")
        self.assertEqual([r["info_hash"] for r in res], [H1])
        self.assertEqual(res[0]["year"], "1999")
        self.assertNotIn("https://h.test/t/2", self.calls)

    def test_search_merges_dedupes_enriches_and_ranks(self):
        seen = []

        def scrape(trk, hashes):
            seen.append((trk, hashes))
            return {H1: {"seeds": 50, "completed": 0, "leech": 3}}

        eng = Engine([self.html, self.json], fetch=self.fetch, scrape=scrape)
        out = eng.search("matrix")
        by_hash = {r["info_hash"]: r for r in out["results"]}
        self.assertEqual(set(by_hash), {H1, H2})
        self.assertEqual(by_hash[H1]["seeds"], 4)  # fonte json ja trazia seeds
        self.assertEqual(by_hash[H2]["seeds"], 2)
        self.assertEqual(seen, [])  # nada a enriquecer
        self.assertNotIn("trackers", out["results"][0])
        self.assertEqual(out["errors"], {})

    def test_enrich_missing_seeds_via_udp_tracker(self):
        eng = Engine([self.html], fetch=self.fetch,
                     scrape=lambda trk, hashes: {H1: {"seeds": 50, "completed": 0, "leech": 3}})
        out = eng.search("matrix")
        self.assertEqual((out["results"][0]["seeds"], out["results"][0]["leech"]), (50, 3))

    def test_source_errors_are_collected(self):
        from backend.services.torrent_index import EngineError

        def failing(url, headers, timeout):
            raise EngineError("fora do ar")

        eng = Engine([self.html], fetch=failing, scrape=None)
        out = eng.search("matrix")
        self.assertEqual(out["results"], [])
        self.assertIn("h", out["errors"])
        with self.assertRaises(EngineError):
            eng.search_source("nope", "x")
        with self.assertRaises(EngineError):
            eng.search_source("h", "  ")


if __name__ == "__main__":
    unittest.main()
