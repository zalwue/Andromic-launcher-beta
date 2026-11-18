"""OptiFine installation from a user-supplied installer jar."""
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import List

from .java import ensure_java
from .paths import LIBRARIES, VERSIONS
from .reporter import Reporter
from .system import POPEN_FLAGS
from .versions import ensure_vanilla

_NAME = re.compile(r"OptiFine_(\d+\.\d+(?:\.\d+)?)_(.+?)\.jar$")


def installed_versions(mc: str) -> List[str]:
    if not VERSIONS.exists():
        return []
    prefix = f"{mc}-OptiFine"
    return sorted((d.name for d in VERSIONS.iterdir()
                   if d.name.startswith(prefix) and (d / f"{d.name}.json").exists()),
                  reverse=True)


def install(jar_path: str, manifest: list, java_override: str, rep: Reporter) -> str:
    jar = Path(jar_path)
    match = _NAME.search(jar.name)
    if not match:
        raise RuntimeError("Expected an OptiFine installer named OptiFine_<version>_<edition>.jar")
    mc, edition = match.group(1), match.group(2)
    base = ensure_vanilla(manifest, mc, rep)
    java, _ = ensure_java(base, java_override, rep)

    lib_version = f"{mc}_{edition}"
    version_id = f"{mc}-OptiFine_{edition}"
    lib_dir = LIBRARIES / "optifine" / "OptiFine" / lib_version
    lib_dir.mkdir(parents=True, exist_ok=True)
    patched = lib_dir / f"OptiFine-{lib_version}.jar"

    rep.status("Patching client with OptiFine")
    result = subprocess.run(
        [java, "-cp", str(jar), "optifine.Patcher",
         str(VERSIONS / mc / f"{mc}.jar"), str(jar), str(patched)],
        capture_output=True, text=True, creationflags=POPEN_FLAGS)
    rep.log((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0 or not patched.exists():
        raise RuntimeError("OptiFine patching failed; see the console for details")

    libraries = [{"name": f"optifine:OptiFine:{lib_version}"}]
    with zipfile.ZipFile(jar) as z:
        names = z.namelist()
        if "launchwrapper-of.txt" in names:
            wrapper = z.read("launchwrapper-of.txt").decode("utf-8").strip()
            wrapper_jar = f"launchwrapper-of-{wrapper}.jar"
            if wrapper_jar in names:
                wrapper_dir = LIBRARIES / "optifine" / "launchwrapper-of" / wrapper
                wrapper_dir.mkdir(parents=True, exist_ok=True)
                (wrapper_dir / wrapper_jar).write_bytes(z.read(wrapper_jar))
                libraries.append({"name": f"optifine:launchwrapper-of:{wrapper}"})
        else:
            libraries += [{"name": "net.minecraft:launchwrapper:1.12"},
                          {"name": "net.sf.jopt-simple:jopt-simple:5.0.3"},
                          {"name": "org.ow2.asm:asm-all:5.0.3"}]

    profile = {
        "id": version_id, "inheritsFrom": mc, "type": "release",
        "libraries": libraries,
        "mainClass": "net.minecraft.launchwrapper.Launch",
        "arguments": {"game": ["--tweakClass", "optifine.OptiFineTweaker"], "jvm": []},
    }
    target = VERSIONS / version_id
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{version_id}.json").write_text(json.dumps(profile, indent=2), "utf-8")
    return version_id
