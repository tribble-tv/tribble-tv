import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HOST = os.getenv("KODI_RESOLVER_HOST", "0.0.0.0")
PORT = int(os.getenv("KODI_RESOLVER_PORT", "8090"))
KODI_JSONRPC_URL = os.getenv("KODI_JSONRPC_URL", "http://kodi-headless:8080/jsonrpc").rstrip("/")
MAX_ITEMS = int(os.getenv("KODI_RESOLVER_MAX_ITEMS", "500"))


class ResolverError(RuntimeError):
    pass


def jsonrpc(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": "tribble-tv",
        "method": method,
        "params": params or {},
    }
    req = Request(
        KODI_JSONRPC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as response:
            data = response.read().decode("utf-8", "ignore")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise ResolverError(f"Kodi JSON-RPC HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise ResolverError(f"Kodi JSON-RPC indisponivel: {exc.reason}") from exc

    payload = json.loads(data)
    if payload.get("error"):
        raise ResolverError(payload["error"].get("message") or "Kodi JSON-RPC falhou")
    return payload.get("result") or {}


def is_http_url(value):
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_plugin_url(value):
    return (value or "").startswith("plugin://")


def validate_source_url(source_url):
    if not source_url:
        return
    if not is_http_url(source_url):
        raise ResolverError("URL da fonte deve ser HTTP/HTTPS.")
    headers = {"User-Agent": "TribbleTV-KodiResolver/1.0"}
    if source_url.lower().endswith(".zip"):
        headers["Range"] = "bytes=0-2047"
    req = Request(source_url, headers=headers)
    try:
        with urlopen(req, timeout=20) as response:
            sample = response.read(4)
            if response.status >= 400:
                raise ResolverError(f"Fonte retornou HTTP {response.status}.")
    except HTTPError as exc:
        raise ResolverError(f"Fonte retornou HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ResolverError(f"Falha ao acessar fonte Kodi: {exc.reason}") from exc
    if source_url.lower().endswith(".zip") and sample and not sample.startswith(b"PK"):
        raise ResolverError("Fonte ZIP nao parece ser um arquivo ZIP valido.")


def install_or_check_addon(addon_id):
    if not addon_id:
        return
    try:
        jsonrpc("Addons.GetAddonDetails", {"addonid": addon_id, "properties": ["enabled"]})
    except ResolverError:
        try:
            jsonrpc("Addons.InstallAddon", {"addonid": addon_id})
        except ResolverError as exc:
            raise ResolverError(f"Add-on {addon_id} nao instalado/configurado: {exc}") from exc


def directory_items(path):
    try:
        result = jsonrpc(
            "Files.GetDirectory",
            {
                "directory": path,
                "media": "video",
                "properties": ["title", "thumbnail", "art"],
            },
        )
        return result.get("files") or []
    except ResolverError as exc:
        print(f"[DEBUG] Files.GetDirectory failed for path: {path}", flush=True)
        print(f"[DEBUG] Error: {exc}", flush=True)
        raise


def item_title(item):
    return item.get("title") or item.get("label") or item.get("file", "").rsplit("/", 1)[-1]


def item_thumb(item):
    art = item.get("art") or {}
    return item.get("thumbnail") or art.get("thumb") or art.get("poster") or ""


def walk(path, category, max_depth):
    found = []
    seen_dirs = set()

    def visit(current_path, current_category, depth):
        if len(found) >= MAX_ITEMS:
            return
        if depth > max_depth or current_path in seen_dirs:
            return
        seen_dirs.add(current_path)
        for item in directory_items(current_path):
            url = item.get("file") or ""
            title = item_title(item)
            next_category = current_category or item.get("label") or category
            if is_http_url(url):
                found.append(
                    {
                        "title": title,
                        "stream_url": url,
                        "category": current_category or category,
                        "thumbnail_url": item_thumb(item),
                    }
                )
            elif is_plugin_url(url) or item.get("filetype") == "directory":
                visit(url, next_category, depth + 1)
            if len(found) >= MAX_ITEMS:
                return

    visit(path, category, 0)
    return found


def resolve(payload):
    source_url = (payload.get("source_url") or "").strip()
    addon_id = (payload.get("addon_id") or "").strip()
    entry_path = (payload.get("entry_path") or "").strip()
    category = (payload.get("default_category") or "Kodi").strip()
    max_depth = max(1, int(payload.get("max_depth") or 4))
    if not addon_id and not entry_path:
        return {
            "status": "needs_config",
            "error": "Informe addon_id ou entry_path para resolver a fonte Kodi.",
            "items": [],
            "stats": {"created": 0, "updated": 0, "skipped": 0, "invalid": 0, "total": 0},
        }
    validate_source_url(source_url)
    # Pular instalacao automatica - tentar acesso direto ao plugin
    # O Kodi headless pode nao suportar Addons.InstallAddon
    root = entry_path or f"plugin://{addon_id}/"
    items = walk(root, category, max_depth)
    return {"status": "success", "items": items, "stats": {"total": len(items)}}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "healthy", "service": "kodi-resolver"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/resolve":
            self._send(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
            self._send(200, resolve(payload))
        except ResolverError as exc:
            self._send(502, {"status": "error", "error": str(exc), "items": []})
        except Exception as exc:
            self._send(500, {"status": "error", "error": str(exc), "items": []})

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    print(f"kodi-resolver listening on {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
