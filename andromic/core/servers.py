"""Minecraft server list ping (status protocol)."""
import json
import re
import socket
import struct
import time
from typing import Tuple


def split_address(address: str) -> Tuple[str, int]:
    address = address.strip()
    host, sep, port = address.rpartition(":")
    if sep and host and port.isdigit():
        return host, int(port)
    return address, 25565


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
    host, port = split_address(address)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            handshake = (_varint(0x00) + _varint(-1) + _string(host)
                         + struct.pack(">H", port) + _varint(1))
            sock.sendall(_packet(handshake) + _packet(_varint(0x00)))
            _read_varint(sock)
            if _read_varint(sock) != 0x00:
                raise ValueError("unexpected packet")
            length = _read_varint(sock)
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
