import random
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app

from backend.models import JellyfinServer, MediaServer, Video, VideoLocation

DEFAULT_STRATEGY = "priority_fallback"


class ServerSelectionError(RuntimeError):
    pass


def active_locations_for_video(video_id):
    return (
        VideoLocation.query.filter_by(video_id=video_id, is_active=True)
        .join(VideoLocation.media_server)
        .order_by(VideoLocation.is_primary.desc(), MediaServer.priority)
        .all()
    )


def _eligible(locations):
    return [
        loc
        for loc in locations
        if loc.media_server
        and loc.media_server.is_stream_capable
        and loc.media_server.is_active
        and loc.media_server.has_capacity()
    ]


def primary_first(locations):
    candidates = _eligible(locations)
    if not candidates:
        return None
    primary = [loc for loc in candidates if loc.is_primary]
    return sorted(primary or candidates, key=lambda loc: loc.media_server.priority)[0]


def priority_fallback(locations):
    candidates = _eligible(locations)
    if not candidates:
        return None
    return sorted(candidates, key=lambda loc: (not loc.is_primary, loc.media_server.priority, loc.id))[0]


def weighted_random(locations):
    candidates = _eligible(locations)
    if not candidates:
        return None
    weights = [max(1, loc.media_server.weight or 1) for loc in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def lowest_connections(locations):
    candidates = _eligible(locations)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda loc: (
            not loc.is_primary,
            loc.media_server.current_connections,
            loc.media_server.priority,
            loc.id,
        ),
    )[0]


STRATEGIES = {
    "primary_first": primary_first,
    "priority_fallback": priority_fallback,
    "weighted_random": weighted_random,
    "lowest_connections": lowest_connections,
}


def select_location(video_id, strategy=DEFAULT_STRATEGY):
    locations = active_locations_for_video(video_id)
    selector = STRATEGIES.get(strategy, STRATEGIES[DEFAULT_STRATEGY])
    selected = selector(locations)
    if not selected:
        raise ServerSelectionError("Nenhum servidor de mídia ativo disponível para este vídeo.")
    return selected


def _expiration(ttl_seconds):
    return datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)


def _build_hls_url(video_id, client_id, jwt_secret, strategy, ttl_seconds):
    location = select_location(video_id, strategy=strategy)
    server = location.media_server
    if not server.is_stream_capable:
        raise ServerSelectionError("Servidor selecionado nÃ£o Ã© uma engine de stream.")
    token = jwt.encode(
        {
            "client_id": client_id,
            "video_id": video_id,
            "server_id": server.id,
            "storage_path": location.storage_path,
            "exp": _expiration(ttl_seconds),
        },
        jwt_secret,
        algorithm="HS256",
    )
    return f"{server.normalized_public_url}/hls/{token}/{video_id}/master.m3u8"


def _build_jellyfin_url(video, client_id, jwt_secret, ttl_seconds):
    server = JellyfinServer.query.get(video.jellyfin_server_id)
    if not server or not server.is_active or not video.jellyfin_item_id:
        raise ServerSelectionError("Servidor ou item Jellyfin indisponível para este vídeo.")
    token = jwt.encode(
        {
            "client_id": client_id,
            "video_id": video.id,
            "provider": "jellyfin",
            "jellyfin_server_id": server.id,
            "jellyfin_item_id": video.jellyfin_item_id,
            "jellyfin_internal_url": server.normalized_internal_url,
            "exp": _expiration(ttl_seconds),
        },
        jwt_secret,
        algorithm="HS256",
    )
    stream_public_url = current_app.config.get("STREAM_PUBLIC_URL", "").rstrip("/")
    return f"{stream_public_url}/jellyfin/{token}/{video.jellyfin_item_id}/master.m3u8"


def _build_embed_url(video):
    if not video.source_url:
        raise ServerSelectionError("Vídeo embed sem URL de origem configurada.")
    return video.source_url


def generate_video_url(video_id, client_id, jwt_secret, strategy=DEFAULT_STRATEGY, ttl_seconds=3600):
    video = Video.query.get(video_id)
    if not video:
        raise ServerSelectionError("Vídeo não encontrado.")
    if video.source_type == "embed":
        return _build_embed_url(video)
    if video.is_jellyfin:
        return _build_jellyfin_url(video, client_id, jwt_secret, ttl_seconds)
    return _build_hls_url(video_id, client_id, jwt_secret, strategy, ttl_seconds)
