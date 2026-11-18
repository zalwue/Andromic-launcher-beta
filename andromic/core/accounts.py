"""Offline accounts: identifiers, skins and the skin resource pack."""
import base64
import hashlib
import json
import re
import struct
import urllib.parse
import uuid
import zipfile
from pathlib import Path
from typing import Tuple

from .constants import MOJANG_PROFILE_API, MOJANG_SESSION_API
from .net import get_json, http_get
from .paths import SKINS

SKIN_PACK_NAME = "AndromicSkin.zip"
SKIN_PACK_ENTRY = f"file/{SKIN_PACK_NAME}"
_DEFAULT_SKINS = ("steve", "alex", "ari", "efe", "kai", "makena", "noor", "sunny", "zuri")

_PACK_FORMATS = (
    ((1, 16, 2), 6), ((1, 17), 7), ((1, 18), 8), ((1, 19), 9), ((1, 19, 3), 12),
    ((1, 19, 4), 13), ((1, 20), 15), ((1, 20, 2), 18), ((1, 20, 3), 22),
    ((1, 20, 5), 32), ((1, 21), 34), ((1, 21, 2), 42), ((1, 21, 4), 46),
    ((1, 21, 5), 55), ((1, 21, 6), 63), ((1, 21, 7), 64), ((1, 21, 9), 69),
)


def offline_uuid(nick: str) -> str:
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{nick}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def new_account(nick: str = "Player") -> dict:
    return {"id": uuid.uuid4().hex[:8], "nick": nick, "slim": False}


def clean_nick(nick: str) -> str:
    cleaned = "".join(ch for ch in nick if ch.isalnum() or ch == "_")[:16]
    return cleaned or "Player"


def skin_file(account: dict) -> Path:
    return SKINS / f"{account['id']}.png"


def png_size(data: bytes) -> Tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")
    return struct.unpack(">II", data[16:24])


def validate_skin(data: bytes) -> None:
    size = png_size(data)
    if size not in ((64, 64), (64, 32)):
        raise ValueError(f"Skin must be 64x64 or 64x32, got {size[0]}x{size[1]}")


def fetch_mojang_skin(nick: str) -> Tuple[bytes, bool]:
    """Download the public skin of a Mojang account; returns (png, is_slim)."""
    profile = get_json(MOJANG_PROFILE_API + urllib.parse.quote(nick))
    details = get_json(MOJANG_SESSION_API + profile["id"])
    for prop in details.get("properties", []):
        if prop["name"] == "textures":
            textures = json.loads(base64.b64decode(prop["value"]))["textures"]
            skin = textures["SKIN"]
            slim = skin.get("metadata", {}).get("model") == "slim"
            return http_get(skin["url"]), slim
    raise RuntimeError("This account has no skin")


def pack_format(mc: str) -> int:
    nums = tuple(int(n) for n in re.findall(r"\d+", mc.split("-")[0])[:3])
    if nums and nums[0] >= 26:
        return 75
    result = 6
    for threshold, fmt in _PACK_FORMATS:
        if nums >= threshold:
            result = fmt
    return result


def build_skin_pack(png: bytes, mc: str, target: Path) -> None:
    """Resource pack that replaces every default player skin with the given one."""
    meta = {"pack": {
        "pack_format": pack_format(mc),
        "supported_formats": {"min_inclusive": 6, "max_inclusive": 999},
        "description": "Andromic offline skin",
    }}
    base = "assets/minecraft/textures/entity/"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.mcmeta", json.dumps(meta))
        for name in ("steve", "alex"):
            z.writestr(f"{base}{name}.png", png)
        for name in _DEFAULT_SKINS:
            for model in ("wide", "slim"):
                z.writestr(f"{base}player/{model}/{name}.png", png)
