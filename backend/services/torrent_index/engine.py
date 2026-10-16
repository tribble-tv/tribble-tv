"""Engine de busca: consulta as fontes, extrai magnets, enriquece com trackers e ranqueia."""
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

from . import magnet as magnet_mod
from . import text as text_mod
from . import trackers
from .sources import Source

MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; TribbleTV-Indexer/1.0)"
MIN_SCORE = 0.5


class EngineError(Exception):
    pass


def http_fetch(url: str, headers: dict | None = None, timeout: float = 15.0) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise EngineError(f"esquema nao permitido: {url}")
    req = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES + 1)
            charset = resp.headers.get_content_charset() or "utf-8"
    except (URLError, OSError, ValueError) as exc:
        raise EngineError(f"falha ao acessar {url}: {exc}") from exc
    if len(raw) > MAX_BYTES:
        raise EngineError(f"resposta muito grande: {url}")
    return raw.decode(charset, errors="replace")


def _to_int(value) -> int | None:
    try:
        return int(str(value).strip().replace(",", "").replace(".", ""))
    except (TypeError, ValueError):
        return None


def _dig(data, path: str):
    for key in filter(None, path.split(".")):
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
            data = data[int(key)]
        else:
            return None
    return data


class Engine:
    def __init__(self, sources: list[Source], fetch=http_fetch, scrape=trackers.scrape_many,
                 timeout: float = 15.0, max_details: int = 10):
        self.sources = {s.id: s for s in sources}
        self._fetch = fetch
        self._scrape = scrape
        self.timeout = timeout
        self.max_details = max_details

    def _get(self, url: str, source: Source) -> str:
        return self._fetch(url, source.headers, self.timeout)

    # -- extracao por tipo de fonte ---------------------------------------
    def _html_candidates(self, source: Source, page: str, base_url: str) -> list[dict]:
        out = []
        for m in source.item_pattern.finditer(page):
            g = {k: v for k, v in m.groupdict().items() if v}
            found = magnet_mod.find_magnets(g["magnet"]) if g.get("magnet") else []
            out.append({
                "title": text_mod.clean_title(g.get("title", "")),
                "magnet": found[0] if found else "",
                "details": urljoin(base_url, g["url"].strip()) if g.get("url") else "",
                "size": g.get("size", ""),
                "seeds": _to_int(g.get("seeds")),
                "leech": _to_int(g.get("leech")),
                "year": g.get("year", ""),
            })
        return out

    def _json_candidates(self, source: Source, body: str) -> list[dict]:
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise EngineError(f"{source.id}: JSON invalido: {exc}") from exc
        items = _dig(data, source.results_path) if source.results_path else data
        if not isinstance(items, list):
            return []
        fields = source.fields
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue

            def get(name):
                return _dig(item, fields[name]) if name in fields else None

            title = str(get("title") or "")
            uri = str(get("magnet") or "")
            if not magnet_mod.parse_magnet(uri) and get("info_hash"):
                try:
                    uri = magnet_mod.build_magnet(str(get("info_hash")), title)
                except ValueError:
                    uri = ""
            out.append({
                "title": text_mod.clean_title(title),
                "magnet": uri,
                "details": str(get("url") or ""),
                "size": str(get("size") or ""),
                "seeds": _to_int(get("seeds")),
                "leech": _to_int(get("leech")),
                "year": str(get("year") or ""),
            })
        return out

    def _resolve_magnets(self, source: Source, candidates: list[dict]) -> list[dict]:
        pending = [c for c in candidates if not c["magnet"] and c["details"] and source.fetch_detail]
        pending = pending[: self.max_details]

        def load(c):
            try:
                found = magnet_mod.find_magnets(self._get(c["details"], source))
                c["magnet"] = found[0] if found else ""
            except EngineError:
                pass

        if pending:
            with ThreadPoolExecutor(max_workers=min(5, len(pending))) as pool:
                list(pool.map(load, pending))
        return [c for c in candidates if magnet_mod.parse_magnet(c["magnet"])]

    # -- API --------------------------------------------------------------
    def search_source(self, source_id: str, query: str, limit: int = 20) -> list[dict]:
        source = self.sources.get(source_id)
        if not source:
            raise EngineError(f"fonte desconhecida: {source_id}")
        query = (query or "").strip()
        if not query:
            raise EngineError("informe um termo de busca.")
        url = source.search_url.replace("{query}", quote_plus(query))
        body = self._get(url, source)
        if source.type == "json":
            candidates = self._json_candidates(source, body)
        else:
            candidates = self._html_candidates(source, body, url)
        candidates = [c for c in candidates if text_mod.match_score(query, c["title"]) >= MIN_SCORE]
        results = []
        for c in self._resolve_magnets(source, candidates):
            parsed = magnet_mod.parse_magnet(c["magnet"])
            title = c["title"] or parsed["name"]
            results.append({
                "title": title,
                "original_title": parsed["name"] or title,
                "year": c["year"] or text_mod.parse_year(title),
                "quality": text_mod.parse_quality(title),
                "size": c["size"] or text_mod.format_size(parsed["size"]),
                "seeds": c["seeds"],
                "leech": c["leech"],
                "magnet": c["magnet"],
                "info_hash": parsed["info_hash"],
                "trackers": parsed["trackers"],
                "details": c["details"],
                "imdb": "",
                "date": "",
                "indexer": source.id,
            })
        return results[:limit]

    def _enrich(self, results: list[dict]) -> None:
        """Preenche seeds/leech ausentes via scrape UDP nos trackers do proprio magnet."""
        if not self._scrape:
            return
        missing = [r for r in results if r["seeds"] is None]

        def run(r):
            udp = [t for t in r["trackers"] if t.lower().startswith("udp://")][:3]
            stats = self._scrape(udp, [r["info_hash"]]) if udp else {}
            st = stats.get(r["info_hash"])
            if st:
                r["seeds"], r["leech"] = st["seeds"], st["leech"]

        if missing:
            with ThreadPoolExecutor(max_workers=min(8, len(missing))) as pool:
                list(pool.map(run, missing))

    def search(self, query: str, source_ids: list[str] | None = None, limit: int = 20) -> dict:
        """Busca em varias fontes em paralelo. Retorna {"results": [...], "errors": {id: msg}}."""
        ids = source_ids or list(self.sources)
        results: list[dict] = []
        errors: dict[str, str] = {}

        def run(sid):
            try:
                return sid, self.search_source(sid, query, limit), None
            except EngineError as exc:
                return sid, [], str(exc)

        if ids:
            with ThreadPoolExecutor(max_workers=len(ids)) as pool:
                for sid, items, error in pool.map(run, ids):
                    results.extend(items)
                    if error:
                        errors[sid] = error

        merged: dict[str, dict] = {}
        for r in results:
            cur = merged.get(r["info_hash"])
            if cur is None or (r["seeds"] or 0) > (cur["seeds"] or 0):
                merged[r["info_hash"]] = r
        unique = list(merged.values())
        self._enrich(unique)
        for r in unique:
            r["seeds"] = r["seeds"] or 0
            r["leech"] = r["leech"] or 0
            r.pop("trackers", None)
        unique.sort(key=lambda r: (text_mod.match_score(query, r["title"]), r["seeds"]), reverse=True)
        return {"results": unique[:limit], "errors": errors}
