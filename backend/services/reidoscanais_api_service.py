import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.extensions import db
from backend.models import Video
from backend.services.xtream_service import REIDOSCANAIS_PROVIDERS, resolve_live_source_url

API_BASE_URL = os.getenv("REIDOSCANAIS_API_BASE_URL", "https://api.reidoscanais.ooo").rstrip("/")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "application/json",
}

DEFAULT_SPORT_IMPORT_STATUSES = {"live", "upcoming"}


class ReidosCanaisAPIError(RuntimeError):
    pass


def _request_json(path, params=None):
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_BASE_URL}{path}{query}"
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ReidosCanaisAPIError(f"API ReidosCanais retornou HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ReidosCanaisAPIError(f"Falha ao acessar API ReidosCanais: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ReidosCanaisAPIError("Resposta invalida da API ReidosCanais.") from exc

    if not payload.get("success", False):
        raise ReidosCanaisAPIError("API ReidosCanais retornou erro.")
    return payload


def list_channel_categories():
    payload = _request_json("/channels/categories")
    return payload.get("data", [])


def list_sports_categories():
    payload = _request_json("/sports/categories")
    return payload.get("data", [])


def fetch_items(source="channels", category="", status="", query=""):
    source = source or "channels"
    category = (category or "").strip()
    status = (status or "").strip()
    query = (query or "").strip()

    if source == "search":
        if not query:
            return []
        payload = _request_json("/search", {"q": query})
        data = payload.get("data", {})
        return _normalize_channels(data.get("channels", [])) + _normalize_sports(data.get("events", []))

    if source == "sports":
        params = {}
        if category:
            params["category"] = category
        if status and status != "all":
            params["status"] = status
        payload = _request_json("/sports", params)
        return _normalize_sports(payload.get("data", []), requested_status=status)

    params = {}
    if category:
        params["category"] = category
    payload = _request_json("/channels", params)
    return _normalize_channels(payload.get("data", []))


def _normalize_channels(channels):
    items = []
    for channel in channels:
        embed_url = (channel.get("embed_url") or "").strip()
        is_active = bool(channel.get("is_active", True))
        items.append(
            {
                "kind": "channel",
                "item_id": channel.get("id") or "",
                "title": channel.get("name") or channel.get("id") or "Canal sem nome",
                "description": channel.get("description") or "",
                "category": channel.get("category") or "",
                "status": "active" if is_active else "inactive",
                "provider": "ReidosCanais",
                "quality": "",
                "embed_url": embed_url,
                "thumb_url": channel.get("logo_url") or "",
                "external_provider": "reidoscanais_api",
                "selected": bool(embed_url and is_active),
                "importable": bool(embed_url and is_active),
            }
        )
    return items


def _normalize_sports(events, requested_status=""):
    items = []
    include_finished = requested_status in {"finished", "all"}
    for event in events:
        event_status = event.get("status") or ""
        default_selected = event_status in DEFAULT_SPORT_IMPORT_STATUSES
        if event_status == "finished" and not include_finished:
            default_selected = False
        embeds = event.get("embeds") or []
        for index, embed in enumerate(embeds, start=1):
            embed_url = (embed.get("embed_url") or "").strip()
            provider = embed.get("provider") or "Embed"
            quality = embed.get("quality") or ""
            suffix = f" - {provider}" + (f" ({quality})" if quality else "")
            items.append(
                {
                    "kind": "sport",
                    "item_id": f"{event.get('id') or ''}:{index}",
                    "title": f"{event.get('title') or 'Evento esportivo'}{suffix}",
                    "description": event.get("description") or "",
                    "category": event.get("category") or "",
                    "status": event_status,
                    "provider": provider,
                    "quality": quality,
                    "start_time": event.get("start_time") or "",
                    "end_time": event.get("end_time") or "",
                    "embed_url": embed_url,
                    "thumb_url": event.get("poster") or "",
                    "external_provider": "reidoscanais_sports_api",
                    "selected": bool(embed_url and default_selected),
                    "importable": bool(embed_url),
                }
            )
    return items


def import_items(items, overwrite=False):
    created = skipped = updated = 0

    for item in items:
        embed_url = (item.get("embed_url") or "").strip()
        title = (item.get("title") or "").strip()
        external_provider = item.get("external_provider") or "reidoscanais_api"
        if not embed_url or not title:
            skipped += 1
            continue
        stream_url = _stream_url_for_import(embed_url, external_provider)
        if not stream_url:
            skipped += 1
            continue

        existing = (
            Video.query.filter(Video.source_type == "embed")
            .filter(Video.source_url.in_([embed_url, stream_url]))
            .first()
        )
        if existing:
            if overwrite:
                existing.title = title
                existing.source_url = stream_url
                existing.external_provider = external_provider
                updated += 1
            else:
                skipped += 1
            continue

        db.session.add(
            Video(
                title=title,
                source_url=stream_url,
                source_type="embed",
                external_provider=external_provider,
            )
        )
        created += 1

    db.session.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def convert_existing_embeds_to_streams():
    converted = failed = unchanged = 0
    videos = (
        Video.query.filter(Video.source_type == "embed")
        .filter(Video.external_provider.in_(REIDOSCANAIS_PROVIDERS))
        .order_by(Video.id)
        .all()
    )
    for video in videos:
        stream_url = _stream_url_for_import(video.source_url, video.external_provider)
        if not stream_url:
            failed += 1
            continue
        if stream_url == video.source_url:
            unchanged += 1
            continue
        video.source_url = stream_url
        converted += 1
    if converted:
        db.session.commit()
    return {"converted": converted, "failed": failed, "unchanged": unchanged}


def _stream_url_for_import(embed_url, external_provider):
    if external_provider not in REIDOSCANAIS_PROVIDERS:
        return embed_url
    return resolve_live_source_url(embed_url)
