import html
import re
import ssl
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from flask import current_app, request
from sqlalchemy import or_, func

from backend.extensions import db
from backend.models import JellyfinItem, Video
from backend.services.playlist_service import build_video_playback_url

REIDOSCANAIS_PROVIDERS = ("reidoscanais_api", "reidoscanais_sports_api")
RESOLVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_LIVE_SOURCE_CACHE = {}

LIVE_CATEGORIES = {
    "reidoscanais": {
        "category_id": "reidoscanais",
        "category_name": "ReidosCanais",
        "parent_id": 0,
        "providers": ("reidoscanais_api",),
    },
    "reidoscanais_sports": {
        "category_id": "reidoscanais_sports",
        "category_name": "ReidosCanais Esportes",
        "parent_id": 0,
        "providers": ("reidoscanais_sports_api",),
    },
}


def _public_base_url():
    stream_public_url = current_app.config.get("STREAM_PUBLIC_URL", "").rstrip("/")
    if stream_public_url:
        return stream_public_url
    return request.url_root.rstrip("/")


def _reidoscanais_query(category_id=None):
    query = Video.query.filter(Video.source_type == "embed").filter(Video.external_provider.in_(REIDOSCANAIS_PROVIDERS))
    category = LIVE_CATEGORIES.get(category_id or "")
    if category:
        query = query.filter(Video.external_provider.in_(category["providers"]))
    return query


def stream_url_for_video(video, client_id):
    if video.source_type == "embed":
        return video.source_url
    return build_video_playback_url(video.id, client_id)


def stream_url_for_video_id(video_id, client_id):
    video = Video.query.get(video_id)
    if not video:
        return None
    return stream_url_for_video(video, client_id)


def serialize_video(video, client_id):
    stream_url = stream_url_for_video(video, client_id)
    category_id = ""
    if video.category:
        category_id = _slugify_category(video.category)
    elif video.is_jellyfin:
        category_id = "jellyfin"
    else:
        category_id = "hls"
    return {
        "stream_id": video.id,
        "name": video.title,
        "stream_type": "movie",
        "stream_url": stream_url,
        "direct_source": stream_url,
        "container_extension": "m3u8",
        "category_id": category_id,
        "stream_icon": video.thumbnail_url or "",
    }


def _slugify_category(name):
    """Converte nome de categoria em slug para category_id."""
    import re
    import unicodedata
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "filmes"


def live_stream_url_for_video(video, username, password, extension="m3u8"):
    return f"{_public_base_url()}/live/{username}/{password}/{video.id}.{extension or 'm3u8'}"


def live_source_url_for_video_id(video_id):
    video = _reidoscanais_query().filter(Video.id == video_id).first()
    if not video:
        return None
    return resolve_live_source_url(video.source_url)


def _extract_m3u8_url(value, base_url):
    value = html.unescape(unquote(value or "")).strip()
    if not value:
        return None

    parsed = urlparse(value)
    query_m3u8 = parse_qs(parsed.query).get("m3u8")
    if query_m3u8:
        return urljoin(base_url, html.unescape(unquote(query_m3u8[0])))

    match = re.search(r"https?://[^\s\"'<>]+?\.m3u8[^\s\"'<>]*", value)
    if match:
        return html.unescape(unquote(match.group(0)))

    if ".m3u8" in value:
        return urljoin(base_url, value)
    return None


def resolve_live_source_url(source_url):
    if not source_url:
        return None
    if source_url in _LIVE_SOURCE_CACHE:
        return _LIVE_SOURCE_CACHE[source_url] or None

    direct = _extract_m3u8_url(source_url, source_url)
    if direct and _is_playable_hls_url(direct):
        _LIVE_SOURCE_CACHE[source_url] = direct
        return direct

    req = Request(source_url, headers=RESOLVER_HEADERS)
    try:
        with urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8", "ignore")
            final_url = response.url or source_url
    except URLError:
        return None

    candidates = []
    candidates.extend(re.findall(r"(?:src|data-src)=[\"']([^\"']+)", body, flags=re.IGNORECASE))
    candidates.extend(re.findall(r"https?://[^\s\"'<>]+?\.m3u8[^\s\"'<>]*", body))
    for candidate in candidates:
        resolved = _extract_m3u8_url(candidate, final_url)
        if resolved and _is_playable_hls_url(resolved):
            _LIVE_SOURCE_CACHE[source_url] = resolved
            return resolved
    _LIVE_SOURCE_CACHE[source_url] = ""
    return None


def _is_playable_hls_url(source_url):
    headers = dict(RESOLVER_HEADERS)
    headers["Accept"] = "*/*"
    req = Request(source_url, headers=headers)
    try:
        with closing(urlopen(req, timeout=5, context=ssl._create_unverified_context())) as response:
            if response.status < 200 or response.status >= 300:
                return False
            sample = response.read(256).decode("utf-8", "ignore")
    except URLError:
        return False
    return "#EXTM3U" in sample


def serialize_live_video(video, username, password, num=1):
    stream_url = live_stream_url_for_video(video, username, password)
    category_id = "reidoscanais_sports" if video.external_provider == "reidoscanais_sports_api" else "reidoscanais"
    return {
        "num": num,
        "name": video.title,
        "stream_type": "live",
        "stream_id": video.id,
        "stream_icon": "",
        "epg_channel_id": "",
        "added": str(int(video.created_at.timestamp())) if video.created_at else "",
        "category_id": category_id,
        "custom_sid": "",
        "tv_archive": 0,
        "direct_source": stream_url,
        "container_extension": "m3u8",
        "stream_url": stream_url,
    }


def get_live_categories():
    categories = []
    for category in LIVE_CATEGORIES.values():
        if _reidoscanais_query(category["category_id"]).first():
            categories.append(
                {
                    "category_id": category["category_id"],
                    "category_name": category["category_name"],
                    "parent_id": category["parent_id"],
                }
            )
    return categories


def get_live_streams(username, password, category_id=None):
    videos = _reidoscanais_query(category_id).order_by(Video.title).all()
    if not videos:
        return []

    source_urls = {video.source_url for video in videos if video.source_url}
    playable_sources = set()
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(resolve_live_source_url, source_url): source_url for source_url in source_urls}
        for future in as_completed(futures):
            source_url = futures[future]
            try:
                if future.result():
                    playable_sources.add(source_url)
            except Exception:
                _LIVE_SOURCE_CACHE[source_url] = ""

    playable_videos = [video for video in videos if video.source_url in playable_sources]
    return [serialize_live_video(video, username, password, index) for index, video in enumerate(playable_videos, start=1)]


def get_live_stream_info(stream_id, username, password):
    video = _reidoscanais_query().filter(Video.id == stream_id).first()
    if not video:
        return None
    return serialize_live_video(video, username, password)


def get_vod_categories():
    categories = [{"category_id": "hls", "category_name": "HLS", "parent_id": 0}]
    if Video.query.filter(or_(Video.source_type == "jellyfin", Video.external_provider == "jellyfin")).first():
        categories.append({"category_id": "jellyfin", "category_name": "Jellyfin", "parent_id": 0})

    # Categorias dinâmicas dos vídeos (YouTube e outros com category preenchida)
    rows = (
        db.session.query(Video.category)
        .filter(Video.category.isnot(None), Video.category != "")
        .filter(Video.external_provider.notin_(REIDOSCANAIS_PROVIDERS))
        .group_by(Video.category)
        .order_by(Video.category)
        .all()
    )
    for (cat_name,) in rows:
        cat_id = _slugify_category(cat_name)
        if cat_id not in {"hls", "jellyfin"}:
            categories.append({"category_id": cat_id, "category_name": cat_name, "parent_id": 0})

    return categories


def get_vod_streams(client_id, category_id=None):
    query = Video.query
    query = query.filter(or_(Video.external_provider.is_(None), Video.external_provider.notin_(REIDOSCANAIS_PROVIDERS)))
    if category_id == "jellyfin":
        query = query.filter(or_(Video.source_type == "jellyfin", Video.external_provider == "jellyfin"))
    elif category_id == "hls":
        query = query.filter(Video.source_type != "jellyfin")
        query = query.filter(or_(Video.external_provider.is_(None), Video.external_provider != "jellyfin"))
        query = query.filter(or_(Video.category.is_(None), Video.category == ""))
        query = query.filter(or_(Video.external_provider.is_(None), Video.external_provider != "youtube"))
    elif category_id:
        # Buscar por slug de categoria
        all_cats = (
            db.session.query(Video.category)
            .filter(Video.category.isnot(None), Video.category != "")
            .group_by(Video.category)
            .all()
        )
        matched = None
        for (cat_name,) in all_cats:
            if _slugify_category(cat_name) == category_id:
                matched = cat_name
                break
        if matched:
            query = query.filter(Video.category == matched)
        else:
            query = query.filter(Video.id < 0)  # nenhum resultado
    return [serialize_video(video, client_id) for video in query.order_by(Video.title).all()]


def get_vod_info(video_id, client_id):
    video = Video.query.get(video_id)
    if not video:
        return None
    if video.source_type == "embed" and video.external_provider in REIDOSCANAIS_PROVIDERS:
        return None
    info = serialize_video(video, client_id)
    if video.is_jellyfin:
        item = JellyfinItem.query.filter_by(
            jellyfin_server_id=video.jellyfin_server_id,
            jellyfin_item_id=video.jellyfin_item_id,
        ).first()
        info.update(
            {
                "category_id": "jellyfin",
                "provider": "jellyfin",
                "jellyfin_server_id": video.jellyfin_server_id,
                "jellyfin_item_id": video.jellyfin_item_id,
                "runtime_ticks": item.runtime_ticks if item else None,
                "image_tag": item.image_tag if item else None,
                "media_type": item.media_type if item else None,
            }
        )
    elif video.category:
        info["category_id"] = _slugify_category(video.category)
        info["category_name"] = video.category
    else:
        info["category_id"] = "hls"
    if video.thumbnail_url:
        info["stream_icon"] = video.thumbnail_url
    return {"info": info, "movie_data": info}
