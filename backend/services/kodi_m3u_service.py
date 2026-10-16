import html
import re
import ssl
from dataclasses import dataclass
from datetime import datetime
from contextlib import closing
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from backend.extensions import db
from backend.models import Video

PROVIDER = "kodi_m3u"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36 Kodi"
    ),
    "Accept": "application/x-mpegURL,application/vnd.apple.mpegurl,text/plain,*/*",
}


class KodiM3UError(RuntimeError):
    pass


@dataclass
class M3UItem:
    title: str
    stream_url: str
    category: str = ""
    thumbnail_url: str = ""


def fetch_playlist(url, timeout=20):
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise KodiM3UError("URL da playlist deve ser HTTP ou HTTPS.")

    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", "ignore")
    except HTTPError as exc:
        raise KodiM3UError(f"Playlist retornou HTTP {exc.code}.") from exc
    except URLError as exc:
        raise KodiM3UError(f"Falha ao acessar playlist: {exc.reason}") from exc


def parse_m3u(content, default_category=""):
    items = []
    pending_meta = {}

    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#EXTINF"):
            pending_meta = _parse_extinf(line)
            continue

        if line.startswith("#"):
            continue

        stream_url = html.unescape(line)
        if not _is_http_url(stream_url):
            pending_meta = {}
            continue

        title = (pending_meta.get("title") or stream_url.rsplit("/", 1)[-1]).strip()
        category = (pending_meta.get("group-title") or default_category or "").strip()
        thumb = (pending_meta.get("tvg-logo") or "").strip()
        items.append(M3UItem(title=title, stream_url=stream_url, category=category, thumbnail_url=thumb))
        pending_meta = {}

    return items


def import_playlist_content(content, default_category="", overwrite=False, validate_hls=False):
    items = parse_m3u(content, default_category=default_category)
    stats = {"created": 0, "updated": 0, "skipped": 0, "invalid": 0, "total": len(items)}
    seen_urls = set()

    for item in items:
        stream_url = item.stream_url.strip()
        if stream_url in seen_urls:
            stats["skipped"] += 1
            continue
        seen_urls.add(stream_url)

        if not _is_supported_stream(stream_url, validate_hls=validate_hls):
            stats["invalid"] += 1
            continue

        existing = Video.query.filter_by(source_url=stream_url).first()
        if existing:
            if overwrite:
                existing.title = item.title
                existing.source_type = "embed"
                existing.external_provider = PROVIDER
                existing.category = item.category or None
                existing.thumbnail_url = item.thumbnail_url or None
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
            continue

        db.session.add(
            Video(
                title=item.title,
                source_url=stream_url,
                source_type="embed",
                external_provider=PROVIDER,
                category=item.category or None,
                thumbnail_url=item.thumbnail_url or None,
            )
        )
        stats["created"] += 1

    db.session.commit()
    return stats


def sync_source(source, overwrite=False, validate_hls=False):
    try:
        content = fetch_playlist(source.playlist_url)
        stats = import_playlist_content(
            content,
            default_category=source.default_category or "",
            overwrite=overwrite,
            validate_hls=validate_hls,
        )
        source.last_status = "success"
        source.last_error = None
        source.last_stats = stats
        source.last_synced_at = datetime.utcnow()
        db.session.commit()
        return stats
    except KodiM3UError as exc:
        source.last_status = "error"
        source.last_error = str(exc)
        source.last_stats = None
        source.last_synced_at = datetime.utcnow()
        db.session.commit()
        raise


def _parse_extinf(line):
    meta = {}
    for key, value in re.findall(r'([A-Za-z0-9_-]+)="([^"]*)"', line):
        meta[key.lower()] = html.unescape(value.strip())

    _, _, title = line.partition(",")
    meta["title"] = html.unescape(title.strip()) if title else ""
    return meta


def _is_http_url(value):
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_supported_stream(stream_url, validate_hls=False):
    if not _is_http_url(stream_url):
        return False
    path = urlparse(stream_url).path.lower()
    if path.endswith(".m3u8"):
        return not validate_hls or _is_playable_hls_url(stream_url)
    return not validate_hls


def _is_playable_hls_url(stream_url):
    req = Request(stream_url, headers={**HEADERS, "Accept": "*/*"})
    try:
        with closing(urlopen(req, timeout=5, context=ssl._create_unverified_context())) as response:
            if response.status < 200 or response.status >= 300:
                return False
            sample = response.read(256).decode("utf-8", "ignore")
    except URLError:
        return False
    return "#EXTM3U" in sample
