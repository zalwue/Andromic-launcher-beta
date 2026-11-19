"""Heuristic crash-log analysis and conservative one-click fix suggestions."""
import re
from typing import Iterable, List

_HINTS = (
    (r"UnsupportedClassVersionError", "The Java version does not match this game or mod. "
     "Clear the custom Java path in Settings so Andromic can choose it automatically."),
    (r"OutOfMemoryError", "The game ran out of memory. Check the allocated RAM in Settings."),
    (r"Could not reserve enough space", "The requested memory could not be allocated. "
     "Lower the RAM value in Settings."),
    (r"requires.*fabric-api|fabric-api.*(missing|not found)|Fabric API",
     "A mod needs Fabric API. Install it from the Content page."),
    (r"Incompatible mod set|Mod resolution failed|Could not find required mod",
     "Mod dependency conflict. Check that every mod matches the game version and loader."),
    (r"NoSuchMethodError|NoClassDefFoundError|AbstractMethodError",
     "A mod is incompatible with this version or loader."),
    (r"GLFW error|pixel format|OpenGL",
     "Graphics initialisation failed. Update your GPU drivers."),
    (r"UnknownHostException|Connection reset|Failed to download",
     "A network error occurred. Check your connection and try again."),
)


def _text(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def analyze(lines: Iterable[str]) -> List[str]:
    text = _text(lines)
    return [hint for pattern, hint in _HINTS if re.search(pattern, text, re.IGNORECASE)]


def auto_fix_plan(lines: Iterable[str], settings: dict, instance: dict,
                  total_ram_mb: int) -> dict:
    """Build only low-risk, reversible settings fixes; never delete user mods/files."""
    log = _text(lines)
    changes, actions = {}, []
    if re.search(r"UnsupportedClassVersionError", log, re.IGNORECASE):
        if settings.get("java_path"):
            changes["java_path"] = ""
            actions.append("Use the Java runtime selected automatically for this Minecraft version.")
    if re.search(r"Could not reserve enough space", log, re.IGNORECASE):
        current = int(settings.get("ram", 4096))
        target = max(512, min(current - 512, int(max(1024, total_ram_mb * 0.45))))
        if target < current:
            changes["ram"] = target
            actions.append(f"Reduce allocated memory from {current} MB to {target} MB.")
    elif re.search(r"OutOfMemoryError", log, re.IGNORECASE):
        current = int(settings.get("ram", 4096))
        safe_limit = max(1024, int(total_ram_mb * 0.70))
        target = min(safe_limit, max(current + 512, 2048))
        if target > current:
            changes["ram"] = target
            actions.append(f"Increase allocated memory from {current} MB to {target} MB.")
    if re.search(r"requires.*fabric-api|fabric-api.*(missing|not found)|Fabric API", log,
                 re.IGNORECASE):
        if instance.get("loader") in ("Fabric", "Quilt"):
            if not settings.get("fabric_api", True):
                changes["fabric_api"] = True
                actions.append("Enable automatic installation of Fabric API / QSL.")
            else:
                actions.append("Retry the automatic Fabric API / QSL installation.")
    return {"changes": changes, "actions": actions}
