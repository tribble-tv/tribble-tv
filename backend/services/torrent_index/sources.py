"""Definicao de fontes em JSON (config/torrent_sources.json ou TORRENT_SOURCES_FILE).

Cada item de "sources" tem id (slug), name, type ("html" ou "json"), search_url com o
marcador {query}, enabled (padrao true) e headers (opcional).

html: `item_pattern` e uma regex com grupos nomeados `title` e `url` ou `magnet`
(opcionais: size, seeds, leech, year). Sem magnet no item, `url` e aberto e o primeiro
magnet da pagina e usado (`fetch_detail`, padrao true).

json: `results_path` (caminho com pontos ate a lista) e `fields`, que mapeia title,
magnet, info_hash, size, seeds, leech, url, year para chaves de cada item. Com
info_hash em vez de magnet, o magnet e montado.
"""
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

_ID_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
_REGEX_GROUPS = {"title", "url", "magnet", "size", "seeds", "leech", "year"}
_JSON_FIELDS = {"title", "magnet", "info_hash", "size", "seeds", "leech", "url", "year"}
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "torrent_sources.json"


class SourceError(Exception):
    pass


@dataclass
class Source:
    id: str
    name: str
    type: str
    search_url: str
    enabled: bool = True
    item_pattern: re.Pattern | None = None
    fetch_detail: bool = True
    results_path: str = ""
    fields: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)


def parse_source(raw: dict) -> Source:
    if not isinstance(raw, dict):
        raise SourceError("fonte deve ser um objeto")
    sid = str(raw.get("id", ""))
    if not _ID_RE.match(sid):
        raise SourceError(f"id invalido: {sid!r}")
    kind = raw.get("type", "html")
    if kind not in ("html", "json"):
        raise SourceError(f"{sid}: type deve ser html ou json")
    url = str(raw.get("search_url", ""))
    if "{query}" not in url:
        raise SourceError(f"{sid}: search_url precisa conter {{query}}")
    parts = urlsplit(url.replace("{query}", "x"))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SourceError(f"{sid}: search_url deve ser http(s)")
    source = Source(
        id=sid,
        name=str(raw.get("name") or sid),
        type=kind,
        search_url=url,
        enabled=bool(raw.get("enabled", True)),
        fetch_detail=bool(raw.get("fetch_detail", True)),
        headers={str(k): str(v) for k, v in (raw.get("headers") or {}).items()},
    )
    if kind == "html":
        try:
            source.item_pattern = re.compile(str(raw.get("item_pattern", "")), re.DOTALL | re.IGNORECASE)
        except re.error as exc:
            raise SourceError(f"{sid}: item_pattern invalido: {exc}") from exc
        names = set(source.item_pattern.groupindex)
        if "title" not in names or not names & {"url", "magnet"}:
            raise SourceError(f"{sid}: item_pattern precisa dos grupos title e (url ou magnet)")
        if names - _REGEX_GROUPS:
            raise SourceError(f"{sid}: grupos desconhecidos: {sorted(names - _REGEX_GROUPS)}")
    else:
        fields = raw.get("fields") or {}
        if "title" not in fields or not set(fields) & {"magnet", "info_hash"}:
            raise SourceError(f"{sid}: fields precisa de title e (magnet ou info_hash)")
        if set(fields) - _JSON_FIELDS:
            raise SourceError(f"{sid}: campos desconhecidos: {sorted(set(fields) - _JSON_FIELDS)}")
        source.fields = {str(k): str(v) for k, v in fields.items()}
        source.results_path = str(raw.get("results_path", ""))
    return source


def load_sources(path: str | os.PathLike | None = None) -> list[Source]:
    """Le as fontes do JSON. Arquivo ausente = lista vazia; JSON/fonte invalida = SourceError."""
    path = Path(path or os.environ.get("TORRENT_SOURCES_FILE") or DEFAULT_PATH)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceError(f"nao foi possivel ler {path}: {exc}") from exc
    items = data.get("sources") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SourceError("esperado uma lista em 'sources'")
    sources = [parse_source(item) for item in items]
    ids = [s.id for s in sources]
    if len(ids) != len(set(ids)):
        raise SourceError("ids de fonte duplicados")
    return [s for s in sources if s.enabled]
