from flask import current_app

from backend.models import Video
from backend.services.server_selector import generate_video_url
from backend.services.settings_service import KEY_VOD_STRATEGY, get_setting


def _resolve_strategy(explicit=None):
    if explicit:
        return explicit
    persisted = get_setting(KEY_VOD_STRATEGY)
    if persisted:
        return persisted
    return current_app.config.get("SERVER_SELECTION_STRATEGY", "priority_fallback")


def build_video_playback_url(video_id, client_id, strategy=None):
    return generate_video_url(
        video_id=video_id,
        client_id=client_id,
        jwt_secret=current_app.config["JWT_SECRET"],
        strategy=_resolve_strategy(strategy),
        ttl_seconds=current_app.config.get("VIDEO_TOKEN_TTL_SECONDS", 3600),
    )


def build_m3u_playlist(client_id, videos=None):
    videos = videos if videos is not None else Video.query.order_by(Video.title).all()
    lines = ["#EXTM3U"]
    for video in videos:
        if video.source_type == "embed":
            stream_url = video.source_url
            provider = video.external_provider or "embed"
        else:
            stream_url = build_video_playback_url(video.id, client_id)
            provider = "jellyfin" if video.is_jellyfin else "hls"
        lines.append(f'#EXTINF:-1 tvg-id="{video.id}" group-title="{provider}",{video.title}')
        lines.append(stream_url)
    return "\n".join(lines) + "\n"
