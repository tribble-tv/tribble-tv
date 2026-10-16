import json
import ssl
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.extensions import db
from backend.models import JellyfinItem, JellyfinLibrary


class JellyfinServiceError(RuntimeError):
    pass


def _server_url(server):
    return (server.internal_url or server.base_url or "").rstrip("/")


def _request_json(server, method, path, payload=None, query=None, timeout=30):
    base_url = _server_url(server)
    if not base_url:
        raise JellyfinServiceError("Servidor Jellyfin sem URL configurada.")
    url = f"{base_url}{path}"
    if query is None:
        query = {}
    query["api_key"] = server.api_key
    url = f"{url}?{urlencode(query, doseq=True)}"
    data = None
    headers = {
        "Accept": "application/json",
        "X-Emby-Token": server.api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(req, timeout=timeout, context=ctx) as response:
            body = response.read()
            if not body:
                return {}
            return json.loads(body.decode("utf-8"))
    except HTTPError as exc:
        raise JellyfinServiceError(f"Jellyfin retornou HTTP {exc.code} para {path}.") from exc
    except URLError as exc:
        raise JellyfinServiceError(f"Falha ao acessar Jellyfin: {exc.reason}.") from exc
    except json.JSONDecodeError as exc:
        raise JellyfinServiceError("Resposta Jellyfin não é JSON válido.") from exc


def get_system_info(server):
    return _request_json(server, "GET", "/System/Info")


def get_libraries(server):
    return _request_json(server, "GET", "/Library/VirtualFolders")


def get_items(server, library_id):
    return _request_json(
        server,
        "GET",
        "/Items",
        query={
            "ParentId": library_id,
            "Recursive": "true",
            "IncludeItemTypes": ["Movie", "Video", "Episode"],
            "Fields": ["Path", "Overview", "MediaSources", "Genres"],
        },
    ).get("Items", [])


def get_item(server, item_id):
    return _request_json(server, "GET", f"/Items/{item_id}")


def sync_libraries(server):
    synced = []
    for data in get_libraries(server):
        library_id = data.get("ItemId") or data.get("Id") or data.get("Name")
        if not library_id:
            continue
        library = JellyfinLibrary.query.filter_by(
            jellyfin_server_id=server.id,
            jellyfin_library_id=str(library_id),
        ).first()
        if library is None:
            library = JellyfinLibrary(jellyfin_server=server, jellyfin_library_id=str(library_id))
            db.session.add(library)
        library.name = data.get("Name") or str(library_id)
        library.type = data.get("CollectionType") or data.get("LibraryOptions", {}).get("ContentType")
        library.is_active = True
        synced.append(library)
    db.session.commit()
    return synced


def _image_tag(data):
    tags = data.get("ImageTags") or {}
    return tags.get("Primary") or tags.get("Thumb") or tags.get("Backdrop")


def sync_items(server, library_id):
    from backend.models import Video
    synced = []
    now = datetime.utcnow()
    for data in get_items(server, library_id):
        item_id = data.get("Id")
        if not item_id:
            continue
        item = JellyfinItem.query.filter_by(
            jellyfin_server_id=server.id,
            jellyfin_item_id=str(item_id),
        ).first()
        if item is None:
            item = JellyfinItem(jellyfin_server=server, jellyfin_item_id=str(item_id))
            db.session.add(item)
        item.name = data.get("Name") or str(item_id)
        item.media_type = data.get("Type") or data.get("MediaType")
        item.path = data.get("Path")
        item.runtime_ticks = data.get("RunTimeTicks")
        item.image_tag = _image_tag(data)
        item.is_active = True
        item.last_synced_at = now
        if item.video_id is None:
            video = Video.query.filter_by(
                jellyfin_server_id=server.id,
                jellyfin_item_id=str(item_id),
            ).first()
            if video is None:
                video = Video(
                    title=item.name,
                    source_type="jellyfin",
                    jellyfin_server_id=server.id,
                    jellyfin_item_id=str(item_id),
                    external_provider="jellyfin",
                )
                db.session.add(video)
                db.session.flush()
            item.video = video
        synced.append(item)
    db.session.commit()
    return synced


def create_user(server, username, password):
    return _request_json(
        server,
        "POST",
        "/Users/New",
        payload={"Name": username, "Password": password},
    )


def disable_user(server, user_id):
    policy = _request_json(server, "GET", f"/Users/{user_id}").get("Policy", {})
    policy["IsDisabled"] = True
    return _request_json(server, "POST", f"/Users/{user_id}/Policy", payload=policy)
