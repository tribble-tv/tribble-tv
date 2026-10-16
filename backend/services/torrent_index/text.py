"""Normalizacao de texto e heuristicas de titulo."""
import re
import unicodedata

_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_QUALITY_RE = re.compile(r"(?<![a-z0-9])(2160p|1080p|720p|480p|4k)(?![a-z0-9])", re.IGNORECASE)
_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB)", re.IGNORECASE)
_SIZE_UNITS = {"KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Minusculo, sem acentos, pontuacao vira espaco."""
    text = strip_accents(text).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokens(text: str) -> list[str]:
    return normalize(text).split()


def match_score(query: str, title: str) -> float:
    """Fracao dos termos da busca presentes no titulo (0.0 a 1.0)."""
    wanted = tokens(query)
    if not wanted:
        return 0.0
    have = set(tokens(title))
    return sum(1 for t in wanted if t in have) / len(wanted)


def parse_year(text: str) -> str:
    match = _YEAR_RE.search(text or "")
    return match.group(1) if match else ""


def parse_quality(text: str) -> str:
    match = _QUALITY_RE.search(text or "")
    return match.group(1).lower() if match else ""


def parse_size_bytes(text: str) -> int | None:
    match = _SIZE_RE.search(text or "")
    if not match:
        return None
    return int(float(match.group(1).replace(",", ".")) * _SIZE_UNITS[match.group(2).upper()])


def format_size(num_bytes: int | None) -> str:
    if not num_bytes:
        return ""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def clean_title(text: str) -> str:
    """Remove tags HTML e espacos repetidos."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()
