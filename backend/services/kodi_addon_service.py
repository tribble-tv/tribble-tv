import json
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import current_app

from backend.extensions import db
from backend.models import Video

PROVIDER = "kodi_addon"
DEFAULT_MAX_DEPTH = 4


class KodiAddonError(RuntimeError):
    pass


@dataclass
class KodiResolvedItem:
    title: str
    stream_url: str
    category: str = ""
    thumbnail_url: str = ""


def sync_source(source, overwrite=False, max_depth=DEFAULT_MAX_DEPTH, resolver_url=None):
    try:
        payload = resolve_source(source, max_depth=max_depth, resolver_url=resolver_url)
        status = (payload.get("status") or "success").strip()
        if status == "needs_config":
            source.last_status = "needs_config"
            source.last_error = payload.get("error") or "Fonte Kodi precisa de configuracao no add-on."
            source.last_stats = payload.get("stats") or _empty_stats()
            source.last_scan_depth = max_depth
            source.last_synced_at = datetime.utcnow()
            db.session.commit()
            return source.last_stats

        stats = import_resolved_items(payload.get("items") or [], source, overwrite=overwrite)
        source.last_status = "success"
        source.last_error = None
        source.last_stats = stats
        source.last_scan_depth = max_depth
        source.last_synced_at = datetime.utcnow()
        db.session.commit()
        return stats
    except KodiAddonError as exc:
        source.last_status = "error"
        source.last_error = str(exc)
        source.last_stats = None
        source.last_scan_depth = max_depth
        source.last_synced_at = datetime.utcnow()
        db.session.commit()
        raise


def resolve_source(source, max_depth=DEFAULT_MAX_DEPTH, resolver_url=None):
    base_url = (resolver_url or current_app.config.get("KODI_RESOLVER_URL") or "").rstrip("/")
    if not base_url:
        raise KodiAddonError("KODI_RESOLVER_URL nao configurado.")

    body = {
        "source_url": source.effective_source_url,
        "addon_id": (source.addon_id or "").strip(),
        "entry_path": (source.entry_path or "").strip(),
        "default_category": (source.default_category or "").strip(),
        "max_depth": max(1, int(max_depth or DEFAULT_MAX_DEPTH)),
    }
    if not body["source_url"]:
        raise KodiAddonError("URL da fonte Kodi e obrigatoria.")

    req = Request(
        f"{base_url}/resolve",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as response:
            data = response.read().decode("utf-8", "ignore")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise KodiAddonError(f"Resolver Kodi retornou HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise KodiAddonError(f"Falha ao acessar resolver Kodi: {exc.reason}") from exc

    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise KodiAddonError("Resolver Kodi retornou JSON invalido.") from exc
    if not isinstance(payload, dict):
        raise KodiAddonError("Resolver Kodi retornou payload invalido.")
    if payload.get("status") == "error":
        raise KodiAddonError(payload.get("error") or "Resolver Kodi falhou.")
    return payload


def import_resolved_items(items, source, overwrite=False):
    stats = _empty_stats()
    stats["total"] = len(items)
    seen_urls = set()

    for raw_item in items:
        item = _normalize_item(raw_item, source)
        if not item:
            stats["invalid"] += 1
            continue
        if item.stream_url in seen_urls:
            stats["skipped"] += 1
            continue
        seen_urls.add(item.stream_url)

        existing = Video.query.filter_by(source_url=item.stream_url).first()
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
                source_url=item.stream_url,
                source_type="embed",
                external_provider=PROVIDER,
                category=item.category or None,
                thumbnail_url=item.thumbnail_url or None,
            )
        )
        stats["created"] += 1

    db.session.commit()
    return stats


def _normalize_item(raw_item, source):
    if not isinstance(raw_item, dict):
        return None
    stream_url = (raw_item.get("stream_url") or raw_item.get("url") or "").strip()
    if not _is_http_url(stream_url):
        return None
    title = (raw_item.get("title") or raw_item.get("label") or stream_url.rsplit("/", 1)[-1]).strip()
    if not title:
        return None
    category = (raw_item.get("category") or source.default_category or "").strip()
    thumbnail_url = (raw_item.get("thumbnail_url") or raw_item.get("thumbnail") or raw_item.get("icon") or "").strip()
    return KodiResolvedItem(
        title=title,
        stream_url=stream_url,
        category=category,
        thumbnail_url=thumbnail_url,
    )


def _is_http_url(value):
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _empty_stats():
    return {"created": 0, "updated": 0, "skipped": 0, "invalid": 0, "total": 0}
