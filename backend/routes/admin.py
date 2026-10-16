import json
import threading
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from backend.extensions import db
from backend.models import JellyfinItem, JellyfinLibrary, JellyfinServer, KodiSource, MediaServer, Video, VideoLocation, XtreamUser
from backend.services import jellyfin_service
from backend.services.jellyfin_service import JellyfinServiceError

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
def index():
    return redirect(url_for("admin.media_servers_index"))


@admin_bp.route("/system-stats")
def system_stats():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.2)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return jsonify({
            "cpu_percent": round(cpu, 1),
            "ram_percent": round(ram.percent, 1),
            "ram_used_gb": round(ram.used / 1024 ** 3, 2),
            "ram_total_gb": round(ram.total / 1024 ** 3, 2),
            "disk_percent": round(disk.percent, 1),
            "disk_used_gb": round(disk.used / 1024 ** 3, 1),
            "disk_total_gb": round(disk.total / 1024 ** 3, 1),
        })
    except ImportError:
        return jsonify({"error": "psutil not installed"}), 503
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500



def _bool(name):
    return request.form.get(name) == "on"


def _int(name, default=0):
    raw = request.form.get(name)
    return int(raw) if raw not in (None, "") else default


def _save_media_server(server):
    server.name = request.form["name"]
    server.public_url = request.form["public_url"].rstrip("/")
    server.internal_url = request.form.get("internal_url") or None
    server.region = request.form.get("region") or None
    server.provider = request.form.get("provider") or None
    server.server_type = request.form.get("server_type") or "go-engine"
    server.api_key = request.form.get("api_key", "")
    server.priority = _int("priority", 100)
    server.weight = _int("weight", 1)
    server.max_connections = _int("max_connections", 0)
    server.current_connections = _int("current_connections", 0)
    server.is_active = _bool("is_active")


def _save_video_location(location):
    location.video_id = _int("video_id")
    location.media_server_id = _int("media_server_id")
    server = MediaServer.query.get(location.media_server_id)
    if not server or not server.is_stream_capable:
        abort(400)
    location.storage_path = request.form["storage_path"].lstrip("/")
    location.source_type = request.form.get("source_type") or "hls"
    location.is_primary = _bool("is_primary")
    location.is_active = _bool("is_active")


def _save_jellyfin_server(server):
    server.name = request.form["name"]
    server.base_url = request.form["base_url"].rstrip("/")
    server.internal_url = (request.form.get("internal_url") or "").rstrip("/") or None
    api_key = request.form.get("api_key")
    if api_key:
        server.api_key = api_key
    server.admin_username = request.form.get("admin_username") or None
    server.region = request.form.get("region") or None
    server.priority = _int("priority", 100)
    server.weight = _int("weight", 1)
    server.is_active = _bool("is_active")


def _save_kodi_source(source, default_active=True):
    source_kind = request.form.get("source_kind", KodiSource.KIND_M3U).strip() or KodiSource.KIND_M3U
    if source_kind not in {KodiSource.KIND_M3U, KodiSource.KIND_ADDON}:
        abort(400)

    source.name = request.form.get("name", "").strip()
    source.source_kind = source_kind
    source_url = (
        request.form.get("source_url", "").strip()
        or request.form.get("playlist_url", "").strip()
    )
    source.source_url = source_url or None
    # Para addons locais sem URL, usar addon_id como identificador unico
    addon_id = request.form.get("addon_id", "").strip()
    if source_kind == KodiSource.KIND_ADDON and not source_url and addon_id:
        source.playlist_url = f"addon://{addon_id}"
    else:
        source.playlist_url = source_url
    source.default_category = request.form.get("default_category", "").strip() or None
    source.addon_id = request.form.get("addon_id", "").strip() or None
    source.entry_path = request.form.get("entry_path", "").strip() or None
    source.sync_interval_minutes = _int("sync_interval_minutes", 0) or None
    source.is_active = _bool("is_active") if "is_active" in request.form else default_active


def _validate_kodi_source(source):
    if not source.name:
        return "Nome da fonte e obrigatorio."
    if source.source_kind == KodiSource.KIND_M3U and not source.effective_source_url:
        return "URL da fonte e obrigatoria para fontes M3U."
    if source.source_kind == KodiSource.KIND_ADDON and not source.addon_id:
        return "Addon ID e obrigatorio para fontes Repo/add-on."
    duplicate = (
        KodiSource.query
        .filter(KodiSource.playlist_url == source.playlist_url, KodiSource.id != source.id)
        .first()
    )
    if duplicate:
        return "Ja existe outra fonte Kodi com essa URL."
    return None


def _sync_kodi_source(source, overwrite=False, validate_hls=False, max_depth=4):
    if source.source_kind == KodiSource.KIND_ADDON:
        from backend.services.kodi_addon_service import KodiAddonError, sync_source

        try:
            return sync_source(source, overwrite=overwrite, max_depth=max_depth)
        except KodiAddonError as exc:
            raise RuntimeError(str(exc)) from exc

    from backend.services.kodi_m3u_service import KodiM3UError, sync_source

    try:
        return sync_source(source, overwrite=overwrite, validate_hls=validate_hls)
    except KodiM3UError as exc:
        raise RuntimeError(str(exc)) from exc


def _flash_kodi_sync_result(stats, category="success"):
    flash(
        f"Sync Kodi concluido: {stats.get('created', 0)} criados, "
        f"{stats.get('updated', 0)} atualizados, {stats.get('skipped', 0)} ignorados, "
        f"{stats.get('invalid', 0)} invalidos.",
        category,
    )


@admin_bp.route("/videos")
def videos_index():
    videos = Video.query.order_by(Video.title).all()
    return render_template("admin/videos/index.html", videos=videos)


@admin_bp.route("/videos/embed/create", methods=["GET", "POST"])
def videos_embed_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        embed_url = request.form.get("embed_url", "").strip()
        if not title or not embed_url:
            flash("Título e URL do embed são obrigatórios.", "error")
            return render_template("admin/videos/embed_form.html", video=None)
        category = request.form.get("category", "").strip() or None
        video = Video(title=title, source_url=embed_url, source_type="embed", external_provider="embed", category=category)
        db.session.add(video)
        db.session.commit()
        flash(f"Vídeo embed '{title}' criado.", "success")
        return redirect(url_for("admin.videos_index"))
    return render_template("admin/videos/embed_form.html", video=None)


@admin_bp.route("/videos/embed/<int:id>/edit", methods=["GET", "POST"])
def videos_embed_edit(id):
    video = Video.query.get_or_404(id)
    if video.source_type != "embed":
        abort(400)
    if request.method == "POST":
        video.title = request.form.get("title", "").strip()
        video.source_url = request.form.get("embed_url", "").strip()
        video.category = request.form.get("category", "").strip() or None
        if not video.title or not video.source_url:
            flash("Título e URL do embed são obrigatórios.", "error")
            return render_template("admin/videos/embed_form.html", video=video)
        db.session.commit()
        flash(f"Vídeo embed '{video.title}' atualizado.", "success")
        return redirect(url_for("admin.videos_index"))
    return render_template("admin/videos/embed_form.html", video=video)


@admin_bp.route("/videos/embed/<int:id>/delete", methods=["POST"])
def videos_embed_delete(id):
    video = Video.query.get_or_404(id)
    if video.source_type != "embed":
        abort(400)
    title = video.title
    db.session.delete(video)
    db.session.commit()
    flash(f"Vídeo embed '{title}' removido.", "success")
    return redirect(url_for("admin.videos_index"))


@admin_bp.route("/videos/torrent/create", methods=["GET", "POST"])
def videos_torrent_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        magnet = request.form.get("magnet", "").strip()
        if not title or not magnet:
            flash("Título e magnet/URL do torrent são obrigatórios.", "error")
            return render_template("admin/videos/torrent_form.html", video=None)
        category = request.form.get("category", "").strip() or None
        thumbnail_url = request.form.get("thumbnail_url", "").strip() or None
        synopsis = request.form.get("synopsis", "").strip() or None
        video = Video(
            title=title,
            source_url=magnet,
            source_type="torrent",
            category=category,
            thumbnail_url=thumbnail_url,
            synopsis=synopsis,
        )
        db.session.add(video)
        db.session.commit()
        flash(f"Vídeo torrent '{title}' criado.", "success")
        return redirect(url_for("admin.videos_index"))
    return render_template("admin/videos/torrent_form.html", video=None)


@admin_bp.route("/videos/torrent/<int:id>/edit", methods=["GET", "POST"])
def videos_torrent_edit(id):
    video = Video.query.get_or_404(id)
    if video.source_type != "torrent":
        abort(400)
    if request.method == "POST":
        video.title = request.form.get("title", "").strip()
        video.source_url = request.form.get("magnet", "").strip()
        video.category = request.form.get("category", "").strip() or None
        video.thumbnail_url = request.form.get("thumbnail_url", "").strip() or None
        video.synopsis = request.form.get("synopsis", "").strip() or None
        if not video.title or not video.source_url:
            flash("Título e magnet/URL são obrigatórios.", "error")
            return render_template("admin/videos/torrent_form.html", video=video)
        db.session.commit()
        flash(f"Vídeo torrent '{video.title}' atualizado.", "success")
        return redirect(url_for("admin.videos_index"))
    return render_template("admin/videos/torrent_form.html", video=video)


@admin_bp.route("/videos/torrent/<int:id>/delete", methods=["POST"])
def videos_torrent_delete(id):
    video = Video.query.get_or_404(id)
    if video.source_type != "torrent":
        abort(400)
    title = video.title
    db.session.delete(video)
    db.session.commit()
    flash(f"Vídeo torrent '{title}' removido.", "success")
    return redirect(url_for("admin.videos_index"))


@admin_bp.route("/torrent-node/status")
def torrent_node_status():
    """Status do microserviço torrent-node."""
    try:
        from backend.services.torrent_service import get_status, health_check
        healthy = health_check()
        if not healthy:
            return jsonify({"status": "unreachable", "active": 0, "torrents": []}), 503
        data = get_status()
        data["status"] = "ok"
        return jsonify(data)
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503


@admin_bp.route("/torrent-node/remove", methods=["POST"])
def torrent_node_remove():
    """Remove um torrent ativo do torrent-node."""
    magnet = request.form.get("magnet") or request.json and request.json.get("magnet")
    if not magnet:
        return jsonify({"error": "magnet required"}), 400
    try:
        from backend.services.torrent_service import remove_torrent
        ok = remove_torrent(magnet)
        return jsonify({"ok": ok})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@admin_bp.route("/kodi-sources")
def kodi_sources_index():
    sources = KodiSource.query.order_by(KodiSource.name).all()
    return render_template("admin/kodi_sources/index.html", sources=sources)


@admin_bp.route("/kodi-sources/create", methods=["POST"])
def kodi_sources_create():
    source = KodiSource(is_active=True)
    _save_kodi_source(source)
    error = _validate_kodi_source(source)
    if error:
        flash(error, "error")
        return redirect(url_for("admin.kodi_sources_index"))
    db.session.add(source)
    db.session.commit()
    flash(f"Fonte Kodi '{source.name}' criada.", "success")
    if source.is_active:
        try:
            stats = _sync_kodi_source(source)
            _flash_kodi_sync_result(stats)
        except RuntimeError as exc:
            flash(str(exc), "error")
    return redirect(url_for("admin.kodi_sources_index"))


@admin_bp.route("/kodi-sources/<int:id>/edit", methods=["GET", "POST"])
def kodi_sources_edit(id):
    source = KodiSource.query.get_or_404(id)
    if request.method == "POST":
        _save_kodi_source(source, default_active=False)
        error = _validate_kodi_source(source)
        if error:
            flash(error, "error")
            return render_template("admin/kodi_sources/form.html", source=source)
        db.session.commit()
        flash(f"Fonte Kodi '{source.name}' atualizada.", "success")
        if source.is_active:
            try:
                stats = _sync_kodi_source(source)
                _flash_kodi_sync_result(stats)
            except RuntimeError as exc:
                flash(str(exc), "error")
        return redirect(url_for("admin.kodi_sources_index"))
    return render_template("admin/kodi_sources/form.html", source=source)


@admin_bp.route("/kodi-sources/<int:id>/toggle", methods=["POST"])
def kodi_sources_toggle(id):
    source = KodiSource.query.get_or_404(id)
    source.is_active = not source.is_active
    db.session.commit()
    status = "ativada" if source.is_active else "desativada"
    flash(f"Fonte Kodi '{source.name}' {status}.", "success")
    return redirect(url_for("admin.kodi_sources_index"))


@admin_bp.route("/kodi-sources/<int:id>/delete", methods=["POST"])
def kodi_sources_delete(id):
    source = KodiSource.query.get_or_404(id)
    name = source.name
    db.session.delete(source)
    db.session.commit()
    flash(f"Fonte Kodi '{name}' removida.", "success")
    return redirect(url_for("admin.kodi_sources_index"))


@admin_bp.route("/kodi-sources/<int:id>/sync", methods=["POST"])
def kodi_sources_sync(id):
    source = KodiSource.query.get_or_404(id)
    if not source.is_active:
        flash("Ative a fonte antes de sincronizar.", "error")
        return redirect(url_for("admin.kodi_sources_index"))

    overwrite = request.form.get("overwrite") == "on"
    validate_hls = request.form.get("validate_hls") == "on"
    max_depth = _int("max_depth", 4)
    try:
        stats = _sync_kodi_source(
            source,
            overwrite=overwrite,
            validate_hls=validate_hls,
            max_depth=max_depth,
        )
        _flash_kodi_sync_result(stats)
    except RuntimeError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.kodi_sources_index"))


@admin_bp.route("/media-servers")
def media_servers_index():
    servers = MediaServer.query.order_by(MediaServer.priority, MediaServer.name).all()
    return render_template("admin/media_servers/index.html", servers=servers)


@admin_bp.route("/media-servers/create", methods=["GET", "POST"])
def media_servers_create():
    server = MediaServer(is_active=True, priority=100, weight=1, server_type="go-engine")
    if request.method == "POST":
        _save_media_server(server)
        if server.is_stream_capable and not server.api_key:
            flash("API key obrigatoria para go-engine.", "error")
            return render_template("admin/media_servers/form.html", server=server)
        db.session.add(server)
        db.session.commit()
        flash("Servidor de mídia criado.", "success")
        return redirect(url_for("admin.media_servers_index"))
    return render_template("admin/media_servers/form.html", server=server)


@admin_bp.route("/media-servers/<int:id>/edit", methods=["GET", "POST"])
def media_servers_edit(id):
    server = MediaServer.query.get_or_404(id)
    if request.method == "POST":
        _save_media_server(server)
        if server.is_stream_capable and not server.api_key:
            flash("API key obrigatoria para go-engine.", "error")
            return render_template("admin/media_servers/form.html", server=server)
        db.session.commit()
        flash("Servidor de mídia atualizado.", "success")
        return redirect(url_for("admin.media_servers_index"))
    return render_template("admin/media_servers/form.html", server=server)


@admin_bp.route("/media-servers/<int:id>/health", methods=["POST"])
def media_servers_health(id):
    server = MediaServer.query.get_or_404(id)
    health_url = f"{(server.internal_url or server.public_url).rstrip('/')}/health"
    headers = {}
    if server.is_stream_capable:
        headers["X-API-Key"] = server.api_key
    req = Request(health_url, headers=headers)
    try:
        with urlopen(req, timeout=5) as response:
            server.health_status = "healthy" if response.status == 200 else f"http_{response.status}"
    except URLError:
        server.health_status = "unreachable"
    server.last_health_check = datetime.utcnow()
    db.session.commit()
    flash(f"Health check: {server.health_status}", "info")
    return redirect(url_for("admin.media_servers_index"))


@admin_bp.route("/media-servers/<int:id>/delete", methods=["POST"])
def media_servers_delete(id):
    server = MediaServer.query.get_or_404(id)
    db.session.delete(server)
    db.session.commit()
    flash("Servidor excluído com sucesso.", "success")
    return redirect(url_for("admin.media_servers_index"))


@admin_bp.route("/videos/<int:id>/locations")
def video_locations_index(id):
    video = Video.query.get_or_404(id)
    locations = video.locations.all()
    return render_template("admin/video_locations/index.html", video=video, locations=locations)


@admin_bp.route("/videos/<int:id>/locations/create", methods=["GET", "POST"])
def video_locations_create(id):
    video = Video.query.get_or_404(id)
    location = VideoLocation(video=video, is_active=True, source_type="hls")
    servers = (
        MediaServer.query.filter_by(server_type="go-engine")
        .order_by(MediaServer.priority, MediaServer.name)
        .all()
    )
    if request.method == "POST":
        _save_video_location(location)
        db.session.add(location)
        db.session.commit()
        flash("Localização criada.", "success")
        return redirect(url_for("admin.video_locations_index", id=video.id))
    return render_template("admin/video_locations/form.html", video=video, location=location, servers=servers)


@admin_bp.route("/video-locations/<int:id>/edit", methods=["GET", "POST"])
def video_locations_edit(id):
    location = VideoLocation.query.get_or_404(id)
    video = location.video
    servers = (
        MediaServer.query.filter_by(server_type="go-engine")
        .order_by(MediaServer.priority, MediaServer.name)
        .all()
    )
    if request.method == "POST":
        _save_video_location(location)
        db.session.commit()
        flash("Localização atualizada.", "success")
        return redirect(url_for("admin.video_locations_index", id=video.id))
    return render_template("admin/video_locations/form.html", video=video, location=location, servers=servers)


@admin_bp.route("/video-locations/<int:id>/delete", methods=["POST"])
def video_locations_delete(id):
    location = VideoLocation.query.get_or_404(id)
    video_id = location.video_id
    db.session.delete(location)
    db.session.commit()
    flash("Localização removida.", "success")
    return redirect(url_for("admin.video_locations_index", id=video_id))


@admin_bp.route("/jellyfin-servers")
def jellyfin_servers_index():
    servers = JellyfinServer.query.order_by(JellyfinServer.priority, JellyfinServer.name).all()
    return render_template("admin/jellyfin_servers/index.html", servers=servers)


@admin_bp.route("/jellyfin-servers/create", methods=["GET", "POST"])
def jellyfin_servers_create():
    server = JellyfinServer(is_active=True, priority=100, weight=1)
    if request.method == "POST":
        _save_jellyfin_server(server)
        if not server.api_key:
            flash("API key é obrigatória.", "error")
            return render_template("admin/jellyfin_servers/form.html", server=server)
        db.session.add(server)
        db.session.commit()
        flash("Servidor Jellyfin criado.", "success")
        return redirect(url_for("admin.jellyfin_servers_index"))
    return render_template("admin/jellyfin_servers/form.html", server=server)


@admin_bp.route("/jellyfin-servers/<int:id>/edit", methods=["GET", "POST"])
def jellyfin_servers_edit(id):
    server = JellyfinServer.query.get_or_404(id)
    if request.method == "POST":
        _save_jellyfin_server(server)
        db.session.commit()
        flash("Servidor Jellyfin atualizado.", "success")
        return redirect(url_for("admin.jellyfin_servers_index"))
    return render_template("admin/jellyfin_servers/form.html", server=server)


@admin_bp.route("/jellyfin-servers/<int:id>/health", methods=["POST"])
def jellyfin_servers_health(id):
    server = JellyfinServer.query.get_or_404(id)
    try:
        info = jellyfin_service.get_system_info(server)
        server.health_status = "healthy" if info else "unknown"
    except JellyfinServiceError as exc:
        server.health_status = "unreachable"
        flash(str(exc), "error")
    server.last_health_check = datetime.utcnow()
    db.session.commit()
    flash(f"Health Jellyfin: {server.health_status}", "info")
    return redirect(url_for("admin.jellyfin_servers_index"))


@admin_bp.route("/jellyfin-servers/<int:id>/sync-libraries", methods=["POST"])
def jellyfin_servers_sync_libraries(id):
    server = JellyfinServer.query.get_or_404(id)
    try:
        libraries = jellyfin_service.sync_libraries(server)
        flash(f"{len(libraries)} bibliotecas sincronizadas.", "success")
    except JellyfinServiceError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.jellyfin_servers_index"))


@admin_bp.route("/jellyfin-servers/<int:id>/sync-items", methods=["POST"])
def jellyfin_servers_sync_items(id):
    import logging
    server = JellyfinServer.query.get_or_404(id)
    library_id = request.form.get("library_id")
    libraries = [JellyfinLibrary.query.get(library_id)] if library_id else server.libraries.filter_by(is_active=True).all()
    total = 0
    try:
        for library in [library for library in libraries if library]:
            logging.warning(f"[SYNC] Library: {library.name} ({library.jellyfin_library_id})")
            items = jellyfin_service.sync_items(server, library.jellyfin_library_id)
            logging.warning(f"[SYNC] Items synced: {len(items)}")
            total += len(items)
        flash(f"{total} itens sincronizados.", "success")
    except Exception as exc:
        logging.error(f"[SYNC] Error: {type(exc).__name__}: {exc}")
        flash(f"{type(exc).__name__}: {exc}", "error")
    return redirect(url_for("admin.jellyfin_servers_index"))


@admin_bp.route("/jellyfin-items")
def jellyfin_items_index():
    query = JellyfinItem.query.join(JellyfinItem.jellyfin_server)
    server_id = request.args.get("server_id")
    active = request.args.get("active")
    if server_id:
        query = query.filter(JellyfinItem.jellyfin_server_id == int(server_id))
    if active == "yes":
        query = query.filter(JellyfinItem.is_active.is_(True))
    elif active == "no":
        query = query.filter(JellyfinItem.is_active.is_(False))
    items = query.order_by(JellyfinItem.name).limit(500).all()
    servers = JellyfinServer.query.order_by(JellyfinServer.name).all()
    return render_template("admin/jellyfin_items/index.html", items=items, servers=servers)


@admin_bp.route("/jellyfin-items/<int:id>/toggle", methods=["POST"])
def jellyfin_items_toggle(id):
    item = JellyfinItem.query.get_or_404(id)
    item.is_active = not item.is_active
    if item.video:
        item.video.source_type = "jellyfin" if item.is_active else "disabled"
    db.session.commit()
    status = "ativado" if item.is_active else "desativado"
    flash(f"'{item.name}' {status}.", "success")
    return redirect(url_for("admin.jellyfin_items_index"))


_scraper_jobs = {}
_scraper_lock = threading.Lock()

_megaembed_jobs = {}
_megaembed_lock = threading.Lock()


def _run_scraper_job(job_id, category, max_pages, app):
    from backend.services.scraper_service import ScraperError, scrape_category
    with _scraper_lock:
        _scraper_jobs[job_id] = {"status": "running", "results": [], "error": None}
    try:
        with app.app_context():
            results = scrape_category(category, max_pages=max_pages)
        with _scraper_lock:
            _scraper_jobs[job_id] = {"status": "done", "results": results, "error": None}
    except ScraperError as exc:
        with _scraper_lock:
            _scraper_jobs[job_id] = {"status": "error", "results": [], "error": str(exc)}
    except Exception as exc:
        with _scraper_lock:
            _scraper_jobs[job_id] = {"status": "error", "results": [], "error": f"Erro inesperado: {exc}"}


@admin_bp.route("/scraper")
def scraper_index():
    from backend.services.scraper_service import CATEGORY_URLS
    category_labels = {
        "homepage": "Homepage (tudo)",
        "filmes": "Filmes",
        "series": "Séries",
        "canais": "Canais",
        "animes": "Animes",
        "infantil": "Infantil",
    }
    categories = [
        {"value": k, "label": category_labels.get(k, k.capitalize())}
        for k in CATEGORY_URLS.keys()
    ]
    return render_template("admin/scraper/index.html", categories=categories)


@admin_bp.route("/scraper/run", methods=["POST"])
def scraper_run():
    from flask import current_app
    import uuid
    category = request.form.get("category", "filmes")
    max_pages = min(int(request.form.get("max_pages", 3)), 20)
    job_id = str(uuid.uuid4())
    app = current_app._get_current_object()
    t = threading.Thread(target=_run_scraper_job, args=(job_id, category, max_pages, app), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@admin_bp.route("/scraper/status/<job_id>")
def scraper_status(job_id):
    with _scraper_lock:
        job = _scraper_jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job)


@admin_bp.route("/scraper/import", methods=["POST"])
def scraper_import():
    from backend.services.scraper_service import ScraperError, import_results
    raw = request.form.get("results_json", "[]")
    overwrite = request.form.get("overwrite") == "on"
    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        flash("JSON inválido.", "error")
        return redirect(url_for("admin.scraper_index"))
    try:
        stats = import_results(results, overwrite=overwrite)
        flash(
            f"Importação concluída: {stats['created']} criados, "
            f"{stats['updated']} atualizados, {stats['skipped']} ignorados.",
            "success",
        )
    except ScraperError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.videos_index"))


@admin_bp.route("/reidoscanais")
def reidoscanais_index():
    from backend.services.reidoscanais_api_service import (
        ReidosCanaisAPIError,
        list_channel_categories,
        list_sports_categories,
    )

    channel_categories = []
    sports_categories = []
    try:
        channel_categories = list_channel_categories()
        sports_categories = list_sports_categories()
    except ReidosCanaisAPIError as exc:
        flash(str(exc), "error")

    return render_template(
        "admin/reidoscanais/index.html",
        channel_categories=channel_categories,
        sports_categories=sports_categories,
    )


def _run_megaembed_job(job_id, kwargs, app):
    from backend.services.megaembed_service import MegaEmbedError, import_available_ids

    def _on_progress(payload):
        with _megaembed_lock:
            entry = _megaembed_jobs.get(job_id)
            if entry is None:
                return
            entry["progress"] = payload

    kwargs["progress_callback"] = _on_progress

    with _megaembed_lock:
        _megaembed_jobs[job_id] = {
            "status": "running",
            "stats": None,
            "error": None,
            "progress": {"stage": "starting", "stats": {}},
        }
    try:
        with app.app_context():
            stats = import_available_ids(**kwargs)
        with _megaembed_lock:
            current = _megaembed_jobs.get(job_id) or {}
            _megaembed_jobs[job_id] = {
                "status": "done",
                "stats": stats,
                "error": None,
                "progress": current.get("progress"),
            }
    except MegaEmbedError as exc:
        with _megaembed_lock:
            current = _megaembed_jobs.get(job_id) or {}
            _megaembed_jobs[job_id] = {
                "status": "error",
                "stats": None,
                "error": str(exc),
                "progress": current.get("progress"),
            }
    except Exception as exc:
        with _megaembed_lock:
            current = _megaembed_jobs.get(job_id) or {}
            _megaembed_jobs[job_id] = {
                "status": "error",
                "stats": None,
                "error": f"Erro inesperado: {exc}",
                "progress": current.get("progress"),
            }


@admin_bp.route("/megaembed/run", methods=["POST"])
def megaembed_run():
    import uuid
    from flask import current_app
    job_id = str(uuid.uuid4())

    raw_delay = request.form.get("request_delay", "").strip()
    try:
        request_delay = max(0.0, float(raw_delay)) if raw_delay else 0.5
    except ValueError:
        request_delay = 0.5

    raw_limit = request.form.get("series_limit", "").strip()
    try:
        series_limit = int(raw_limit) if raw_limit else 25
    except ValueError:
        series_limit = 25
    if series_limit <= 0:
        series_limit = None

    raw_offset = request.form.get("series_offset", "").strip()
    try:
        series_offset = max(0, int(raw_offset)) if raw_offset else 0
    except ValueError:
        series_offset = 0

    kwargs = {
        "include_movies": request.form.get("include_movies") == "on",
        "include_series": request.form.get("include_series") == "on",
        "season": _int("bulk_season", 1),
        "episode": _int("bulk_episode", 1),
        "overwrite": request.form.get("bulk_overwrite") == "on",
        "series_offset": series_offset,
        "series_limit": series_limit,
        "request_delay": request_delay,
    }
    app = current_app._get_current_object()
    t = threading.Thread(target=_run_megaembed_job, args=(job_id, kwargs, app), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@admin_bp.route("/megaembed/status/<job_id>")
def megaembed_status(job_id):
    with _megaembed_lock:
        job = _megaembed_jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job)


@admin_bp.route("/megaembed", methods=["GET", "POST"])
def megaembed_index():
    from backend.services.megaembed_service import MegaEmbedError, build_embed_url, import_embed

    form = {
        "title": "",
        "media_type": "movie",
        "id_type": "tmdb",
        "external_id": "",
        "season": "",
        "episode": "",
        "audio": "dubbed",
        "category": "",
        "overwrite": False,
    }
    preview_url = ""

    if request.method == "POST":
        form.update(
            {
                "title": request.form.get("title", "").strip(),
                "media_type": request.form.get("media_type", "movie"),
                "id_type": request.form.get("id_type", "tmdb"),
                "external_id": request.form.get("external_id", "").strip(),
                "season": request.form.get("season", "").strip(),
                "episode": request.form.get("episode", "").strip(),
                "audio": request.form.get("audio", "dubbed"),
                "category": request.form.get("category", "").strip(),
                "overwrite": request.form.get("overwrite") == "on",
            }
        )
        try:
            preview_url = build_embed_url(
                form["media_type"],
                form["external_id"],
                season=form["season"],
                episode=form["episode"],
                id_type=form["id_type"],
                audio=form["audio"],
            )
            if request.form.get("action") == "preview":
                flash("URL MegaEmbed gerada para conferencia.", "info")
            else:
                video, status = import_embed(form, overwrite=form["overwrite"])
                if status == "created":
                    flash(f"MegaEmbed '{video.title}' importado.", "success")
                elif status == "updated":
                    flash(f"MegaEmbed '{video.title}' atualizado.", "success")
                else:
                    flash(f"MegaEmbed '{video.title}' ja existia. Nada alterado.", "info")
                return redirect(url_for("admin.videos_index"))
        except MegaEmbedError as exc:
            flash(str(exc), "error")

    return render_template(
        "admin/megaembed/index.html",
        form=form,
        preview_url=preview_url,
    )


@admin_bp.route("/reidoscanais/fetch", methods=["POST"])
def reidoscanais_fetch():
    from backend.services.reidoscanais_api_service import ReidosCanaisAPIError, fetch_items

    try:
        items = fetch_items(
            source=request.form.get("source", "channels"),
            category=request.form.get("category", ""),
            status=request.form.get("status", ""),
            query=request.form.get("query", ""),
        )
    except ReidosCanaisAPIError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"items": items, "total": len(items)})


@admin_bp.route("/reidoscanais/import", methods=["POST"])
def reidoscanais_import():
    from backend.services.reidoscanais_api_service import import_items

    raw = request.form.get("items_json", "[]")
    overwrite = request.form.get("overwrite") == "on"
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        flash("JSON invÃ¡lido.", "error")
        return redirect(url_for("admin.reidoscanais_index"))

    stats = import_items(items, overwrite=overwrite)
    flash(
        f"ImportaÃ§Ã£o ReidosCanais concluÃ­da: {stats['created']} criados, "
        f"{stats['updated']} atualizados, {stats['skipped']} ignorados.",
        "success",
    )
    return redirect(url_for("admin.videos_index"))


VOD_STRATEGIES = [
    {
        "key": "priority_fallback",
        "label": "Prioridade com fallback",
        "icon": "shield",
        "description": (
            "Usa o servidor primário com menor prioridade numérica. "
            "Se ele estiver lotado ou inativo, cai automaticamente para o próximo."
        ),
        "best_for": "Cenário padrão com servidor principal + réplicas de backup.",
    },
    {
        "key": "primary_first",
        "label": "Primário primeiro",
        "icon": "star",
        "description": (
            "Sempre prefere localizações marcadas como primárias. "
            "Útil quando existe um servidor mestre que deve ser usado sempre que possível."
        ),
        "best_for": "Servidor mestre dedicado, com réplicas só em emergência.",
    },
    {
        "key": "weighted_random",
        "label": "Aleatório ponderado",
        "icon": "shuffle",
        "description": (
            "Sorteia o servidor proporcionalmente ao peso (weight) de cada localização. "
            "Distribui a carga sem hot-spots."
        ),
        "best_for": "Cluster com servidores de capacidades diferentes.",
    },
    {
        "key": "lowest_connections",
        "label": "Menos conexões",
        "icon": "activity",
        "description": (
            "Envia novos clientes ao servidor com menor número de conexões ativas. "
            "Equaliza a carga em tempo real."
        ),
        "best_for": "Picos de audiência ao vivo / streams longas.",
    },
]

LIVE_STRATEGIES = [
    {
        "key": "round_robin",
        "label": "Round Robin",
        "icon": "repeat",
        "description": "Distribui as conexões em ordem circular, igualmente entre todos os servidores saudáveis.",
        "best_for": "Cluster homogêneo (mesma capacidade).",
    },
    {
        "key": "weighted",
        "label": "Ponderado",
        "icon": "bar-chart-2",
        "description": "Usa a prioridade como peso: servidores com priority maior recebem mais conexões.",
        "best_for": "Cluster heterogêneo com servidores mais potentes.",
    },
    {
        "key": "least_connections",
        "label": "Menos conexões",
        "icon": "activity",
        "description": "Sempre envia para o servidor com o menor número de conexões ativas.",
        "best_for": "Streams ao vivo com sessões longas.",
    },
    {
        "key": "random",
        "label": "Aleatório",
        "icon": "shuffle",
        "description": "Escolhe um servidor saudável aleatoriamente. Simples e eficaz para testes.",
        "best_for": "Ambientes de teste / staging.",
    },
    {
        "key": "health_based",
        "label": "Baseado em saúde",
        "icon": "heart",
        "description": "Combina latência medida e carga atual para escolher o melhor servidor disponível.",
        "best_for": "Produção crítica com health-check ativo.",
    },
]


@admin_bp.route("/load-balancer", methods=["GET", "POST"])
def load_balancer_settings():
    from flask import current_app

    from backend.models import MediaServer, StreamingServer
    from backend.services import (
        KEY_LIVE_STRATEGY,
        KEY_VOD_STRATEGY,
        get_setting,
        set_setting,
    )
    from backend.services.load_balancer_service import LoadBalancerService
    from backend.services.server_selector import DEFAULT_STRATEGY as VOD_DEFAULT
    from backend.services.server_selector import STRATEGIES as VOD_STRATEGY_MAP

    vod_keys = set(VOD_STRATEGY_MAP.keys())
    live_keys = set(LoadBalancerService.STRATEGIES)

    if request.method == "POST":
        new_vod = request.form.get("vod_strategy", "").strip()
        new_live = request.form.get("live_strategy", "").strip()
        if new_vod not in vod_keys:
            flash("Estratégia VOD inválida.", "error")
            return redirect(url_for("admin.load_balancer_settings"))
        if new_live not in live_keys:
            flash("Estratégia Live inválida.", "error")
            return redirect(url_for("admin.load_balancer_settings"))
        set_setting(KEY_VOD_STRATEGY, new_vod)
        set_setting(KEY_LIVE_STRATEGY, new_live)
        flash("Configuração do balanceador atualizada.", "success")
        return redirect(url_for("admin.load_balancer_settings"))

    current_vod = get_setting(KEY_VOD_STRATEGY) or current_app.config.get(
        "SERVER_SELECTION_STRATEGY", VOD_DEFAULT
    )
    current_live = get_setting(KEY_LIVE_STRATEGY) or "round_robin"

    media_servers = MediaServer.query.order_by(MediaServer.priority, MediaServer.name).all()
    try:
        live_servers = StreamingServer.query.order_by(StreamingServer.priority).all()
    except Exception:
        live_servers = []

    stats = {
        "total_media": len(media_servers),
        "active_media": sum(1 for s in media_servers if s.is_active),
        "total_live": len(live_servers),
        "active_live": sum(1 for s in live_servers if getattr(s, "is_active", False)),
    }

    return render_template(
        "admin/load_balancer/index.html",
        vod_strategies=VOD_STRATEGIES,
        live_strategies=LIVE_STRATEGIES,
        current_vod=current_vod,
        current_live=current_live,
        media_servers=media_servers,
        live_servers=live_servers,
        stats=stats,
    )


@admin_bp.route("/reidoscanais/convert", methods=["POST"])
def reidoscanais_convert():
    from backend.services.reidoscanais_api_service import convert_existing_embeds_to_streams

    stats = convert_existing_embeds_to_streams()
    flash(
        f"Conversao ReidosCanais concluida: {stats['converted']} convertidos, "
        f"{stats['unchanged']} ja diretos, {stats['failed']} sem stream direto valido.",
        "success",
    )
    return redirect(url_for("admin.reidoscanais_index"))
