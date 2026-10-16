"""Serviço de integração com o microserviço torrent-node (WebTorrent)."""
import os
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError
import json


TORRENT_NODE_URL = os.environ.get("TORRENT_NODE_URL", "http://torrent-node:9119")


def _torrent_url(path: str, params: dict | None = None) -> str:
    base = TORRENT_NODE_URL.rstrip("/")
    if params:
        return f"{base}{path}?{urlencode(params)}"
    return f"{base}{path}"


def get_stream_url(magnet: str, filename: str | None = None) -> str:
    """Retorna a URL de streaming do torrent-node para o Flask fazer proxy."""
    params: dict = {"magnet": magnet}
    if filename:
        params["file"] = filename
    return _torrent_url("/stream", params)


def get_torrent_info(magnet: str) -> dict:
    """Consulta metadados do torrent no torrent-node."""
    url = _torrent_url("/info", {"magnet": magnet})
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except URLError as exc:
        raise TorrentServiceError(f"torrent-node unreachable: {exc}") from exc
    except Exception as exc:
        raise TorrentServiceError(str(exc)) from exc


def get_status() -> dict:
    """Retorna status do serviço torrent-node."""
    url = _torrent_url("/status")
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except URLError as exc:
        raise TorrentServiceError(f"torrent-node unreachable: {exc}") from exc


def health_check() -> bool:
    """Verifica se o torrent-node está acessível."""
    try:
        url = _torrent_url("/health")
        with urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except Exception:
        return False


def remove_torrent(magnet: str) -> bool:
    """Remove torrent ativo do torrent-node."""
    import urllib.request
    url = _torrent_url("/torrent", {"magnet": magnet})
    try:
        req = Request(url, method="DELETE")
        with urlopen(req, timeout=5):
            return True
    except Exception:
        return False


class TorrentServiceError(Exception):
    pass
