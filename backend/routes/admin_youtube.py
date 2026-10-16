"""Rotas admin para o módulo YouTube — /admin/youtube."""

import json
import threading
import uuid
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from backend.extensions import db
from backend.models import YouTubeChannel, YouTubeImportJob

admin_youtube_bp = Blueprint("admin_youtube", __name__, url_prefix="/admin/youtube")

# ---------------------------------------------------------------------------
# Job async (mesmo padrão do scraper existente)
# ---------------------------------------------------------------------------

_youtube_jobs = {}
_youtube_lock = threading.Lock()


def _run_fetch_job(job_id, channel_id, max_results, app):
    """Thread que executa a coleta de vídeos de um canal."""
    from backend.services.youtube_service import YouTubeServiceError, fetch_channel_videos

    with _youtube_lock:
        _youtube_jobs[job_id] = {
            "status": "running",
            "results": [],
            "error": None,
            "channel_id": channel_id,
        }

    try:
        with app.app_context():
            channel = YouTubeChannel.query.get(channel_id)
            if not channel:
                raise YouTubeServiceError("Canal não encontrado")

            # Criar registro do job
            job = YouTubeImportJob(
                channel_id=channel_id,
                status="running",
                started_at=datetime.utcnow(),
            )
            db.session.add(job)
            db.session.commit()
            db_job_id = job.id

            results = fetch_channel_videos(channel.handle, max_results=max_results)

            # Atualizar job
            job = YouTubeImportJob.query.get(db_job_id)
            job.status = "done"
            job.total_found = len(results)
            job.finished_at = datetime.utcnow()

            channel.last_synced_at = datetime.utcnow()
            db.session.commit()

        with _youtube_lock:
            _youtube_jobs[job_id] = {
                "status": "done",
                "results": results,
                "error": None,
                "channel_id": channel_id,
                "db_job_id": db_job_id,
            }
    except YouTubeServiceError as exc:
        with app.app_context():
            try:
                job = YouTubeImportJob.query.filter_by(
                    channel_id=channel_id, status="running"
                ).order_by(YouTubeImportJob.id.desc()).first()
                if job:
                    job.status = "error"
                    job.error_message = str(exc)
                    job.finished_at = datetime.utcnow()
                    db.session.commit()
            except Exception:
                pass

        with _youtube_lock:
            _youtube_jobs[job_id] = {
                "status": "error",
                "results": [],
                "error": str(exc),
                "channel_id": channel_id,
            }
    except Exception as exc:
        with _youtube_lock:
            _youtube_jobs[job_id] = {
                "status": "error",
                "results": [],
                "error": f"Erro inesperado: {exc}",
                "channel_id": channel_id,
            }


# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------

@admin_youtube_bp.route("")
def index():
    channels = YouTubeChannel.query.order_by(YouTubeChannel.name).all()
    recent_jobs = (
        YouTubeImportJob.query
        .order_by(YouTubeImportJob.id.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "admin/youtube/index.html",
        channels=channels,
        recent_jobs=recent_jobs,
    )


# ---------------------------------------------------------------------------
# CRUD de canais
# ---------------------------------------------------------------------------

@admin_youtube_bp.route("/channels/create", methods=["POST"])
def channels_create():
    name = request.form.get("name", "").strip()
    handle = request.form.get("handle", "").strip()

    if not name or not handle:
        flash("Nome e handle são obrigatórios.", "error")
        return redirect(url_for("admin_youtube.index"))

    # Normalizar handle
    if not handle.startswith("@"):
        handle = f"@{handle}"

    if YouTubeChannel.query.filter_by(handle=handle).first():
        flash(f"Canal {handle} já existe.", "error")
        return redirect(url_for("admin_youtube.index"))

    channel = YouTubeChannel(
        name=name,
        handle=handle,
        channel_url=f"https://www.youtube.com/{handle}/videos",
        is_active=True,
    )
    db.session.add(channel)
    db.session.commit()
    flash(f"Canal '{name}' criado com sucesso.", "success")
    return redirect(url_for("admin_youtube.index"))


@admin_youtube_bp.route("/channels/<int:id>/edit", methods=["POST"])
def channels_edit(id):
    channel = YouTubeChannel.query.get_or_404(id)
    name = request.form.get("name", "").strip()
    handle = request.form.get("handle", "").strip()

    if name:
        channel.name = name
    if handle:
        if not handle.startswith("@"):
            handle = f"@{handle}"
        channel.handle = handle
        channel.channel_url = f"https://www.youtube.com/{handle}/videos"

    db.session.commit()
    flash(f"Canal '{channel.name}' atualizado.", "success")
    return redirect(url_for("admin_youtube.index"))


@admin_youtube_bp.route("/channels/<int:id>/toggle", methods=["POST"])
def channels_toggle(id):
    channel = YouTubeChannel.query.get_or_404(id)
    channel.is_active = not channel.is_active
    db.session.commit()
    status = "ativado" if channel.is_active else "desativado"
    flash(f"Canal '{channel.name}' {status}.", "success")
    return redirect(url_for("admin_youtube.index"))


@admin_youtube_bp.route("/channels/<int:id>/delete", methods=["POST"])
def channels_delete(id):
    channel = YouTubeChannel.query.get_or_404(id)
    name = channel.name
    db.session.delete(channel)
    db.session.commit()
    flash(f"Canal '{name}' removido.", "success")
    return redirect(url_for("admin_youtube.index"))


# ---------------------------------------------------------------------------
# Coleta de vídeos (async)
# ---------------------------------------------------------------------------

@admin_youtube_bp.route("/channels/<int:id>/fetch", methods=["POST"])
def channels_fetch(id):
    from flask import current_app

    channel = YouTubeChannel.query.get_or_404(id)
    max_results = min(int(request.form.get("max_results", 50)), 200)
    job_id = str(uuid.uuid4())
    app = current_app._get_current_object()

    t = threading.Thread(
        target=_run_fetch_job,
        args=(job_id, channel.id, max_results, app),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id, "channel_id": channel.id})


@admin_youtube_bp.route("/fetch-status/<job_id>")
def fetch_status(job_id):
    with _youtube_lock:
        job = _youtube_jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job)


# ---------------------------------------------------------------------------
# Importação
# ---------------------------------------------------------------------------

@admin_youtube_bp.route("/import", methods=["POST"])
def import_videos():
    from backend.services.youtube_service import YouTubeServiceError, import_videos as do_import

    raw = request.form.get("results_json", "[]")
    overwrite = request.form.get("overwrite") == "on"

    try:
        videos = json.loads(raw)
    except json.JSONDecodeError:
        flash("JSON inválido.", "error")
        return redirect(url_for("admin_youtube.index"))

    try:
        stats = do_import(videos, overwrite=overwrite)
        flash(
            f"Importação YouTube concluída: {stats['created']} criados, "
            f"{stats['updated']} atualizados, {stats['skipped']} ignorados.",
            "success",
        )
    except YouTubeServiceError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin_youtube.index"))
