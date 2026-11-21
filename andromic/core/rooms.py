"""Local co-op rooms and shareable invite codes.

A room is a lightweight, offline-first description of a multiplayer session:
the host/port, the instance to launch and an optional password.  Rooms are
stored in the launcher configuration; invite codes are self-contained so they
can be shared through any chat without a server component.
"""
from __future__ import annotations

import base64
import json
import re
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

INVITE_PREFIX = "ANDROMIC-ROOM:"
DISCOVERY_MAGIC = "ANDROMIC_LAN_V1"
DISCOVERY_PORT = 25566
_MAX_NAME = 64
_MAX_PASSWORD = 128
_MAX_DESCRIPTION = 280


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_host(host: str) -> str:
    value = str(host or "").strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if not value:
        raise ValueError("A server address is required")
    if len(value) > 255 or any(ch.isspace() for ch in value):
        raise ValueError("Invalid server address")
    return value


def normalize_address(host: str, port: int = 25565) -> str:
    host = _clean_host(host)
    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("The port must be a number") from exc
    if not 1 <= port <= 65535:
        raise ValueError("The port must be between 1 and 65535")
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def split_address(address: str) -> tuple:
    """Split ``host:port`` and ``[ipv6]:port`` addresses safely."""
    value = str(address or "").strip()
    if value.startswith("["):
        closing = value.find("]")
        if closing < 0:
            raise ValueError("Invalid IPv6 address")
        host = value[1:closing]
        suffix = value[closing + 1:]
        port = int(suffix[1:]) if suffix.startswith(":") and suffix[1:].isdigit() else 25565
        return host, port
    host, sep, raw_port = value.rpartition(":")
    if sep and raw_port.isdigit() and ":" not in host:
        return host, int(raw_port)
    return value, 25565


def new_room(name: str, host: str, port: int = 25565, instance: str = "",
             password: str = "", description: str = "") -> Dict[str, Any]:
    name = str(name or "").strip() or "Room"
    if len(name) > _MAX_NAME:
        name = name[:_MAX_NAME]
    if len(str(password)) > _MAX_PASSWORD:
        raise ValueError("The room password is too long")
    return {
        "id": uuid.uuid4().hex[:10],
        "name": name,
        "host": _clean_host(host),
        "port": int(port),
        "instance": str(instance or "").strip(),
        "password": str(password or ""),
        "description": str(description or "").strip()[:_MAX_DESCRIPTION],
        "created": _now(),
    }


def validate_room(room: dict) -> List[str]:
    errors: List[str] = []
    if not isinstance(room, dict):
        return ["Room data must be an object"]
    if not str(room.get("name", "")).strip():
        errors.append("Room name is required")
    elif len(str(room.get("name"))) > _MAX_NAME:
        errors.append("Room name is too long")
    try:
        _clean_host(room.get("host", ""))
    except ValueError as exc:
        errors.append(str(exc))
    try:
        port = int(room.get("port", 25565))
        if not 1 <= port <= 65535:
            errors.append("The port must be between 1 and 65535")
    except (TypeError, ValueError):
        errors.append("The port must be a number")
    if len(str(room.get("password", ""))) > _MAX_PASSWORD:
        errors.append("The room password is too long")
    return errors


def normalize_room(room: dict) -> Dict[str, Any]:
    errors = validate_room(room)
    if errors:
        raise ValueError("; ".join(errors))
    name = str(room.get("name", "")).strip()
    host = _clean_host(room.get("host", ""))
    port = int(room.get("port", 25565))
    identifier = str(room.get("id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", identifier):
        identifier = uuid.uuid4().hex[:10]
    return {
        "id": identifier,
        "name": name[:_MAX_NAME],
        "host": host,
        "port": port,
        "instance": str(room.get("instance", "")).strip(),
        "password": str(room.get("password", "")),
        "description": str(room.get("description", "")).strip()[:_MAX_DESCRIPTION],
        "created": str(room.get("created") or _now()),
    }


def room_address(room: dict) -> str:
    return normalize_address(room.get("host", ""), room.get("port", 25565))


def encode_invite(room: dict) -> str:
    payload = {"v": 1, "room": normalize_room(room)}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return INVITE_PREFIX + encoded


def decode_invite(code: str) -> Dict[str, Any]:
    value = str(code or "").strip()
    if value.upper().startswith(INVITE_PREFIX):
        value = value[len(INVITE_PREFIX):]
    if not value:
        raise ValueError("The invite code is empty")
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(value + padding)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The invite code is damaged") from exc
    room = payload.get("room") if isinstance(payload, dict) else None
    if not isinstance(room, dict):
        raise ValueError("The invite code does not contain a room")
    return normalize_room(room)


def share_text(room: dict) -> str:
    room = normalize_room(room)
    lines = [f"Andromic room: {room['name']}", f"Address: {room_address(room)}"]
    if room.get("instance"):
        lines.append(f"Instance: {room['instance']}")
    if room.get("password"):
        lines.append(f"Password: {room['password']}")
    if room.get("description"):
        lines.append(room["description"])
    lines.append(encode_invite(room))
    return "\n".join(lines)


def find_room(rooms: Iterable[dict], identifier: str) -> Optional[dict]:
    value = str(identifier or "").strip()
    for room in rooms:
        if room.get("id") == value or room.get("name") == value:
            return room
    return None


def add_room(rooms: List[dict], room: dict) -> dict:
    clean = normalize_room(room)
    existing = find_room(rooms, clean["id"])
    if existing is not None:
        rooms[rooms.index(existing)] = clean
        return clean
    names = {str(item.get("name", "")).lower() for item in rooms}
    if clean["name"].lower() in names:
        base, counter = clean["name"], 2
        while f"{base} {counter}".lower() in names:
            counter += 1
        clean["name"] = f"{base} {counter}"
    rooms.append(clean)
    return clean


def remove_room(rooms: List[dict], identifier: str) -> bool:
    room = find_room(rooms, identifier)
    if room is None:
        return False
    rooms.remove(room)
    return True


def room_from_server(entry: dict, instance: str = "") -> Dict[str, Any]:
    host, port = split_address(entry.get("address", ""))
    return new_room(entry.get("name") or host, host, port, instance)


def discovery_packet(room: dict) -> bytes:
    # LAN announcements are broadcast to every device on the local network.
    # Never disclose a room password in these unauthenticated UDP packets.
    public_room = normalize_room(room)
    public_room["password"] = ""
    payload = {"magic": DISCOVERY_MAGIC, "room": public_room, "sent": time.time()}
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_discovery(data: bytes) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(data.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("magic") != DISCOVERY_MAGIC:
            return None
        room = payload.get("room")
        if not isinstance(room, dict):
            return None
        clean = normalize_room(room)
        # Discovery payloads are public metadata, not password-bearing invites.
        clean["password"] = ""
        return clean
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def discover_lan_rooms(timeout: float = 1.5, port: int = DISCOVERY_PORT) -> List[Dict[str, Any]]:
    """Listen for LAN room announcements; returns an empty list when unavailable."""
    deadline = time.time() + max(0.1, float(timeout))
    found: Dict[str, Dict[str, Any]] = {}
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.25)
        sock.bind(("", int(port)))
        while time.time() < deadline:
            try:
                data, _address = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            room = parse_discovery(data)
            if room:
                found[room["id"]] = room
    except OSError:
        return []
    finally:
        if sock is not None:
            sock.close()
    return list(found.values())


def announce_room(room: dict, port: int = DISCOVERY_PORT,
                  broadcasts: Iterable[str] = ("255.255.255.255", "127.0.0.1")) -> int:
    """Broadcast a room announcement; returns the number of successful sends."""
    packet = discovery_packet(room)
    sent = 0
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for address in broadcasts:
            try:
                sock.sendto(packet, (address, int(port)))
                sent += 1
            except OSError:
                continue
    except OSError:
        return 0
    finally:
        if sock is not None:
            sock.close()
    return sent
