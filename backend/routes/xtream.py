import base64
import ssl
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from flask import Blueprint, Response, current_app, jsonify, request, session

from backend.services import xtream_service
from backend.services.xtream_auth_service import authenticate, create_default_response
from backend.models import XtreamUser

xtream_bp = Blueprint("xtream", __name__)


def _get_client_id():
    """Gera ou retorna ID único do cliente."""
    client_id = session.get("client_id")
    if not client_id:
        import uuid
        client_id = str(uuid.uuid4())[:8]
        session["client_id"] = client_id
    return client_id


def _xtream_param(name, default=""):
    data = request.get_json(silent=True) if request.is_json else None
    if isinstance(data, dict) and data.get(name) is not None:
        return str(data.get(name, default))
    return request.values.get(name, default)


def _get_auth_user():
    """Autentica usuário via query params username/password."""
    username = _xtream_param("username", "").strip()
    password = _xtream_param("password", "").strip()
    
    if not username or not password:
        return None
    
    return authenticate(username, password)


def _get_path_auth_user(username, password):
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return None
    return authenticate(username, password)


def _internal_engine_url(public_url):
    stream_public_url = current_app.config.get("STREAM_PUBLIC_URL", "").rstrip("/")
    engine_internal_url = current_app.config.get("ENGINE_INTERNAL_URL", "").rstrip("/")
    if stream_public_url and engine_internal_url and public_url.startswith(stream_public_url + "/"):
        return engine_internal_url + public_url[len(stream_public_url):]
    return public_url


def _proxy_stream_url(stream_url):
    target_url = _internal_engine_url(stream_url)
    headers = {"User-Agent": request.headers.get("User-Agent", "TribbleTV-Xtream")}
    req = Request(target_url, headers=headers)
    try:
        with urlopen(req, timeout=30) as upstream:
            body = upstream.read()
            content_type = upstream.headers.get("Content-Type") or "application/octet-stream"
            response = Response(body, status=upstream.status, mimetype=content_type)
            for header in ("Cache-Control", "ETag", "Last-Modified"):
                value = upstream.headers.get(header)
                if value:
                    response.headers[header] = value
            return response
    except URLError:
        return jsonify({"error": "stream fetch failed"}), 502


def _external_request_headers(target_url):
    parsed = urlparse(target_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    headers = {"User-Agent": request.headers.get("User-Agent", "Mozilla/5.0")}
    if origin:
        headers["Referer"] = origin + "/"
        headers["Origin"] = origin
    return headers


def _fetch_external_url(target_url):
    req = Request(target_url, headers=_external_request_headers(target_url))
    context = ssl._create_unverified_context()
    with urlopen(req, timeout=30, context=context) as upstream:
        return upstream.read(), upstream.headers.get("Content-Type") or "", upstream.status, upstream.url


def _encode_live_asset(target_url):
    return base64.urlsafe_b64encode(target_url.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_live_asset(encoded_url):
    padding = "=" * (-len(encoded_url) % 4)
    return base64.urlsafe_b64decode((encoded_url + padding).encode("ascii")).decode("utf-8")


def _proxied_live_asset_url(username, password, stream_id, target_url):
    return f"/live-segment/{username}/{password}/{stream_id}/{_encode_live_asset(target_url)}"


def _is_playlist(target_url, content_type=""):
    parsed = urlparse(target_url)
    return parsed.path.lower().endswith(".m3u8") or "mpegurl" in (content_type or "").lower()


def _rewrite_live_playlist(playlist, playlist_url, username, password, stream_id):
    lines = []
    for line in playlist.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            lines.append(line)
            continue
        target_url = urljoin(playlist_url, trimmed)
        lines.append(_proxied_live_asset_url(username, password, stream_id, target_url))
    return "\n".join(lines) + "\n"


@xtream_bp.route("/player_api.php", methods=["GET", "POST"])
def player_api():
    """Endpoint principal da API Xtream Codes."""
    action = _xtream_param("action", "").strip()
    user = _get_auth_user()
    client_id = _get_client_id()
    
    # Se não autenticado, retorna erro
    if not user:
        return jsonify(create_default_response(None))
    
    # Ações específicas
    if action == "get_live_categories":
        return jsonify(xtream_service.get_live_categories())

    if action in {"get_live_streams", "202"}:
        category_id = _xtream_param("category_id", "").strip()
        return jsonify(xtream_service.get_live_streams(user.username, _xtream_param("password", ""), category_id))

    if action in {"get_live_info", "get_short_epg", "get_simple_data_table"}:
        stream_id = _xtream_param("stream_id", "").strip()
        if not stream_id or not stream_id.isdigit():
            return jsonify({"error": "invalid stream_id"}), 400
        info = xtream_service.get_live_stream_info(int(stream_id), user.username, _xtream_param("password", ""))
        if not info:
            return jsonify({"error": "not found"}), 404
        if action == "get_live_info":
            return jsonify(info)
        return jsonify({"epg_listings": []})

    if action == "get_vod_categories":
        return jsonify(xtream_service.get_vod_categories())
    
    if action == "get_vod_streams":
        category_id = _xtream_param("category_id", "").strip()
        return jsonify(xtream_service.get_vod_streams(client_id, category_id))
    
    if action == "get_vod_info":
        vod_id = _xtream_param("vod_id", "").strip()
        if not vod_id or not vod_id.isdigit():
            return jsonify({"error": "invalid vod_id"}), 400
        info = xtream_service.get_vod_info(int(vod_id), client_id)
        if not info:
            return jsonify({"error": "not found"}), 404
        return jsonify(info)
    
    # Resposta padrão (info do usuário + servidor)
    return jsonify(create_default_response(user))


@xtream_bp.route("/panel_api.php", methods=["GET", "POST"])
def panel_api():
    """Endpoint do painel administrativo (XC API)."""
    # Mesma lógica do player_api para compatibilidade
    return player_api()


@xtream_bp.route("/get.php")
def get_playlist():
    """Retorna playlist M3U."""
    user = _get_auth_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    
    client_id = _get_client_id()
    from backend.services.playlist_service import build_m3u_playlist
    from backend.models import JellyfinItem, Video
    
    # Buscar apenas vídeos ativos
    active_ids = [r[0] for r in JellyfinItem.query.filter_by(is_active=True).with_entities(JellyfinItem.video_id).all() if r[0]]
    videos = Video.query.filter(Video.id.in_(active_ids)).order_by(Video.title).all()
    m3u = build_m3u_playlist(client_id, videos)
    
    from flask import Response
    return Response(m3u, mimetype="application/vnd.apple.mpegurl")


@xtream_bp.route("/movie/<username>/<password>/<path:stream_file>")
def movie_stream(username, password, stream_file):
    """Compatibilidade Xtream: /movie/user/pass/stream_id.ext."""
    user = _get_path_auth_user(username, password)
    if not user:
        return jsonify({"error": "authentication required"}), 401

    stream_id = stream_file.rsplit(".", 1)[0]
    if not stream_id.isdigit():
        return jsonify({"error": "invalid stream_id"}), 400

    client_id = _get_client_id()
    stream_url = xtream_service.stream_url_for_video_id(int(stream_id), client_id)
    if not stream_url:
        return jsonify({"error": "not found"}), 404
    return _proxy_stream_url(stream_url)


@xtream_bp.route("/live/<username>/<password>/<path:stream_file>")
def live_stream(username, password, stream_file):
    """Compatibilidade Xtream: /live/user/pass/stream_id.ext para embeds ReidosCanais."""
    user = _get_path_auth_user(username, password)
    if not user:
        return jsonify({"error": "authentication required"}), 401

    stream_id = stream_file.rsplit(".", 1)[0]
    if not stream_id.isdigit():
        return jsonify({"error": "invalid stream_id"}), 400

    source_url = xtream_service.live_source_url_for_video_id(int(stream_id))
    if not source_url:
        return jsonify({"error": "live source not resolved"}), 502

    try:
        body, content_type, status, final_url = _fetch_external_url(source_url)
    except URLError:
        return jsonify({"error": "live source fetch failed"}), 502
    if status < 200 or status >= 300:
        return jsonify({"error": "live source fetch failed"}), 502

    if _is_playlist(final_url, content_type):
        rewritten = _rewrite_live_playlist(body.decode("utf-8", "ignore"), final_url, username, password, stream_id)
        return Response(rewritten, mimetype="application/vnd.apple.mpegurl")
    return Response(body, content_type=content_type or "application/octet-stream")


@xtream_bp.route("/live-segment/<username>/<password>/<stream_id>/<encoded_url>")
def live_segment(username, password, stream_id, encoded_url):
    """Proxy de variants/segmentos HLS externos para evitar certificado/CORS do host de origem."""
    user = _get_path_auth_user(username, password)
    if not user:
        return jsonify({"error": "authentication required"}), 401
    if not stream_id.isdigit():
        return jsonify({"error": "invalid stream_id"}), 400
    if not xtream_service.live_source_url_for_video_id(int(stream_id)):
        return jsonify({"error": "not found"}), 404

    try:
        target_url = _decode_live_asset(encoded_url)
    except (ValueError, UnicodeDecodeError):
        return jsonify({"error": "invalid segment"}), 400

    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return jsonify({"error": "invalid segment target"}), 400

    try:
        body, content_type, status, final_url = _fetch_external_url(target_url)
    except URLError:
        return jsonify({"error": "live segment fetch failed"}), 502
    if status < 200 or status >= 300:
        return jsonify({"error": "live segment fetch failed"}), 502

    if _is_playlist(final_url, content_type):
        rewritten = _rewrite_live_playlist(body.decode("utf-8", "ignore"), final_url, username, password, stream_id)
        return Response(rewritten, mimetype="application/vnd.apple.mpegurl")
    return Response(body, content_type=content_type or "application/octet-stream")
