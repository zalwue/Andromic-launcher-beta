"""Installation pipeline and game process management."""
import os
import subprocess
from collections import deque
from typing import Callable, List, Optional

from . import accounts, ely, net, optifine
from .assets import install_assets, logging_argument
from .command import build_command
from .config import sanitize_settings, save_config
from .instances import backup_worlds, instance_dir
from .java import ensure_java
from .libraries import extract_natives, install_libraries
from .loaders import install_loader
from .modrinth import install_project, mod_loaders
from .options import apply_settings
from .paths import VERSIONS
from .reporter import Reporter
from .system import POPEN_FLAGS
from .versions import ensure_vanilla, load_version


class GameLauncher:
    def __init__(self, manifest: List[dict], rep: Reporter):
        self.manifest = manifest
        self.rep = rep
        self.log_tail = deque(maxlen=400)

    def _resolve_version(self, inst: dict, java: str) -> str:
        loader = inst["loader"]
        if loader == "Vanilla":
            return inst["mc"]
        if loader == "OptiFine":
            version_id = inst["lv"]
            if not (VERSIONS / version_id / f"{version_id}.json").exists():
                raise RuntimeError("OptiFine is not installed for this version. "
                                   "Install it from the instance settings.")
            return version_id
        return install_loader(loader, inst["mc"], inst["lv"], java, self.rep)

    def _ensure_fabric_api(self, inst: dict, game_dir) -> None:
        if inst["loader"] not in ("Fabric", "Quilt"):
            return
        mods = game_dir / "mods"
        existing = [f.lower() for f in os.listdir(mods)] if mods.exists() else []
        if any("fabric-api" in f or "qsl" in f for f in existing):
            return
        self.rep.status("Installing Fabric API")
        slug = "fabric-api" if inst["loader"] == "Fabric" else "qsl"
        try:
            install_project(slug, mods, inst["mc"], mod_loaders(inst["loader"]), True, self.rep.log)
        except net.DownloadCancelled:
            raise
        except Exception as exc:
            self.rep.log(f"Fabric API installation skipped: {exc}")

    def _prepare_instance(self, settings: dict, inst: dict, account: dict, game_dir) -> None:
        game_dir.mkdir(parents=True, exist_ok=True)
        if settings["fabric_api"]:
            self._ensure_fabric_api(inst, game_dir)
        if settings["auto_backup"]:
            self.rep.status("Backing up worlds")
            backup_worlds(inst)
        skin = accounts.skin_file(account)
        pack = game_dir / "resourcepacks" / accounts.SKIN_PACK_NAME
        has_local_skin = account.get("type") != "ely" and skin.exists()
        if has_local_skin:
            accounts.build_skin_pack(skin.read_bytes(), inst["mc"], pack)
        elif pack.exists():
            pack.unlink()
        apply_settings(game_dir, settings, has_local_skin)

    def run(self, cfg: dict, inst: dict, account: dict,
            on_java: Optional[Callable[[int], None]] = None,
            on_start: Optional[Callable[[], None]] = None,
            cancel: "Optional[net.CancelToken]" = None) -> int:
        rep = self.rep
        settings = sanitize_settings(cfg)
        # Apply download concurrency to every download in this session.
        net.set_thread_mode(settings["download_threads"], settings["download_threads_manual"])
        previous_cancel = net.set_default_cancel(cancel)
        try:
            if cancel is not None:
                cancel.raise_if_cancelled()
            return self._run_inner(cfg, inst, account, settings, on_java, on_start, rep)
        finally:
            net.set_default_cancel(previous_cancel)

    def _run_inner(self, cfg, inst, account, settings, on_java, on_start, rep) -> int:
        authlib_path = ""
        if account.get("type") == "ely":
            rep.status("Refreshing Ely.by session")
            ely.refresh_account(account)
            save_config(cfg)
            authlib_path = str(ely.ensure_authlib_injector())
        base = ensure_vanilla(self.manifest, inst["mc"], rep)
        java, major = ensure_java(base, settings["java_path"], rep)
        if on_java:
            on_java(major)
        version_id = self._resolve_version(inst, java)
        version = load_version(version_id)

        classpath, native_archives = install_libraries(version, rep)
        natives_dir = extract_natives(native_archives, version_id)
        rep.status("Checking assets")
        asset_index = install_assets(version, rep)

        game_dir = instance_dir(inst)
        self._prepare_instance(settings, inst, account, game_dir)

        root = version["_root"]
        client = VERSIONS / root / f"{root}.jar"
        entries = []
        for path in [*classpath, client]:
            if str(path) not in entries:
                entries.append(str(path))
        log_arg = logging_argument(version)
        nick = accounts.clean_nick(account["nick"])
        command = build_command(
            version, version_id, java, settings, nick, game_dir, entries, natives_dir,
            asset_index, inst.get("server", "").strip(), [log_arg] if log_arg else [],
            account=account, authlib_injector=authlib_path)

        rep.log("-" * 48)
        rep.log(f"Launching {version_id} as {nick} (Java {major}, {settings['ram']} MB)")
        rep.status("Game is running")
        rep.progress(0, 1)
        if on_start:
            on_start()
        self.log_tail.clear()
        proc = subprocess.Popen(
            command, cwd=str(game_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=POPEN_FLAGS)
        for line in proc.stdout:
            line = line.rstrip()
            self.log_tail.append(line)
            rep.log(line)
        code = proc.wait()
        rep.log(f"Game exited with code {code}")
        return code

    def _restore_download_state(self, previous_cancel) -> None:
        net.set_default_cancel(previous_cancel)
