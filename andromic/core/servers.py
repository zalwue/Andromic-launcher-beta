"""Minecraft server list ping (status protocol) and server list management.

Stage 3 adds:
* a built-in list of recommended servers (never removed, only hidden)
* strict validation of user-entered ``host:port`` addresses (default port
  25565, port range 1..65535, IPv6 ``[::1]:port`` support)
* custom server persistence helpers (add / edit / remove / normalise)
"""
import json
import re
import socket
import struct
import time
from typing import List, Optional, Tuple

DEFAULT_PORT = 25565

# Recommended public servers shown on first open / when no custom servers
# exist.  Only factual name+address pairs are stored; live status (version,
# players, latency, online/offline) is queried at runtime and never invented.
RECOMMENDED_SERVERS: List[dict] = [
    {"name": "Hypixel", "address": f"mc.hypixel.net:{DEFAULT_PORT}", "recommended": True},
    {"name": "CubeCraft", "address": f"play.cubecraft.net:{DEFAULT_PORT}", "recommended": True},
    {"name": "The Hive", "address": f"play.hivemc.com:{DEFAULT_PORT}", "recommended": True},
    {"name": "Mineplex", "address": f"us.mineplex.com:{DEFAULT_PORT}", "recommended": True},
]

_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9_-]{1,63}(\.(?!-)[A-Za-z0-9_-]{1,63})*\.?$")
_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def _valid_hostname(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    if any(ch.isspace() for ch in host):
        return False
    if host.startswith("[") or host.endswith("]"):
        return False
    if any(ch in host for ch in "/\\@?#,;\"'<>(){}"):
        return False
    if host.lower() in ("localhost",):
        return True
    match = _IPV4_RE.match(host)
    if match:
        return all(0 <= int(part) <= 255 for part in match.groups())
    # IPv6 (bare form, already unwrapped from brackets by caller)
    if ":" in host:
        try:
            socket.inet_pton(socket.AF_INET6, host)
            return True
        except (OSError, ValueError):
            return False
    return bool(_HOSTNAME_RE.match(host))


def split_address(address: str) -> Tuple[str, int]:
    address = address.strip()
    if address.startswith("["):
        closing = address.find("]")
        if closing < 0:
            raise ValueError("Invalid IPv6 server address")
        host = address[1:closing]
        suffix = address[closing + 1:]
        if not suffix:
            return host, 25565
        if not suffix.startswith(":") or not suffix[1:].isdigit():
            raise ValueError("Invalid server port")
        port = int(suffix[1:])
    else:
        host, sep, raw_port = address.rpartition(":")
        # A bare IPv6 address has several colons and no unambiguous port.
        if sep and host and raw_port.isdigit() and ":" not in host:
            port = int(raw_port)
        else:
            return address, 25565
    if not host or not 1 <= port <= 65535:
        raise ValueError("Server port must be between 1 and 65535")
    return host, port


def _varint(value: int) -> bytes:
    value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _string(text: str) -> bytes:
    data = text.encode("utf-8")
    return _varint(len(data)) + data


def _packet(payload: bytes) -> bytes:
    return _varint(len(payload)) + payload


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed")
        data += chunk
    return bytes(data)


def _read_varint(sock: socket.socket) -> int:
    result = 0
    for shift in range(0, 35, 7):
        byte = _recv_exact(sock, 1)[0]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result
    raise ValueError("varint too long")


def _flatten(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_flatten(n) for n in node)
    if isinstance(node, dict):
        return str(node.get("text", "")) + _flatten(node.get("extra", []))
    return ""


def ping(address: str, timeout: float = 4.0) -> dict:
    """Query a server; returns a dict with `online` and, if reachable, details."""
    try:
        host, port = split_address(address)
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            handshake = (_varint(0x00) + _varint(-1) + _string(host)
                         + struct.pack(">H", port) + _varint(1))
            sock.sendall(_packet(handshake) + _packet(_varint(0x00)))
            _read_varint(sock)
            if _read_varint(sock) != 0x00:
                raise ValueError("unexpected packet")
            length = _read_varint(sock)
            if length < 1 or length > 1024 * 1024:
                raise ValueError("invalid status response size")
            data = json.loads(_recv_exact(sock, length).decode("utf-8", errors="replace"))

            latency = None
            started = time.time()
            sock.sendall(_packet(_varint(0x01) + struct.pack(">q", int(started * 1000))))
            try:
                _read_varint(sock)
                _recv_exact(sock, 9)
                latency = int((time.time() - started) * 1000)
            except (OSError, ValueError, ConnectionError):
                pass
    except (OSError, ValueError, ConnectionError):
        return {"online": False}
    players = data.get("players", {})
    motd = re.sub("\u00a7.", "", _flatten(data.get("description", ""))).strip()
    return {
        "online": True,
        "motd": " ".join(motd.split()),
        "players": players.get("online", 0),
        "max": players.get("max", 0),
        "version": data.get("version", {}).get("name", ""),
        "latency": latency,
    }


def validate_address(address: str) -> Tuple[str, int]:
    """Strictly validate a ``host:port`` server address; returns ``(host, port)``.

    * port defaults to 25565 when omitted
    * port must be a plain integer in 1..65535
    * hostname / IPv4 / bracketed IPv6 hosts are accepted
    * empty host, embedded spaces, illegal characters and bad ports raise
      ``ValueError``
    """
    if not isinstance(address, str):
        raise ValueError("Server address must be a string")
    text = address.strip()
    if not text:
        raise ValueError("Server address is required")
    if any(ch.isspace() for ch in text):
        raise ValueError("Server address must not contain spaces")

    if text.startswith("["):  # [IPv6] or [IPv6]:port
        closing = text.find("]")
        if closing < 0:
            raise ValueError("Invalid IPv6 server address")
        host = text[1:closing].strip()
        suffix = text[closing + 1:]
        port = DEFAULT_PORT
        if suffix:
            if not suffix.startswith(":") or not suffix[1:].isdigit():
                raise ValueError("Invalid server port")
            port = int(suffix[1:])
        _check_ipv6(host)
    else:
        if text.count(":") == 1:  # hostname/IPv4 : port
            host, _, raw_port = text.partition(":")
            if not raw_port.isdigit():
                raise ValueError("Invalid server port")
            port = int(raw_port)
        elif ":" in text:  # bare IPv6, no port
            host, port = text, DEFAULT_PORT
            _check_ipv6(host)
        else:
            host, port = text, DEFAULT_PORT

    host = host.strip()
    if not host:
        raise ValueError("Server address is required")
    if not 1 <= port <= 65535:
        raise ValueError("Server port must be between 1 and 65535")
    if ":" not in host and not _valid_hostname(host):
        raise ValueError(f"Invalid server host: {host!r}")
    return host, port


def _check_ipv6(host: str) -> None:
    try:
        socket.inet_pton(socket.AF_INET6, host)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid IPv6 server address: {host!r}") from exc


def normalize_address(address: str) -> str:
    """Validate ``address`` and return a canonical ``host:port`` string."""
    host, port = validate_address(address)
    if ":" in host:  # IPv6
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def normalize_server_entry(entry) -> Optional[dict]:
    """Repair a persisted server entry; ``None`` when unusable."""
    if isinstance(entry, str):
        name, address = "", entry
    elif isinstance(entry, dict):
        name = entry.get("name") or entry.get("title") or ""
        address = entry.get("address") or entry.get("ip") or entry.get("host") or ""
    else:
        return None
    if not isinstance(address, str) or not address.strip():
        return None
    try:
        normalized = normalize_address(address)
    except ValueError:
        return None
    name = str(name or "").strip() or normalized.rsplit(":", 1)[0]
    out = {"name": name[:128], "address": normalized}
    if isinstance(entry, dict) and entry.get("recommended"):
        out["recommended"] = True
    return out


def recommended_visible(servers_list) -> bool:
    """Recommended servers are shown only when no custom servers exist."""
    return not any(not s.get("recommended") for s in (servers_list or [])
                   if isinstance(s, dict))


def visible_servers(servers_list) -> List[dict]:
    """Custom servers if any, otherwise the recommended list (never removed)."""
    custom = [s for s in (servers_list or []) if isinstance(s, dict) and not s.get("recommended")]
    if custom:
        return custom
    recommended_saved = [s for s in (servers_list or [])
                         if isinstance(s, dict) and s.get("recommended")]
    return recommended_saved or list(RECOMMENDED_SERVERS)


def add_server(servers_list: list, name: str, address: str) -> dict:
    """Validate + append a custom server; returns the normalised entry."""
    normalized = normalize_address(address)
    entry = {"name": (name or "").strip()[:128] or normalized.rsplit(":", 1)[0],
             "address": normalized}
    servers_list.append(entry)
    return entry


def edit_server(servers_list: list, index: int, name: str, address: str) -> dict:
    """Edit the custom server at ``index`` (recommended entries excluded)."""
    custom = [i for i, s in enumerate(servers_list) if not s.get("recommended")]
    if not 0 <= index < len(custom):
        raise IndexError("Server index out of range")
    position = custom[index]
    normalized = normalize_address(address)
    entry = dict(servers_list[position])
    entry["name"] = (name or "").strip()[:128] or normalized.rsplit(":", 1)[0]
    entry["address"] = normalized
    entry.pop("recommended", None)
    servers_list[position] = entry
    return entry


def remove_server(servers_list: list, index: int) -> Optional[dict]:
    """Remove the custom server at ``index``; returns it or ``None``."""
    custom = [i for i, s in enumerate(servers_list) if not s.get("recommended")]
    if not 0 <= index < len(custom):
        return None
    position = custom[index]
    removed = servers_list.pop(position)
    return removed
