"""Serviço de importação YouTube para TribbleTV.

Usa yt-dlp como CLI para extrair metadata pública dos vídeos
de canais YouTube, sem download de mídia.
"""

import json
import logging
import re
import subprocess

from backend.extensions import db
from backend.models import Video

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapa de categorias por keywords
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "Terror": [
        "terror", "horror", "assombr", "sobrenatural", "zumbi", "zombie",
        "monstro", "demon", "possu", "macabr", "sinistro", "pesadelo",
        "slasher", "gore", "sangrento", "fantasma",
    ],
    "Ação": [
        "ação", "acao", "action", "luta", "combate", "guerra", "war",
        "explosão", "explosao", "tiro", "perseguição", "perseguicao",
        "batalha", "arma", "missão", "missao",
    ],
    "Comédia": [
        "comédia", "comedia", "comedy", "humor", "engraçad", "engracad",
        "riso", "piada", "comica", "cômico", "comico", "diversão", "diversao",
    ],
    "Drama": [
        "drama", "dramát", "dramat", "emocionante", "trágic", "tragic",
        "sentimento", "conflito", "superação", "superacao",
    ],
    "Romance": [
        "romance", "romântic", "romantic", "amor", "paixão", "paixao",
        "casal", "namoro",
    ],
    "Suspense": [
        "suspense", "thriller", "mistério", "misterio", "enigma",
        "investigação", "investigacao", "detetive", "crime", "assassin",
        "policial", "noir",
    ],
    "Faroeste": [
        "faroeste", "western", "velho oeste", "cowboy", "bangue-bangue",
        "bang bang", "pistoleiro",
    ],
    "Ficção Científica": [
        "ficção científica", "ficcao cientifica", "sci-fi", "scifi",
        "ficção", "ficcao", "espacial", "alienígena", "alienigena",
        "futurista", "robô", "robo", "distopia", "nave espacial",
    ],
    "Documentário": [
        "documentário", "documentario", "documentary", "documental",
        "vida real", "realidade", "biografia",
    ],
    "Infantil": [
        "infantil", "criança", "crianca", "kids", "animação infantil",
        "desenho", "cartoon", "family", "familiar",
    ],
    "Aventura": [
        "aventura", "adventure", "exploração", "exploracao",
        "jornada", "expedição", "expedicao", "pirata",
    ],
    "Animação": [
        "animação", "animacao", "animation", "animated", "anime",
        "desenho animado",
    ],
}

# Ordem de prioridade na detecção (gêneros mais específicos primeiro)
CATEGORY_PRIORITY = [
    "Terror", "Ficção Científica", "Faroeste", "Documentário",
    "Infantil", "Animação", "Suspense", "Romance", "Comédia",
    "Aventura", "Ação", "Drama",
]


class YouTubeServiceError(Exception):
    """Erro ao interagir com o serviço YouTube."""


# ---------------------------------------------------------------------------
# Categorização
# ---------------------------------------------------------------------------

def detect_category(title, description="", tags=None, playlist_title=""):
    """Detecta categoria/gênero de um vídeo baseado em metadata.

    Prioridade:
      1. playlist_title (shelf / playlist do canal)
      2. keywords em title + description + tags
      3. Fallback: 'Filmes'
    """
    tags = tags or []
    search_fields = [
        (playlist_title or "").lower(),
        (title or "").lower(),
        (description or "").lower(),
        " ".join(t.lower() for t in tags),
    ]
    combined = " ".join(search_fields)

    for category in CATEGORY_PRIORITY:
        keywords = CATEGORY_KEYWORDS[category]
        for keyword in keywords:
            if keyword in combined:
                return category

    return "Filmes"


# ---------------------------------------------------------------------------
# Coleta de vídeos via yt-dlp
# ---------------------------------------------------------------------------

def fetch_channel_videos(channel_handle, max_results=50):
    """Coleta lista de vídeos de um canal YouTube usando yt-dlp.

    Retorna lista de dicts com metadata simplificada.
    Não baixa nenhum vídeo — apenas extrai informações.
    """
    url = f"https://www.youtube.com/{channel_handle}/videos"

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--no-download",
        "--playlist-end", str(max_results),
        "--extractor-args", "youtube:lang=pt",
        url,
    ]

    logger.info("[YouTube] Buscando vídeos de %s (max %d)...", channel_handle, max_results)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise YouTubeServiceError(
            "yt-dlp não encontrado. Instale com: pip install yt-dlp"
        )
    except subprocess.TimeoutExpired:
        raise YouTubeServiceError(
            f"Timeout ao buscar vídeos de {channel_handle} (120s)"
        )

    if result.returncode != 0 and not result.stdout.strip():
        stderr = (result.stderr or "").strip()
        raise YouTubeServiceError(f"yt-dlp erro: {stderr[:500]}")

    videos = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        video_id = data.get("id") or data.get("url", "")
        if not video_id or len(video_id) < 5:
            continue

        title = data.get("title") or ""
        if title in ("[Private video]", "[Deleted video]"):
            continue

        description = data.get("description") or ""
        tags = data.get("tags") or []
        playlist_title = data.get("playlist_title") or ""
        thumbnail = (
            data.get("thumbnail")
            or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        )
        duration = data.get("duration")

        category = detect_category(title, description, tags, playlist_title)

        videos.append({
            "video_id": video_id,
            "title": title,
            "description": description[:500] if description else "",
            "thumbnail": thumbnail,
            "duration": duration,
            "tags": tags[:20] if tags else [],
            "upload_date": data.get("upload_date") or "",
            "playlist_title": playlist_title,
            "category": category,
        })

    logger.info("[YouTube] %d vídeos encontrados em %s", len(videos), channel_handle)
    return videos


# ---------------------------------------------------------------------------
# Importação para o banco
# ---------------------------------------------------------------------------

def import_videos(videos, overwrite=False):
    """Importa vídeos YouTube como registros Video (embed).

    Args:
        videos: lista de dicts (output de fetch_channel_videos ou seleção do admin)
        overwrite: se True, atualiza título/categoria de vídeos já existentes

    Returns:
        dict com contadores: created, updated, skipped
    """
    stats = {"created": 0, "updated": 0, "skipped": 0}

    for item in videos:
        video_id = item.get("video_id", "").strip()
        if not video_id:
            stats["skipped"] += 1
            continue

        title = (item.get("title") or "").strip()
        if not title:
            stats["skipped"] += 1
            continue

        category = item.get("category") or detect_category(
            title, item.get("description", ""), item.get("tags", []), ""
        )
        thumbnail = item.get("thumbnail") or ""
        embed_url = f"https://www.youtube.com/embed/{video_id}"

        # Buscar existente por youtube_video_id
        existing = Video.query.filter_by(youtube_video_id=video_id).first()
        if not existing:
            # Buscar por source_url como fallback
            existing = Video.query.filter_by(source_url=embed_url).first()

        if existing:
            if overwrite:
                existing.title = title
                existing.category = category
                existing.thumbnail_url = thumbnail
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
            continue

        video = Video(
            title=title,
            source_url=embed_url,
            source_type="embed",
            external_provider="youtube",
            category=category,
            thumbnail_url=thumbnail,
            youtube_video_id=video_id,
        )
        db.session.add(video)
        stats["created"] += 1

    db.session.commit()
    logger.info(
        "[YouTube] Importação: %d criados, %d atualizados, %d ignorados",
        stats["created"], stats["updated"], stats["skipped"],
    )
    return stats
