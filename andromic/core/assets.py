"""Asset index, asset objects and client logging configuration."""
import json
from typing import Optional

from .constants import RESOURCES_URL
from .net import download, download_many
from .paths import ASSETS
from .reporter import Reporter


def install_assets(version: dict, rep: Reporter) -> str:
    index = version["assetIndex"]
    index_path = ASSETS / "indexes" / f"{index['id']}.json"
    download(index["url"], index_path, index.get("sha1"), index.get("size"))
    data = json.loads(index_path.read_text("utf-8"))
    items = [
        (f"{RESOURCES_URL}/{obj['hash'][:2]}/{obj['hash']}",
         ASSETS / "objects" / obj["hash"][:2] / obj["hash"], obj["hash"], obj["size"])
        for obj in data["objects"].values()
    ]
    download_many(items, rep, "Assets")
    return index["id"]


def logging_argument(version: dict) -> Optional[str]:
    client = version.get("logging", {}).get("client")
    if not client or not client.get("file"):
        return None
    file = client["file"]
    path = ASSETS / "log_configs" / file["id"]
    download(file["url"], path, file.get("sha1"), file.get("size"))
    return client["argument"].replace("${path}", str(path))
