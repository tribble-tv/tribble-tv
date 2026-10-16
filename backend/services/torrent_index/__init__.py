"""Indexer de torrents proprio: magnet, trackers UDP (BEP 15), texto, fontes JSON e engine."""
from .engine import Engine, EngineError
from .sources import Source, SourceError, load_sources

__all__ = ["Engine", "EngineError", "Source", "SourceError", "load_sources"]
