"""Heuristic crash log analysis."""
import re
from typing import Iterable, List

_HINTS = (
    (r"UnsupportedClassVersionError", "The Java version does not match this game or mod. "
     "Clear the custom Java path in Settings so Andromic can choose it automatically."),
    (r"OutOfMemoryError", "The game ran out of memory. Increase the allocated RAM in Settings."),
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


def analyze(lines: Iterable[str]) -> List[str]:
    text = "\n".join(lines)
    return [hint for pattern, hint in _HINTS if re.search(pattern, text, re.IGNORECASE)]
