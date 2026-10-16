import json
import os
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.extensions import db
from backend.models import Video

DEFAULT_DUBBED_DOMAIN = os.getenv("MEGAEMBED_DUBBED_DOMAIN", "https://mgeb.top").rstrip("/")
DEFAULT_SUBTITLED_DOMAIN = os.getenv("MEGAEMBED_SUBTITLED_DOMAIN", "https://nhdapi.com").rstrip("/")
PUBLIC_SITE_URL = os.getenv("MEGAEMBED_PUBLIC_SITE_URL", "https://megaembed.com").rstrip("/")
TMDB_API_BASE_URL = os.getenv("TMDB_API_BASE_URL", "https://api.themoviedb.org/3").rstrip("/")
TMDB_IMAGE_BASE_URL = os.getenv("TMDB_IMAGE_BASE_URL", "https://image.tmdb.org/t/p/w500").rstrip("/")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN", "").strip()
TMDB_CACHE_PATH = os.getenv("TMDB_CACHE_PATH", "/data/tmdb_cache.json")
TMDB_CACHE_TTL_SECONDS = int(os.getenv("TMDB_CACHE_TTL_SECONDS", str(30 * 24 * 60 * 60)))
TMDB_CACHE_VERSION = 1
_TMDB_CACHE_LOCK = threading.Lock()
_TMDB_CACHE = None

API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": f"{PUBLIC_SITE_URL}/",
    "Origin": PUBLIC_SITE_URL,
}
TMDB_HEADERS = {
    "User-Agent": API_HEADERS["User-Agent"],
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}
if TMDB_BEARER_TOKEN:
    TMDB_HEADERS["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"

MEDIA_TYPES = {"movie", "series"}
ID_TYPES = {"tmdb", "imdb"}
AUDIO_TYPES = {"dubbed", "subtitled"}


class MegaEmbedError(ValueError):
    pass


def normalize_external_id(external_id):
    external_id = (external_id or "").strip()
    if not external_id:
        raise MegaEmbedError("ID TMDB/IMDB e obrigatorio.")
    return external_id


def build_embed_url(media_type, external_id, season=None, episode=None, id_type="tmdb", audio="dubbed"):
    media_type = (media_type or "").strip().lower()
    id_type = (id_type or "tmdb").strip().lower()
    audio = (audio or "dubbed").strip().lower()
    external_id = normalize_external_id(external_id)

    if media_type not in MEDIA_TYPES:
        raise MegaEmbedError("Tipo de midia MegaEmbed invalido.")
    if id_type not in ID_TYPES:
        raise MegaEmbedError("Tipo de ID MegaEmbed invalido.")
    if audio not in AUDIO_TYPES:
        raise MegaEmbedError("Audio MegaEmbed invalido.")
    if audio == "subtitled" and id_type != "tmdb":
        raise MegaEmbedError("MegaEmbed legendado aceita apenas TMDB ID.")

    if media_type == "movie":
        if audio == "subtitled":
            return f"{DEFAULT_SUBTITLED_DOMAIN}/embed/movie/{external_id}"
        return f"{DEFAULT_DUBBED_DOMAIN}/embed/{external_id}"

    season_number = _positive_int(season, "Temporada")
    episode_number = _positive_int(episode, "Episodio")
    if audio == "subtitled":
        return f"{DEFAULT_SUBTITLED_DOMAIN}/embed/tv/{external_id}/{season_number}/{episode_number}"
    return f"{DEFAULT_DUBBED_DOMAIN}/embed/{external_id}/{season_number}/{episode_number}"


def import_embed(item, overwrite=False):
    title = (item.get("title") or "").strip()
    if not title:
        raise MegaEmbedError("Titulo e obrigatorio.")

    embed_url = build_embed_url(
        media_type=item.get("media_type"),
        external_id=item.get("external_id"),
        season=item.get("season"),
        episode=item.get("episode"),
        id_type=item.get("id_type"),
        audio=item.get("audio"),
    )
    category = (item.get("category") or "").strip() or _default_category(item.get("media_type"))

    existing = Video.query.filter_by(source_type="embed", source_url=embed_url).first()
    if existing:
        if overwrite:
            existing.title = title
            existing.category = category
            existing.external_provider = "megaembed"
            db.session.commit()
            return existing, "updated"
        return existing, "skipped"

    video = Video(
        title=title,
        source_url=embed_url,
        source_type="embed",
        external_provider="megaembed",
        category=category,
    )
    db.session.add(video)
    db.session.commit()
    return video, "created"


def fetch_available_ids(media_type):
    media_type = (media_type or "").strip().lower()
    if media_type == "movie":
        path = "/api/movie"
    elif media_type == "series":
        path = "/api/series"
    else:
        raise MegaEmbedError("Tipo de midia MegaEmbed invalido.")

    url = f"{DEFAULT_DUBBED_DOMAIN}{path}"
    req = Request(url, headers=API_HEADERS)
    try:
        with urlopen(req, timeout=20, context=ssl._create_unverified_context()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise MegaEmbedError(f"MegaEmbed retornou HTTP {exc.code} em {url}.") from exc
    except URLError as exc:
        raise MegaEmbedError(f"Falha ao acessar MegaEmbed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise MegaEmbedError("Resposta invalida da API MegaEmbed.") from exc
    return _normalize_id_payload(payload)


def import_available_ids(
    include_movies=True,
    include_series=True,
    season=1,
    episode=1,
    overwrite=False,
    series_offset=0,
    series_limit=None,
    request_delay=0.0,
    progress_callback=None,
):
    if not include_movies and not include_series:
        raise MegaEmbedError("Selecione filmes, series ou ambos para importar.")

    try:
        series_offset = max(0, int(series_offset or 0))
    except (TypeError, ValueError):
        series_offset = 0
    if series_limit in (None, "", 0, "0"):
        series_limit_value = None
    else:
        try:
            series_limit_value = max(1, int(series_limit))
        except (TypeError, ValueError):
            series_limit_value = None
    try:
        request_delay = max(0.0, float(request_delay or 0.0))
    except (TypeError, ValueError):
        request_delay = 0.0

    stats = {
        "movies_total": 0,
        "series_total": 0,
        "series_total_available": 0,
        "series_offset": series_offset,
        "series_limit": series_limit_value,
        "series_processed": 0,
        "next_offset": series_offset,
        "has_more": False,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "names_resolved": 0,
        "names_failed": 0,
        "seasons_processed": 0,
        "episodes_total": 0,
        "series_failed": 0,
    }

    def _emit(stage, **extra):
        if not progress_callback:
            return
        payload = {
            "stage": stage,
            "stats": dict(stats),
        }
        payload.update(extra)
        try:
            progress_callback(payload)
        except Exception:
            pass

    if include_movies:
        _emit("fetching_movies")
        movie_ids = fetch_available_ids("movie")
        stats["movies_total"] = len(movie_ids)
        _emit("importing_movies")
        _import_id_batch(
            movie_ids,
            "movie",
            stats,
            overwrite=overwrite,
            request_delay=request_delay,
            progress_callback=_emit,
        )

    if include_movies and (stats["created"] or stats["updated"]):
        db.session.commit()

    if include_series:
        if not TMDB_API_KEY and not TMDB_BEARER_TOKEN:
            raise MegaEmbedError("TMDB_API_KEY ou TMDB_BEARER_TOKEN e obrigatorio para expandir series em episodios.")
        _emit("fetching_series")
        all_series_ids = fetch_available_ids("series")
        stats["series_total_available"] = len(all_series_ids)

        if series_offset >= len(all_series_ids):
            series_chunk = []
        elif series_limit_value is None:
            series_chunk = all_series_ids[series_offset:]
        else:
            series_chunk = all_series_ids[series_offset:series_offset + series_limit_value]

        stats["series_total"] = len(series_chunk)
        _emit("importing_series")
        _import_series_episode_batch(
            series_chunk,
            stats,
            overwrite=overwrite,
            request_delay=request_delay,
            progress_callback=_emit,
        )

        consumed = series_offset + stats["series_processed"]
        stats["next_offset"] = consumed
        stats["has_more"] = consumed < stats["series_total_available"]

    if stats["created"] or stats["updated"]:
        db.session.commit()
    _emit("done")
    return stats


def _positive_int(value, label):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise MegaEmbedError(f"{label} e obrigatorio para series.") from exc
    if number < 1:
        raise MegaEmbedError(f"{label} deve ser maior que zero.")
    return number


def _default_category(media_type):
    return "Series" if (media_type or "").strip().lower() == "series" else "Filmes"


def _normalize_id_payload(payload):
    if isinstance(payload, list):
        ids = payload
    elif isinstance(payload, dict):
        ids = payload.get("data") or payload.get("ids") or payload.get("results") or []
    else:
        ids = []

    normalized = []
    seen = set()
    for value in ids:
        external_id = str(value).strip()
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        normalized.append(external_id)
    return normalized


def _import_id_batch(ids, media_type, stats, season=1, episode=1, overwrite=False, batch_size=100, request_delay=0.0, progress_callback=None):
    if media_type == "series":
        season = _positive_int(season, "Temporada")
        episode = _positive_int(episode, "Episodio")
    pending = 0
    total = len(ids)
    with db.session.no_autoflush:
        for index, external_id in enumerate(ids, start=1):
            tmdb_metadata = fetch_tmdb_metadata(media_type, external_id, request_delay=request_delay)
            if tmdb_metadata:
                stats["names_resolved"] += 1
            else:
                stats["names_failed"] += 1
            title = _display_title(media_type, external_id, season, episode, tmdb_metadata)
            item = {
                "title": title,
                "media_type": media_type,
                "id_type": "tmdb",
                "external_id": external_id,
                "season": season,
                "episode": episode,
                "audio": "dubbed",
                "category": _default_category(media_type),
            }
            embed_url = build_embed_url(media_type, external_id, season=season, episode=episode, id_type="tmdb")
            existing = Video.query.filter_by(source_type="embed", source_url=embed_url).first()
            if existing:
                if overwrite:
                    existing.title = item["title"]
                    existing.external_provider = "megaembed"
                    existing.category = item["category"]
                    if tmdb_metadata and tmdb_metadata.get("thumbnail_url"):
                        existing.thumbnail_url = tmdb_metadata["thumbnail_url"]
                    if tmdb_metadata and tmdb_metadata.get("synopsis"):
                        existing.synopsis = tmdb_metadata["synopsis"]
                    stats["updated"] += 1
                    pending += 1
                else:
                    stats["skipped"] += 1
                continue

            db.session.add(
                Video(
                    title=item["title"],
                    source_url=embed_url,
                    source_type="embed",
                    external_provider="megaembed",
                    category=item["category"],
                    thumbnail_url=tmdb_metadata.get("thumbnail_url") if tmdb_metadata else None,
                    synopsis=tmdb_metadata.get("synopsis") if tmdb_metadata else None,
                )
            )
            stats["created"] += 1
            pending += 1

            if pending >= batch_size:
                db.session.flush()
                pending = 0

            if progress_callback:
                progress_callback(
                    "movie_progress",
                    current_index=index,
                    total=total,
                    current_id=external_id,
                    current_title=(tmdb_metadata or {}).get("title") if tmdb_metadata else None,
                )


def _import_series_episode_batch(ids, stats, overwrite=False, batch_size=100, request_delay=0.0, progress_callback=None):
    pending = 0
    total = len(ids)
    with db.session.no_autoflush:
        for index, external_id in enumerate(ids, start=1):
            if progress_callback:
                progress_callback(
                    "series_start",
                    current_index=index,
                    total=total,
                    current_id=external_id,
                )
            series = fetch_tmdb_series_details(external_id, request_delay=request_delay)
            if not series:
                stats["names_failed"] += 1
                stats["series_failed"] += 1
                stats["series_processed"] += 1
                continue

            stats["names_resolved"] += 1
            seasons = [season for season in series.get("seasons", []) if int(season.get("season_number") or 0) > 0]
            if not seasons:
                stats["series_failed"] += 1
                stats["series_processed"] += 1
                continue

            for season in seasons:
                season_number = int(season.get("season_number") or 0)
                if progress_callback:
                    progress_callback(
                        "season_start",
                        current_index=index,
                        total=total,
                        current_id=external_id,
                        current_title=series.get("title"),
                        current_season=season_number,
                    )
                season_payload = fetch_tmdb_season_details(external_id, season_number, request_delay=request_delay)
                episodes = season_payload.get("episodes", []) if season_payload else []
                if not episodes:
                    continue
                stats["seasons_processed"] += 1

                for episode_payload in episodes:
                    episode_number = int(episode_payload.get("episode_number") or 0)
                    if episode_number < 1:
                        continue
                    stats["episodes_total"] += 1
                    embed_url = build_embed_url("series", external_id, season=season_number, episode=episode_number, id_type="tmdb")
                    title = _episode_title(series, season_number, episode_number, episode_payload)
                    thumbnail_url = _episode_thumbnail(series, episode_payload)
                    existing = Video.query.filter_by(source_type="embed", source_url=embed_url).first()
                    if existing:
                        if overwrite:
                            existing.title = title
                            existing.external_provider = "megaembed"
                            existing.category = "Series"
                            if thumbnail_url:
                                existing.thumbnail_url = thumbnail_url
                            if series.get("synopsis"):
                                existing.synopsis = series["synopsis"]
                            stats["updated"] += 1
                            pending += 1
                        else:
                            stats["skipped"] += 1
                        continue

                    db.session.add(
                        Video(
                            title=title,
                            source_url=embed_url,
                            source_type="embed",
                            external_provider="megaembed",
                            category="Series",
                            thumbnail_url=thumbnail_url,
                            synopsis=series.get("synopsis") or None,
                        )
                    )
                    stats["created"] += 1
                    pending += 1

                    if pending >= batch_size:
                        db.session.flush()
                        pending = 0

            stats["series_processed"] += 1
            if progress_callback:
                progress_callback(
                    "series_done",
                    current_index=index,
                    total=total,
                    current_id=external_id,
                    current_title=series.get("title"),
                )
            if (pending or stats["created"] or stats["updated"]) and index % max(1, batch_size // 10 or 1) == 0:
                try:
                    db.session.flush()
                except Exception:
                    pass


def fetch_tmdb_metadata(media_type, external_id, request_delay=0.0):
    cached = _get_tmdb_cache_entry(media_type, external_id)
    if cached is not None:
        return cached

    if not TMDB_API_KEY and not TMDB_BEARER_TOKEN:
        return None

    media_path = "tv" if media_type == "series" else "movie"
    for language in ("pt-BR", "en-US"):
        payload = _request_tmdb_json(f"/{media_path}/{external_id}", {"language": language}, delay=request_delay)
        if not payload:
            continue
        title = (payload.get("name") if media_type == "series" else payload.get("title")) or payload.get("original_name") or payload.get("original_title")
        if not title:
            continue
        poster_path = payload.get("poster_path")
        overview = (payload.get("overview") or "").strip()
        metadata = {
            "title": title,
            "thumbnail_url": f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else "",
            "synopsis": overview,
        }
        _set_tmdb_cache_entry(media_type, external_id, metadata)
        return metadata
    return None


def fetch_tmdb_series_details(external_id, request_delay=0.0):
    cached = _get_tmdb_cache_entry("series_details", external_id)
    if cached is not None:
        return cached

    for language in ("pt-BR", "en-US"):
        payload = _request_tmdb_json(f"/tv/{external_id}", {"language": language}, delay=request_delay)
        if not payload:
            continue
        title = payload.get("name") or payload.get("original_name")
        if not title:
            continue
        poster_path = payload.get("poster_path")
        overview = (payload.get("overview") or "").strip()
        details = {
            "title": title,
            "thumbnail_url": f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else "",
            "synopsis": overview,
            "seasons": [
                {
                    "season_number": season.get("season_number"),
                    "episode_count": season.get("episode_count") or 0,
                }
                for season in payload.get("seasons", [])
            ],
        }
        _set_tmdb_cache_entry("series_details", external_id, details)
        return details
    return None


def fetch_tmdb_season_details(external_id, season_number, request_delay=0.0):
    cache_id = f"{external_id}:{season_number}"
    cached = _get_tmdb_cache_entry("series_season", cache_id)
    if cached is not None:
        return cached

    for language in ("pt-BR", "en-US"):
        payload = _request_tmdb_json(f"/tv/{external_id}/season/{season_number}", {"language": language}, delay=request_delay)
        if not payload:
            continue
        episodes = []
        for episode in payload.get("episodes", []):
            episode_number = episode.get("episode_number")
            if not episode_number:
                continue
            still_path = episode.get("still_path")
            episodes.append(
                {
                    "episode_number": episode_number,
                    "name": episode.get("name") or "",
                    "still_url": f"{TMDB_IMAGE_BASE_URL}{still_path}" if still_path else "",
                }
            )
        details = {"season_number": season_number, "episodes": episodes}
        _set_tmdb_cache_entry("series_season", cache_id, details)
        return details
    return None


def _request_tmdb_json(path, params=None, delay=0.0):
    query_params = dict(params or {})
    if TMDB_API_KEY and not TMDB_BEARER_TOKEN:
        query_params["api_key"] = TMDB_API_KEY
    query = f"?{urlencode(query_params)}" if query_params else ""
    req = Request(f"{TMDB_API_BASE_URL}{path}{query}", headers=TMDB_HEADERS)
    try:
        with urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError):
        return None
    if delay and delay > 0:
        try:
            time.sleep(float(delay))
        except (TypeError, ValueError):
            pass
    return payload


def _tmdb_cache_key(media_type, external_id):
    return f"{media_type}:{external_id}"


def _get_tmdb_cache_entry(media_type, external_id):
    cache = _load_tmdb_cache()
    item = cache.get("entries", {}).get(_tmdb_cache_key(media_type, external_id))
    if not item:
        return None
    cached_at = int(item.get("cached_at") or 0)
    if TMDB_CACHE_TTL_SECONDS > 0 and time.time() - cached_at > TMDB_CACHE_TTL_SECONDS:
        return None
    return item.get("data")


def _set_tmdb_cache_entry(media_type, external_id, metadata):
    with _TMDB_CACHE_LOCK:
        cache = _load_tmdb_cache_unlocked()
        cache.setdefault("entries", {})[_tmdb_cache_key(media_type, external_id)] = {
            "cached_at": int(time.time()),
            "data": metadata,
        }
        _write_tmdb_cache_unlocked(cache)


def _load_tmdb_cache():
    with _TMDB_CACHE_LOCK:
        return _load_tmdb_cache_unlocked()


def _load_tmdb_cache_unlocked():
    global _TMDB_CACHE
    if _TMDB_CACHE is not None:
        return _TMDB_CACHE

    try:
        with open(TMDB_CACHE_PATH, "r", encoding="utf-8") as cache_file:
            cache = json.load(cache_file)
    except (OSError, json.JSONDecodeError):
        cache = {"version": TMDB_CACHE_VERSION, "entries": {}}

    if cache.get("version") != TMDB_CACHE_VERSION or not isinstance(cache.get("entries"), dict):
        cache = {"version": TMDB_CACHE_VERSION, "entries": {}}

    _TMDB_CACHE = cache
    return _TMDB_CACHE


def _write_tmdb_cache_unlocked(cache):
    global _TMDB_CACHE
    directory = os.path.dirname(TMDB_CACHE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{TMDB_CACHE_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as cache_file:
        json.dump(cache, cache_file, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, TMDB_CACHE_PATH)
    _TMDB_CACHE = cache


def _display_title(media_type, external_id, season, episode, tmdb_metadata=None):
    if tmdb_metadata and tmdb_metadata.get("title"):
        if media_type == "series":
            return f"{tmdb_metadata['title']} T{int(season):02d}E{int(episode):02d}"
        return tmdb_metadata["title"]
    return _bulk_title(media_type, external_id, season, episode)


def _episode_title(series, season_number, episode_number, episode_payload):
    base = series.get("title") or f"MegaEmbed Serie"
    episode_name = (episode_payload.get("name") or "").strip()
    title = f"{base} T{int(season_number):02d}E{int(episode_number):02d}"
    if episode_name:
        return f"{title} - {episode_name}"
    return title


def _episode_thumbnail(series, episode_payload):
    return episode_payload.get("still_url") or series.get("thumbnail_url") or None


def _bulk_title(media_type, external_id, season, episode):
    if media_type == "series":
        return f"MegaEmbed Serie {external_id} T{int(season):02d}E{int(episode):02d}"
    return f"MegaEmbed Filme {external_id}"
