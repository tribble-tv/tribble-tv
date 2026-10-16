"""Parse, construcao e extracao de magnet links (BEP 9)."""
import base64
import binascii
import html
import re
from urllib.parse import parse_qs, quote, urlsplit

_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_BASE32 = re.compile(r"^[A-Za-z2-7]{32}$")
_MAGNET_RE = re.compile(r"magnet:\?[^\s\"'<>]+", re.IGNORECASE)
_BTIH_PREFIX = "urn:btih:"


def normalize_info_hash(value: str) -> str | None:
    """Aceita hex (40) ou base32 (32) e devolve hex minusculo, ou None."""
    value = (value or "").strip()
    if _HEX40.match(value):
        return value.lower()
    if _BASE32.match(value):
        try:
            return binascii.hexlify(base64.b32decode(value.upper())).decode()
        except (binascii.Error, ValueError):
            return None
    return None


def parse_magnet(uri: str) -> dict | None:
    """Devolve {info_hash, name, trackers, size} ou None se nao for magnet BTIH valido."""
    uri = html.unescape((uri or "").strip())
    parts = urlsplit(uri)
    if parts.scheme.lower() != "magnet":
        return None
    params = parse_qs(parts.query, keep_blank_values=False)
    info_hash = None
    for xt in params.get("xt", []):
        if xt.lower().startswith(_BTIH_PREFIX):
            info_hash = normalize_info_hash(xt[len(_BTIH_PREFIX):])
            if info_hash:
                break
    if not info_hash:
        return None
    size = None
    try:
        size = int(params["xl"][0]) if params.get("xl") else None
    except ValueError:
        pass
    return {
        "info_hash": info_hash,
        "name": (params.get("dn") or [""])[0],
        "trackers": params.get("tr", []),
        "size": size,
    }


def build_magnet(info_hash: str, name: str = "", trackers: list[str] | None = None) -> str:
    info_hash = normalize_info_hash(info_hash)
    if not info_hash:
        raise ValueError("info_hash invalido")
    uri = f"magnet:?xt={_BTIH_PREFIX}{info_hash}"
    if name:
        uri += f"&dn={quote(name, safe='')}"
    for tracker in trackers or []:
        uri += f"&tr={quote(tracker, safe='')}"
    return uri


def find_magnets(text: str) -> list[str]:
    """Extrai magnets validos de um trecho de HTML/texto, sem repeticoes (por info_hash)."""
    seen: set[str] = set()
    found = []
    for raw in _MAGNET_RE.findall(text or ""):
        uri = html.unescape(raw)
        parsed = parse_magnet(uri)
        if parsed and parsed["info_hash"] not in seen:
            seen.add(parsed["info_hash"])
            found.append(uri)
    return found
