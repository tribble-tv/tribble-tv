import re
import unicodedata
import uuid
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import or_

from backend.extensions import db
from backend.models import JellyfinItem, JellyfinServer, Video, WatchProgress, XtreamUser
from backend.services.playlist_service import build_m3u_playlist, build_video_playback_url
from backend.services.server_selector import ServerSelectionError
from backend.services.xtream_auth_service import authenticate

client_bp = Blueprint("client", __name__)


def current_client_id():
    return session.get("client_id")


def _require_client():
    client_id = current_client_id()
    if not client_id:
        client_id = str(uuid.uuid4())
        session["client_id"] = client_id
    return client_id


def current_client_user():
    user_id = session.get("client_user_id")
    if not user_id:
        return None
    user = XtreamUser.query.filter_by(id=user_id, is_active=True).first()
    if not user:
        session.pop("client_user_id", None)
        session.pop("client_username", None)
        return None
    return user


def _is_safe_next_url(next_url):
    if not next_url:
        return False
    parsed = urlparse(next_url)
    return not parsed.scheme and not parsed.netloc and next_url.startswith("/")


def _login_redirect():
    next_url = request.full_path if request.query_string else request.path
    return redirect(url_for("client.login", next=next_url))


def _require_client_user():
    user = current_client_user()
    if not user:
        return None
    _require_client()
    return user


def _require_client_page():
    if _require_client_user():
        return None
    return _login_redirect()


def _require_client_api():
    if _require_client_user():
        return None
    return jsonify({"error": "authentication required"}), 401


def _authenticated_playlist_client_id():
    if _require_client_user():
        return _require_client(), None

    username = request.values.get("username", "").strip()
    password = request.values.get("password", "").strip()
    if username or password:
        if not authenticate(username, password):
            return None, (jsonify({"error": "authentication required"}), 401)
        return _require_client(), None

    return None, _login_redirect()


def _empty_progress(video_id):
    return {
        "video_id": video_id,
        "position_seconds": 0.0,
        "duration_seconds": 0.0,
        "progress_percent": 0.0,
        "completed": False,
        "last_watched_at": None,
    }


def _progress_payload(progress, video_id):
    if not progress:
        return _empty_progress(video_id)
    return progress.to_dict()


def _progress_map_for_user(user_id, video_ids):
    ids = sorted({int(video_id) for video_id in video_ids if video_id})
    if not ids:
        return {}
    result = {}
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        rows = (
            WatchProgress.query
            .filter(WatchProgress.user_id == user_id, WatchProgress.video_id.in_(batch))
            .all()
        )
        for row in rows:
            result[row.video_id] = row
    return result


def _float_payload_value(payload, key, default=0.0):
    try:
        return float(payload.get(key, default) or default)
    except (TypeError, ValueError):
        return default


@client_bp.context_processor
def inject_client_user():
    return {"current_client_user": current_client_user()}


@client_bp.route("/")
def index():
    return redirect(url_for("client.catalog"))


@client_bp.route("/client/login", methods=["GET", "POST"])
def login():
    if current_client_user():
        next_url = request.args.get("next")
        if _is_safe_next_url(next_url):
            return redirect(next_url)
        return redirect(url_for("client.catalog"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        next_url = request.form.get("next") or request.args.get("next")

        user = authenticate(username, password)
        if user:
            session["client_user_id"] = user.id
            session["client_username"] = user.username
            _require_client()
            if _is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("client.catalog"))

        flash("Usuario ou senha invalidos.", "error")

    next_url = request.args.get("next")
    if not _is_safe_next_url(next_url):
        next_url = url_for("client.catalog")
    return render_template("client/login.html", next_url=next_url)


@client_bp.route("/client/logout")
def logout():
    session.pop("client_user_id", None)
    session.pop("client_username", None)
    flash("Sessao encerrada.", "success")
    return redirect(url_for("client.login"))


@client_bp.route("/client/")
def catalog():
    auth_response = _require_client_page()
    if auth_response:
        return auth_response
    _require_client()
    categories = sorted(list({
        v.category for v in
        Video.query.with_entities(Video.category).filter(Video.source_type != "disabled").all()
        if v.category
    }))
    return render_template("client/catalog.html", categories=categories)


@client_bp.route("/client/api/videos")
def api_videos():
    auth_response = _require_client_api()
    if auth_response:
        return auth_response

    q = (request.args.get("q") or "").strip().lower()
    category = (request.args.get("category") or "").strip().lower()
    provider = (request.args.get("provider") or "").strip().lower()
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(int(request.args.get("per_page", 100)), 200)
    except (ValueError, TypeError):
        page = 1
        per_page = 100

    query = Video.query.filter(Video.source_type != "disabled")

    if q:
        query = query.filter(Video.title.ilike(f"%{q}%"))
    if category and category != "all":
        query = query.filter(db.func.lower(Video.category) == category)
    if provider and provider != "all":
        if provider == "youtube":
            query = query.filter(Video.source_type == "embed", Video.external_provider == "youtube")
        elif provider == "embed":
            query = query.filter(Video.source_type == "embed", Video.external_provider != "youtube")
        elif provider == "jellyfin":
            query = query.filter(Video.source_type == "jellyfin")
        elif provider == "hls":
            query = query.filter(Video.source_type == "hls")
        elif provider == "torrent":
            query = query.filter(Video.source_type == "torrent")

    total = query.count()
    videos = query.order_by(Video.title).offset((page - 1) * per_page).limit(per_page).all()
    user = current_client_user()
    progress_by_video = _progress_map_for_user(user.id, [v.id for v in videos]) if user else {}

    def provider_key(v):
        if v.source_type == "embed" and v.external_provider == "youtube":
            return "youtube"
        if v.source_type == "embed":
            return "embed"
        if v.source_type == "jellyfin":
            return "jellyfin"
        if v.source_type == "torrent":
            return "torrent"
        return "hls"

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "videos": [
            {
                "id": v.id,
                "title": v.title,
                "category": v.category or "Vídeo",
                "thumbnail_url": v.thumbnail_url or "",
                "synopsis": v.synopsis or "",
                "provider": provider_key(v),
                "created_at": v.created_at.strftime("%d/%m/%Y") if v.created_at else "",
                "progress": _progress_payload(progress_by_video.get(v.id), v.id),
                "progress_percent": _progress_payload(progress_by_video.get(v.id), v.id)["progress_percent"],
                "completed": _progress_payload(progress_by_video.get(v.id), v.id)["completed"],
            }
            for v in videos
        ],
    })

# ─── helpers ────────────────────────────────────────────────────────────────
@client_bp.route("/client/api/videos/<int:video_id>/progress", methods=["GET", "POST"])
def video_progress(video_id):
    user = _require_client_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401

    video = Video.query.get_or_404(video_id)
    progress = WatchProgress.query.filter_by(user_id=user.id, video_id=video.id).first()

    if request.method == "GET":
        return jsonify(_progress_payload(progress, video.id))

    if video.source_type == "embed":
        return jsonify({"error": "progress is not available for embedded players"}), 400

    payload = request.get_json(silent=True) or request.form or {}
    duration = max(0.0, _float_payload_value(payload, "duration_seconds"))
    position = max(0.0, _float_payload_value(payload, "position_seconds"))
    if duration > 0:
        position = min(position, duration)
        progress_percent = min(100.0, max(0.0, (position / duration) * 100.0))
    else:
        progress_percent = 0.0

    raw_completed = payload.get("completed", False)
    explicit_completed = raw_completed is True or str(raw_completed).strip().lower() in {"1", "true", "yes", "on"}
    near_end = duration > 0 and position > 0 and (progress_percent >= 90.0 or duration - position <= 30.0)
    completed = explicit_completed or near_end

    now = datetime.utcnow()
    if not progress:
        progress = WatchProgress(user_id=user.id, video_id=video.id, created_at=now)
        db.session.add(progress)

    progress.position_seconds = position
    progress.duration_seconds = duration
    progress.progress_percent = 100.0 if completed and progress_percent >= 90.0 else progress_percent
    progress.completed = completed
    progress.last_watched_at = now
    progress.updated_at = now
    db.session.commit()

    return jsonify(progress.to_dict())


_EP_RE = re.compile(r'\s+T(\d+)E(\d+)(?:\s|$)', re.IGNORECASE)


def _series_base_title(title: str) -> str | None:
    """Return base series name if title contains an episode marker."""
    m = _EP_RE.search(title)
    return title[:m.start()].strip() if m else None


def _slug(text: str) -> str:
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[\s_-]+', '-', text)


# ─── routes ──────────────────────────────────────────────────────────────────

@client_bp.route("/client/api/series")
def api_series():
    """Return series grouped by base title, with episode/season counts."""
    auth_response = _require_client_api()
    if auth_response:
        return auth_response

    q = (request.args.get("q") or "").strip().lower()
    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(int(request.args.get("per_page", 100)), 200)
    except (ValueError, TypeError):
        page, per_page = 1, 100

    rows = (
        Video.query
        .filter(Video.source_type != "disabled", db.func.lower(Video.category) == "series")
        .with_entities(Video.id, Video.title, Video.thumbnail_url, Video.created_at, Video.synopsis)
        .order_by(Video.title)
        .all()
    )

    user = current_client_user()
    progress_by_video = _progress_map_for_user(user.id, [row[0] for row in rows]) if user else {}

    # Group by base title
    groups: dict[str, dict] = {}
    for vid_id, title, thumb, created, synopsis in rows:
        base = _series_base_title(title)
        if base is None:
            continue
        if q and q not in base.lower():
            continue
        m = _EP_RE.search(title)
        season, episode = int(m.group(1)), int(m.group(2))
        key = base.lower()
        if key not in groups:
            groups[key] = {
                "slug": _slug(base),
                "title": base,
                "thumbnail_url": thumb or "",
                "synopsis": synopsis or "",
                "seasons": set(),
                "episodes": 0,
                "first_video_id": vid_id,
                "progress_total": 0.0,
                "completed_episodes": 0,
            }
        progress_payload = _progress_payload(progress_by_video.get(vid_id), vid_id)
        groups[key]["seasons"].add(season)
        groups[key]["episodes"] += 1
        groups[key]["progress_total"] += progress_payload["progress_percent"]
        if progress_payload["completed"]:
            groups[key]["completed_episodes"] += 1
        if thumb and not groups[key]["thumbnail_url"]:
            groups[key]["thumbnail_url"] = thumb
        if synopsis and not groups[key]["synopsis"]:
            groups[key]["synopsis"] = synopsis

    all_series = sorted(groups.values(), key=lambda x: x["title"])
    total = len(all_series)
    start = (page - 1) * per_page
    page_items = all_series[start: start + per_page]

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "series": [
            {
                "slug":          s["slug"],
                "title":         s["title"],
                "thumbnail_url": s["thumbnail_url"],
                "synopsis":      s.get("synopsis", ""),
                "season_count":  len(s["seasons"]),
                "episode_count": s["episodes"],
                "completed_episodes": s["completed_episodes"],
                "progress_percent": round(s["progress_total"] / max(1, s["episodes"]), 2),
                "completed": s["episodes"] > 0 and s["completed_episodes"] == s["episodes"],
            }
            for s in page_items
        ],
    })


@client_bp.route("/client/series/<series_slug>")
def series_detail(series_slug):
    """Series detail page — shows all seasons/episodes grouped."""
    auth_response = _require_client_page()
    if auth_response:
        return auth_response

    _require_client()
    return render_template("client/series.html", series_slug=series_slug)


@client_bp.route("/client/series/<series_slug>/episodes")
def series_episodes(series_slug):
    """Return all episodes for a series, grouped by season."""
    auth_response = _require_client_api()
    if auth_response:
        return auth_response

    rows = (
        Video.query
        .filter(Video.source_type != "disabled", db.func.lower(Video.category) == "series")
        .with_entities(Video.id, Video.title, Video.thumbnail_url, Video.created_at, Video.synopsis)
        .order_by(Video.title)
        .all()
    )

    seasons: dict[int, list] = {}
    series_title = None
    series_thumb = ""
    series_synopsis = ""
    matched_video_ids = []

    for vid_id, title, thumb, created, synopsis in rows:
        base = _series_base_title(title)
        if base is None:
            continue
        if _slug(base) != series_slug:
            continue
        m = _EP_RE.search(title)
        season, episode = int(m.group(1)), int(m.group(2))
        if series_title is None:
            series_title = base
        if thumb and not series_thumb:
            series_thumb = thumb
        if synopsis and not series_synopsis:
            series_synopsis = synopsis
        matched_video_ids.append(vid_id)
        seasons.setdefault(season, []).append({
            "id":         vid_id,
            "title":      title,
            "episode":    episode,
            "thumbnail_url": thumb or "",
        })

    if series_title is None:
        return jsonify({"error": "Series not found"}), 404

    user = current_client_user()
    progress_by_video = _progress_map_for_user(user.id, matched_video_ids) if user else {}
    for s in seasons.values():
        for episode in s:
            progress_payload = _progress_payload(progress_by_video.get(episode["id"]), episode["id"])
            episode["progress"] = progress_payload
            episode["progress_percent"] = progress_payload["progress_percent"]
            episode["completed"] = progress_payload["completed"]
        s.sort(key=lambda e: e["episode"])

    return jsonify({
        "title":         series_title,
        "thumbnail_url": series_thumb,
        "synopsis":      series_synopsis,
        "seasons":       {
            str(k): v for k, v in sorted(seasons.items())
        },
    })


@client_bp.route("/client/player/<int:video_id>")
def player(video_id):
    auth_response = _require_client_page()
    if auth_response:
        return auth_response

    client_id = _require_client()
    video = Video.query.get_or_404(video_id)
    is_embed = video.source_type == "embed"
    if is_embed:
        playback_url = video.source_url
    elif video.source_type == "torrent":
        playback_url = url_for("client.torrent_stream", video_id=video_id)
    else:
        try:
            playback_url = build_video_playback_url(video_id, client_id)
        except ServerSelectionError:
            abort(503)
            
    # Carregar sugestões de vídeos (outros vídeos ativos na mesma categoria ou aleatórios)
    suggestions = []
    if video.category:
        suggestions = (
            Video.query
            .filter(Video.id != video.id, Video.source_type != "disabled", Video.category == video.category)
            .order_by(db.func.random())
            .limit(5)
            .all()
        )
    
    if len(suggestions) < 5:
        needed = 5 - len(suggestions)
        exclude_ids = [video.id] + [s.id for s in suggestions]
        extra = (
            Video.query
            .filter(Video.id.notin_(exclude_ids), Video.source_type != "disabled")
            .order_by(db.func.random())
            .limit(needed)
            .all()
        )
        suggestions.extend(extra)

    return render_template(
        "client/player.html", 
        video=video, 
        playback_url=playback_url, 
        is_embed=is_embed, 
        suggestions=suggestions
    )


@client_bp.route("/play/<int:video_id>")
def play(video_id):
    auth_response = _require_client_page()
    if auth_response:
        return auth_response

    client_id = _require_client()
    video = Video.query.get_or_404(video_id)
    if video.source_type == "embed":
        return redirect(url_for("client.player", video_id=video_id))
    try:
        playback_url = build_video_playback_url(video_id, client_id)
    except ServerSelectionError:
        abort(503)
    return redirect(playback_url, code=302)


@client_bp.route("/playlist.m3u")
def playlist_m3u():
    client_id, auth_response = _authenticated_playlist_client_id()
    if auth_response:
        return auth_response

    active_jellyfin_video_ids = (
        JellyfinItem.query
        .filter_by(is_active=True)
        .with_entities(JellyfinItem.video_id)
        .all()
    )
    jellyfin_ids = {r[0] for r in active_jellyfin_video_ids if r[0]}
    videos = (
        Video.query
        .filter(Video.source_type != "disabled")
        .filter(
            or_(
                Video.source_type != "jellyfin",
                Video.id.in_(jellyfin_ids) if jellyfin_ids else False,
            )
        )
        .order_by(Video.title)
        .all()
    )
    m3u = build_m3u_playlist(client_id, videos)
    return Response(m3u, mimetype="application/vnd.apple.mpegurl",
                    headers={"Content-Disposition": "attachment; filename=playlist.m3u"})


@client_bp.route("/open-jellyfin/<int:video_id>")
def open_jellyfin(video_id):
    auth_response = _require_client_page()
    if auth_response:
        return auth_response

    _require_client()
    video = Video.query.get_or_404(video_id)
    if not video.is_jellyfin or not video.jellyfin_server_id or not video.jellyfin_item_id:
        abort(404)
    server = JellyfinServer.query.get_or_404(video.jellyfin_server_id)
    if not server.is_active:
        abort(503)
    return redirect(f"{server.normalized_base_url}/web/index.html#!/details?id={video.jellyfin_item_id}", code=302)


# ─── Torrent streaming ────────────────────────────────────────────────────────

def _torrent_node_url(path: str, params: dict | None = None) -> str:
    import os
    from urllib.parse import urlencode
    base = os.environ.get("TORRENT_NODE_URL", "http://torrent-node:9119").rstrip("/")
    if params:
        return f"{base}{path}?{urlencode(params)}"
    return f"{base}{path}"


@client_bp.route("/torrent/stream/<int:video_id>")
def torrent_stream(video_id):
    """Proxy de streaming do torrent-node com suporte a Range requests."""
    auth_response = _require_client_page()
    if auth_response:
        return auth_response

    video = Video.query.get_or_404(video_id)
    if video.source_type != "torrent" or not video.source_url:
        abort(404)

    params = {"magnet": video.source_url}
    filename = request.args.get("file")
    if filename:
        params["file"] = filename

    node_url = _torrent_node_url("/stream", params)
    headers = {}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]

    try:
        req = Request(node_url, headers=headers)
        upstream = urlopen(req, timeout=30)
    except URLError as exc:
        return jsonify({"error": f"torrent-node unavailable: {exc}"}), 503

    status = upstream.status
    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    content_range = upstream.headers.get("Content-Range")
    content_length = upstream.headers.get("Content-Length")
    accept_ranges = upstream.headers.get("Accept-Ranges", "bytes")

    resp_headers = {
        "Content-Type": content_type,
        "Accept-Ranges": accept_ranges,
    }
    if content_range:
        resp_headers["Content-Range"] = content_range
    if content_length:
        resp_headers["Content-Length"] = content_length

    def generate():
        try:
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            upstream.close()

    return Response(generate(), status=status, headers=resp_headers)


@client_bp.route("/torrent/info/<int:video_id>")
def torrent_info(video_id):
    """Retorna metadados do torrent via torrent-node."""
    auth_response = _require_client_api()
    if auth_response:
        return auth_response

    video = Video.query.get_or_404(video_id)
    if video.source_type != "torrent" or not video.source_url:
        abort(404)

    try:
        from backend.services.torrent_service import get_torrent_info, TorrentServiceError
        info = get_torrent_info(video.source_url)
        return jsonify(info)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@client_bp.route("/torrent/status")
def torrent_status():
    """Retorna status geral do torrent-node."""
    auth_response = _require_client_api()
    if auth_response:
        return auth_response

    try:
        from backend.services.torrent_service import get_status, TorrentServiceError
        return jsonify(get_status())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503
