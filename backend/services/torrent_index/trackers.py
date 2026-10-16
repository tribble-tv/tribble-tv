"""Scrape de seeds/leechers em trackers UDP (BEP 15)."""
import os
import socket
import struct
from urllib.parse import urlsplit

PROTOCOL_ID = 0x41727101980
ACTION_CONNECT = 0
ACTION_SCRAPE = 2
ACTION_ERROR = 3
MAX_HASHES_PER_REQUEST = 74


class TrackerError(Exception):
    pass


def parse_tracker_url(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    if parts.scheme.lower() != "udp" or not parts.hostname or not parts.port:
        raise TrackerError(f"tracker UDP invalido: {url}")
    return parts.hostname, parts.port


def _exchange(sock, addr, packet: bytes, action: int, tid: int, min_len: int) -> bytes:
    sock.sendto(packet, addr)
    data, _ = sock.recvfrom(65535)
    if len(data) < 8:
        raise TrackerError("resposta curta")
    got_action, got_tid = struct.unpack(">II", data[:8])
    if got_tid != tid:
        raise TrackerError("transaction_id diferente")
    if got_action == ACTION_ERROR:
        raise TrackerError(f"tracker: {data[8:].decode(errors='replace')}")
    if got_action != action or len(data) < min_len:
        raise TrackerError("resposta inesperada")
    return data


def scrape(tracker_url: str, info_hashes: list[str], timeout: float = 3.0,
           socket_factory=socket.socket) -> dict[str, dict]:
    """Devolve {info_hash: {"seeds", "completed", "leech"}} de um tracker UDP."""
    hashes = [h.lower() for h in info_hashes][:MAX_HASHES_PER_REQUEST]
    if not hashes:
        return {}
    addr = parse_tracker_url(tracker_url)
    sock = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        tid = int.from_bytes(os.urandom(4), "big")
        resp = _exchange(sock, addr, struct.pack(">QII", PROTOCOL_ID, ACTION_CONNECT, tid),
                         ACTION_CONNECT, tid, 16)
        connection_id = struct.unpack(">Q", resp[8:16])[0]

        tid = int.from_bytes(os.urandom(4), "big")
        packet = struct.pack(">QII", connection_id, ACTION_SCRAPE, tid)
        packet += b"".join(bytes.fromhex(h) for h in hashes)
        resp = _exchange(sock, addr, packet, ACTION_SCRAPE, tid, 8 + 12 * len(hashes))
    except (OSError, ValueError, struct.error) as exc:
        raise TrackerError(f"{tracker_url}: {exc}") from exc
    finally:
        sock.close()

    stats = {}
    for i, h in enumerate(hashes):
        seeds, completed, leech = struct.unpack(">III", resp[8 + 12 * i: 20 + 12 * i])
        stats[h] = {"seeds": seeds, "completed": completed, "leech": leech}
    return stats


def scrape_many(trackers: list[str], info_hashes: list[str], timeout: float = 3.0,
                socket_factory=socket.socket) -> dict[str, dict]:
    """Consulta os trackers UDP em ordem e fica com o maior numero de seeds por hash.

    Falhas em trackers individuais sao ignoradas; retorna {} se nenhum responder.
    """
    best: dict[str, dict] = {}
    for url in trackers:
        try:
            stats = scrape(url, info_hashes, timeout, socket_factory)
        except TrackerError:
            continue
        for h, st in stats.items():
            if h not in best or st["seeds"] > best[h]["seeds"]:
                best[h] = st
    return best
