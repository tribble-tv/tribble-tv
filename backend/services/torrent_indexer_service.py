"""Fachada do indexer de torrents proprio (pacote backend.services.torrent_index).

As fontes vem de config/torrent_sources.json (ou TORRENT_SOURCES_FILE). Nao ha servico
externo: a busca, a extracao de magnets e o scrape de trackers rodam dentro do painel.
"""
import os

from backend.services.torrent_index import Engine, EngineError, SourceError, load_sources

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class TorrentIndexerError(Exception):
    pass


def _timeout() -> float:
    try:
        return float(os.environ.get("TORRENT_INDEXER_TIMEOUT_SECONDS", "15"))
    except ValueError:
        return 15.0


def _scrape_enabled() -> bool:
    return os.environ.get("TORRENT_INDEXER_TRACKER_SCRAPE", "1").strip().lower() not in ("0", "false", "no")


def _engine() -> Engine:
    try:
        sources = load_sources()
    except SourceError as exc:
        raise TorrentIndexerError(f"configuracao de fontes invalida: {exc}") from exc
    kwargs = {} if _scrape_enabled() else {"scrape": None}
    return Engine(sources, timeout=_timeout(), **kwargs)


def _clamp(limit) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def indexers() -> dict[str, str]:
    """{id: nome} das fontes habilitadas; vazio se nao configurado ou invalido."""
    try:
        return {s.id: s.name for s in load_sources()}
    except SourceError:
        return {}


def is_configured() -> bool:
    return bool(indexers())


def health_check() -> bool:
    """True se o arquivo de fontes e valido e tem ao menos uma fonte habilitada."""
    return is_configured()


def search(query: str, indexer: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Busca em uma fonte especifica e devolve resultados normalizados."""
    try:
        return _engine().search_source(indexer, query, _clamp(limit))
    except EngineError as exc:
        raise TorrentIndexerError(str(exc)) from exc


def search_all(query: str, limit: int = DEFAULT_LIMIT) -> dict:
    """Busca em todas as fontes. Retorna {"results": [...], "errors": {fonte: msg}}."""
    query = (query or "").strip()
    if not query:
        raise TorrentIndexerError("informe um termo de busca.")
    return _engine().search(query, limit=_clamp(limit))
