import json
import os
import py_compile
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from andromic.core import (backup, command, customization, diagnostics, instances,
                           paths, rooms, system, worlds)
from andromic.core import updater, java
from andromic.core.crash import auto_fix_plan
from andromic.core.importers import _loader_from_pack, import_prism_multimc


class UpdaterTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(updater.is_newer("v1.2.0", "1.1.9"))
        self.assertFalse(updater.is_newer("v1.0.0", "1.0"))

    def test_prerelease_ordering(self):
        self.assertTrue(updater.is_newer("v2.1.0", "2.1.0b1"))
        self.assertTrue(updater.is_newer("v2.1.0b2", "2.1.0b1"))
        self.assertFalse(updater.is_newer("v2.1.0b1", "2.1.0"))
        self.assertFalse(updater.is_newer("v2.1.0b1", "2.1.0b2"))
        self.assertFalse(updater.is_newer("v2.1.0b1", "2.1b1"))

    def test_selects_windows_executable(self):
        assets = [
            {"name": "Andromic-v2-linux.zip"},
            {"name": "Andromic-v2-windows.exe"},
        ]
        with patch.object(updater, "OS", "windows"):
            self.assertEqual(updater._asset_for_current_os(assets)["name"],
                             "Andromic-v2-windows.exe")


class ImporterTests(unittest.TestCase):
    def test_detects_forge_even_if_metadata_order_differs(self):
        pack = {"components": [
            {"uid": "net.minecraftforge", "version": "47.2.0"},
            {"uid": "net.minecraft", "version": "1.20.1"},
        ]}
        self.assertEqual(_loader_from_pack(pack), ("1.20.1", "Forge", "1.20.1-47.2.0"))

    def test_imports_prism_overrides(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = root / "export.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("Pack/mmc-pack.json", json.dumps({"components": [
                    {"uid": "net.minecraft", "version": "1.20.1"},
                    {"uid": "net.fabricmc.fabric-loader", "version": "0.15.11"},
                ]}))
                archive.writestr("Pack/overrides/.minecraft/options.txt", "test")
            with patch.object(instances, "INSTANCES", root / "instances"):
                record = import_prism_multimc(archive_path, "export", [])
                target = instances.instance_dir(record) / "options.txt"
                self.assertEqual(record["loader"], "Fabric")
                self.assertEqual(target.read_text("utf-8"), "test")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = root / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("mmc-pack.json", json.dumps({"components": [
                    {"uid": "net.minecraft", "version": "1.20.1"},
                ]}))
                archive.writestr("overrides/../../outside.txt", "bad")
            with patch.object(instances, "INSTANCES", root / "instances"):
                with self.assertRaises(ValueError):
                    import_prism_multimc(archive_path, "bad", [])


class CrashFixTests(unittest.TestCase):
    def test_custom_java_is_reset_for_version_error(self):
        plan = auto_fix_plan(
            ["java.lang.UnsupportedClassVersionError"],
            {"java_path": "/invalid/java", "ram": 4096, "fabric_api": True},
            {"loader": "Fabric"}, 8192,
        )
        self.assertEqual(plan["changes"]["java_path"], "")


# ---------------------------------------------------------------------------
# Cross-platform paths and process helpers
# ---------------------------------------------------------------------------

class PathAndPlatformTests(unittest.TestCase):
    def test_layout_and_ensure_dirs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Andromic"
            layout = paths.layout(root)
            self.assertIn("backups", layout)
            self.assertIn("diagnostics", layout)
            paths.ensure_dirs(root)
            for directory in layout.values():
                self.assertTrue(directory.is_dir(), directory)
            self.assertTrue(paths.is_writable(root))
            self.assertGreater(paths.free_space_mb(root), 0)

    def test_atomic_write_and_unique_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "nested" / "file.txt"
            paths.atomic_write_text(target, "hello")
            self.assertEqual(target.read_text("utf-8"), "hello")
            duplicate = paths.unique_path(target)
            self.assertEqual(duplicate.name, "file (2).txt")
            self.assertTrue(paths.path_inside(root, target))
            self.assertFalse(paths.path_inside(root / "other", target))
            self.assertTrue(paths.safe_remove_tree(root / "nested"))
            self.assertFalse(paths.safe_remove_tree(root / "missing"))

    def test_windows_long_path_prefix(self):
        long_path = "C:\\Users\\Player\\" + ("very-long-folder\\" * 20) + "file.txt"
        with patch.object(paths, "OS", "windows"):
            converted = paths.long_path(long_path)
            self.assertTrue(converted.startswith("\\\\?\\"))
            self.assertEqual(paths.long_path("C:\\short.txt"), "C:\\short.txt")
        with patch.object(paths, "OS", "linux"):
            self.assertEqual(paths.long_path(long_path), long_path)

    def test_data_dir_per_platform(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(system, "OS", "windows"), patch.dict(
                    os.environ, {"APPDATA": str(root / "Roaming")}, clear=False):
                self.assertEqual(system.data_dir(), root / "Roaming" / "Andromic")
            with patch.object(system, "OS", "linux"), patch.dict(
                    os.environ, {"XDG_DATA_HOME": str(root / "xdg")}, clear=False):
                self.assertEqual(system.data_dir(), root / "xdg" / "Andromic")
            with patch.object(system, "OS", "osx"), patch.object(
                    system.Path, "home", return_value=root / "home"):
                self.assertEqual(system.data_dir(),
                                 root / "home" / "Library" / "Application Support" / "Andromic")

    def test_runtime_keys_for_all_platforms(self):
        cases = (
            ("windows", "x64", "windows-x64", ("windows", "x64")),
            ("windows", "x86", "windows-x86", ("windows", "x32")),
            ("windows", "arm64", "windows-arm64", ("windows", "aarch64")),
            ("osx", "arm64", "mac-os-arm64", ("mac", "aarch64")),
            ("osx", "x64", "mac-os", ("mac", "x64")),
            ("linux", "x64", "linux", ("linux", "x64")),
            ("linux", "x86", "linux-i386", ("linux", "x32")),
        )
        for os_name, arch, key, target in cases:
            with patch.object(system, "OS", os_name), patch.object(system, "ARCH", arch):
                self.assertEqual(system.mojang_runtime_key(), key)
                self.assertEqual(system.adoptium_target(), target)
        self.assertGreater(system.total_ram_mb(), 0)

    def test_java_search_tolerates_permission_errors(self):
        with patch.object(Path, "is_dir", side_effect=PermissionError("denied")):
            self.assertIsNone(java.find_java(Path("/restricted/java")))

    def test_java_discovery_and_override(self):
        from andromic.core import java
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "bin" / system.JAVA_BIN
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\nexit 0\n", "utf-8")
            self.assertEqual(java.find_java(root), binary)
            self.assertEqual(java.resolve_override(str(binary)), str(binary))
            self.assertEqual(java.resolve_override(str(root)), str(binary))
            self.assertIsNone(java.resolve_override(str(root / "missing")))
            self.assertIsNone(java.find_java(root / "missing"))
        self.assertEqual(java.guess_major("1.20.1"), 17)
        self.assertEqual(java.guess_major("1.21.4"), 21)
        self.assertEqual(java.guess_major("1.8.9"), 8)
        with patch.object(java.subprocess, "run",
                          return_value=SimpleNamespace(stdout='openjdk version "21.0.2" 2024')):
            self.assertEqual(java.java_major(Path("java")), 21)

    def test_command_uses_platform_classpath_and_mac_flags(self):
        version = {
            "type": "release",
            "mainClass": "net.minecraft.client.main.Main",
            "arguments": {
                "jvm": ["-cp", "${classpath}"],
                "game": ["--username", "${auth_player_name}"],
            },
        }
        settings = {"width": "1280", "height": "720", "ram": 2048,
                    "optimize_jvm": True, "jvm_args": "-Dfoo=bar", "fullscreen": False}
        with patch.object(command, "CLASSPATH_SEP", ";"):
            result = command.build_command(
                version, "1.20.1", "java", settings, "Player", "/tmp/game",
                ["a.jar", "b.jar", "a.jar"], "/tmp/natives", "5", extra_jvm=["-Dbar=baz"])
        self.assertEqual(result[0], "java")
        self.assertIn("-Xmx2048M", result)
        self.assertIn("a.jar;b.jar", result)
        self.assertIn("-Dfoo=bar", result)
        self.assertIn("-Dbar=baz", result)
        self.assertIn("-Dfile.encoding=UTF-8", result)
        with patch.object(command, "OS", "osx"):
            mac = command.build_command(
                version, "1.20.1", "java", settings, "Player", "/tmp/game",
                ["a.jar"], "/tmp/natives", "5")
        self.assertIn("-XstartOnFirstThread", mac)
        self.assertIn("-Xdock:name=Minecraft", mac)

    def test_command_legacy_ipv6_server_fallback(self):
        version = {"type": "release", "mainClass": "Main",
                   "minecraftArguments": "--username ${auth_player_name}"}
        settings = {"width": "800", "height": "600", "ram": 1024,
                    "optimize_jvm": False, "jvm_args": "", "fullscreen": True}
        result = command.build_command(
            version, "1.8.9", "java", settings, "Player", "/tmp/game",
            ["client.jar"], "/tmp/natives", "legacy", server="2001:db8::1")
        self.assertIn("--fullscreen", result)
        self.assertEqual(result[result.index("--server") + 1], "2001:db8::1")
        self.assertEqual(result[result.index("--port") + 1], "25565")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class DiagnosticsTests(unittest.TestCase):
    def test_run_diagnostics_and_safe_fixes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            cfg = {"accounts": [{"id": "abc", "nick": "Player"}], "instances": [],
                   "servers": [], "rooms": [], "theme": "light", "accent_color": "#3482FF",
                   "ram": 4096, "width": "1280", "height": "720"}
            report = diagnostics.run_diagnostics(root=root, cfg=cfg)
            self.assertIn(report["status"], ("ok", "warn", "error"))
            ids = {check["id"] for check in report["checks"]}
            self.assertTrue({"paths", "config", "java", "instances", "backups"} <= ids)
            self.assertIn("Data folder:", diagnostics.format_report(report))
            actions = diagnostics.apply_safe_fixes(root)
            self.assertTrue(any("versions" in action for action in actions))
            self.assertEqual(diagnostics.apply_safe_fixes(root), [])
            self.assertEqual(diagnostics.check_directories(root)["status"], "ok")
            saved = diagnostics.save_report(report, root / "reports")
            self.assertTrue(saved.is_file())
            self.assertIn("Andromic Launcher diagnostics", saved.read_text("utf-8"))

    def test_config_and_log_checks(self):
        bad = diagnostics.check_config({"theme": "neon", "ram": 999999,
                                        "width": "not-a-number", "accounts": [],
                                        "instances": [], "servers": [],
                                        "java_path": "/definitely/missing/java"})
        self.assertEqual(bad["status"], "warn")
        self.assertIn("theme", bad["details"])
        good = diagnostics.check_config({"theme": "dark", "ram": 2048, "width": "1280",
                                         "height": "720", "accounts": [{"id": "1"}],
                                         "instances": [], "servers": []})
        self.assertEqual(good["status"], "ok")
        analysis = diagnostics.analyze_log([
            "java.lang.UnsupportedClassVersionError: bad",
            "java.lang.OutOfMemoryError: Java heap space",
        ])
        self.assertEqual(len(analysis["hints"]), 2)
        self.assertTrue(any("OutOfMemory" in line for line in analysis["errors"]))

    def test_backups_check_and_stale_parts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup_dir = root / "backups"
            backup_dir.mkdir()
            with patch.object(diagnostics, "BACKUPS", backup_dir):
                self.assertEqual(diagnostics.check_backups()["status"], "ok")
            partial = root / "downloads" / "file.part"
            partial.parent.mkdir(parents=True)
            partial.write_text("partial")
            old = time.time() - 7200
            os.utime(partial, (old, old))
            actions = diagnostics.apply_safe_fixes(root)
            self.assertFalse(partial.exists())
            self.assertTrue(any("partial" in action for action in actions))


# ---------------------------------------------------------------------------
# World manager and NBT
# ---------------------------------------------------------------------------

def _level_root(name="Test World", last_played=1700000000000, game_type=1):
    return worlds.Tag(10, {
        "Data": worlds.Tag(10, {
            "LevelName": worlds.Tag(8, name),
            "LastPlayed": worlds.Tag(4, last_played),
            "GameType": worlds.Tag(3, game_type),
            "Difficulty": worlds.Tag(1, 2),
            "hardcore": worlds.Tag(1, 0),
            "DataVersion": worlds.Tag(3, 3465),
            "DayTime": worlds.Tag(4, 1000),
            "Version": worlds.Tag(10, {"Name": worlds.Tag(8, "1.20.1")}),
        })
    })


class WorldTests(unittest.TestCase):
    def _make_instance(self, root, name="Test"):
        instance = {"name": name, "mc": "1.20.1"}
        saves = root / "instances" / name / "saves"
        saves.mkdir(parents=True)
        return instance, saves

    def test_nbt_roundtrip_and_tag_paths(self):
        root = _level_root("Roundtrip")
        payload = worlds.write_nbt_bytes(root)
        self.assertEqual(payload[:2], b"\x1f\x8b")
        restored = worlds.read_nbt_bytes(payload)
        self.assertEqual(worlds.tag_value(restored, "Data.LevelName"), "Roundtrip")
        self.assertTrue(worlds.set_tag(restored, "Data.Custom.Nested",
                                       worlds.Tag(8, "value")))
        self.assertEqual(worlds.tag_value(restored, "Data.Custom.Nested"), "value")
        self.assertIsNone(worlds.tag_path(restored, "Data.Missing"))
        uncompressed = worlds.write_nbt_bytes(restored, compress=False)
        self.assertNotEqual(uncompressed[:2], b"\x1f\x8b")
        self.assertEqual(worlds.tag_value(worlds.read_nbt_bytes(uncompressed),
                                          "Data.Custom.Nested"), "value")

    def test_world_listing_rename_duplicate_export_import_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(instances, "INSTANCES", root / "instances"):
                instance, saves = self._make_instance(root)
                world = saves / "World"
                (world / "region").mkdir(parents=True)
                worlds.write_nbt_file(world / "level.dat", _level_root("My World"))
                (world / "icon.png").write_bytes(b"png")
                (world / "region" / "r.0.0.mca").write_bytes(b"region")

                listing = worlds.list_worlds(instance)
                self.assertEqual(len(listing), 1)
                self.assertEqual(listing[0]["name"], "My World")
                self.assertEqual(listing[0]["game_type"], "Creative")
                self.assertEqual(listing[0]["version"], "1.20.1")
                self.assertGreater(listing[0]["size"], 0)
                self.assertTrue(listing[0]["last_played"].startswith("2023-11-14"))

                renamed = worlds.rename_world(instance, "World", "Renamed World")
                self.assertEqual(renamed.name, "Renamed World")
                self.assertEqual(worlds.list_worlds(instance)[0]["name"], "Renamed World")

                duplicate = worlds.duplicate_world(instance, "Renamed World", "Copy")
                self.assertTrue((duplicate / "level.dat").is_file())
                self.assertEqual(len(worlds.list_worlds(instance)), 2)

                archive = worlds.export_world(instance, "Renamed World", root / "export.zip")
                with zipfile.ZipFile(archive) as z:
                    self.assertIn("Renamed World/level.dat", z.namelist())
                imported = worlds.import_world(instance, archive, "Imported")
                self.assertTrue((imported / "level.dat").is_file())
                self.assertEqual(worlds.read_level_info(imported)["name"], "Imported")

                self.assertTrue(worlds.delete_world(instance, "Renamed World"))
                self.assertFalse((saves / "Renamed World").exists())

    def test_world_import_rejects_traversal_and_broken_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(instances, "INSTANCES", root / "instances"):
                instance, saves = self._make_instance(root)
                bad = root / "bad.zip"
                with zipfile.ZipFile(bad, "w") as archive:
                    archive.writestr("level.dat", worlds.write_nbt_bytes(_level_root()))
                    archive.writestr("../outside.txt", "bad")
                with self.assertRaises(ValueError):
                    worlds.import_world(instance, bad)
                self.assertFalse((root / "outside.txt").exists())
                broken = root / "broken.zip"
                with zipfile.ZipFile(broken, "w") as archive:
                    archive.writestr("readme.txt", "no world")
                with self.assertRaises(ValueError):
                    worlds.import_world(instance, broken)
                broken_world = saves / "Broken"
                broken_world.mkdir()
                (broken_world / "level.dat").write_bytes(b"not nbt")
                info = worlds.read_level_info(broken_world)
                self.assertTrue(info["error"])


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

class BackupTests(unittest.TestCase):
    def _instance(self, root):
        instance = {"name": "Test", "mc": "1.20.1"}
        base = root / "instances" / "Test"
        (base / "saves" / "World").mkdir(parents=True)
        worlds.write_nbt_file(base / "saves" / "World" / "level.dat",
                              _level_root("Backup World"))
        (base / "mods").mkdir()
        (base / "mods" / "example.jar").write_bytes(b"jar")
        (base / "options.txt").write_text("fov:70\n", "utf-8")
        return instance, base

    def test_create_list_verify_restore_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(instances, "INSTANCES", root / "instances"):
                instance, base = self._instance(root)
                backup_dir = root / "backups"
                archive = backup.create_backup(instance, "worlds", backup_root=backup_dir)
                self.assertIsNotNone(archive)
                self.assertTrue(archive.is_file())
                info = backup.backup_info(archive)
                self.assertTrue(info["valid"])
                self.assertEqual(info["instance"], "Test")
                self.assertEqual(info["scope"], "worlds")
                self.assertEqual(len(backup.list_backups(instance, backup_dir)), 1)
                self.assertTrue(backup.verify_backup(archive)["valid"])

                full = backup.create_backup(instance, "instance", note="nightly",
                                            backup_root=backup_dir)
                full_info = backup.backup_info(full)
                self.assertEqual(full_info["scope"], "instance")
                self.assertEqual(full_info["note"], "nightly")
                with zipfile.ZipFile(full) as z:
                    self.assertIn("mods/example.jar", z.namelist())
                    self.assertIn("options.txt", z.namelist())
                    self.assertIn(backup.MANIFEST_NAME, z.namelist())

                restored = root / "restored"
                backup.restore_backup(archive, target=restored)
                self.assertTrue((restored / "saves" / "World" / "level.dat").is_file())
                with self.assertRaises(FileExistsError):
                    backup.restore_backup(archive, target=restored, overwrite=False)

                self.assertTrue(backup.delete_backup(archive))
                self.assertFalse(archive.exists())
                summary = backup.backup_summary(instance, backup_dir)
                self.assertEqual(summary["count"], 1)

    def test_restore_rejects_traversal_and_prune_keeps_newest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(instances, "INSTANCES", root / "instances"):
                instance, base = self._instance(root)
                backup_dir = root / "backups"
                bad = root / "bad.zip"
                with zipfile.ZipFile(bad, "w") as z:
                    z.writestr("../outside.txt", "bad")
                with self.assertRaises(ValueError):
                    backup.restore_backup(bad, target=root / "restore")
                self.assertFalse((root / "outside.txt").exists())

                for note in ("one", "two", "three"):
                    self.assertIsNotNone(backup.create_backup(
                        instance, "worlds", note=note, backup_root=backup_dir))
                self.assertEqual(len(backup.list_backups(instance, backup_dir)), 3)
                backup.prune_backups(instance, keep=1, backup_root=backup_dir)
                self.assertEqual(len(backup.list_backups(instance, backup_dir)), 1)

    def test_empty_backup_and_legacy_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(instances, "INSTANCES", root / "instances"):
                empty = {"name": "Empty"}
                (root / "instances" / "Empty").mkdir(parents=True)
                self.assertIsNone(backup.create_backup(empty, backup_root=root / "backups"))
                instance, base = self._instance(root)
                with patch.object(instances, "BACKUPS", root / "legacy"):
                    legacy = instances.backup_worlds(instance, keep=5)
                self.assertIsNotNone(legacy)
                info = backup.backup_info(legacy)
                self.assertTrue(info["valid"])
                self.assertEqual(info["instance"], "Test")
                self.assertEqual(info["scope"], "worlds")


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

class RoomTests(unittest.TestCase):
    def test_room_validation_addresses_and_invites(self):
        room = rooms.new_room("SMP", "mc.example.com", 25566, "Main",
                              "secret", "Friends only")
        self.assertEqual(rooms.validate_room(room), [])
        self.assertEqual(rooms.room_address(room), "mc.example.com:25566")
        ipv6 = rooms.new_room("IPv6", "2001:db8::1", 25565)
        self.assertEqual(rooms.room_address(ipv6), "[2001:db8::1]:25565")
        self.assertEqual(rooms.split_address("[2001:db8::1]:25566"),
                         ("2001:db8::1", 25566))
        self.assertEqual(rooms.split_address("example.com"), ("example.com", 25565))

        code = rooms.encode_invite(room)
        self.assertTrue(code.startswith(rooms.INVITE_PREFIX))
        decoded = rooms.decode_invite(code)
        self.assertEqual(decoded["name"], "SMP")
        self.assertEqual(decoded["password"], "secret")
        self.assertIn("Address: mc.example.com:25566", rooms.share_text(room))
        with self.assertRaises(ValueError):
            rooms.decode_invite(code[:-3] + "!!!")
        with self.assertRaises(ValueError):
            rooms.new_room("Bad", "host with spaces")

    def test_room_collection_and_server_conversion(self):
        room = rooms.new_room("SMP", "host", 25565)
        collection = []
        rooms.add_room(collection, room)
        duplicate = rooms.add_room(collection, rooms.new_room("SMP", "host2", 25566))
        self.assertEqual(duplicate["name"], "SMP 2")
        self.assertIs(rooms.find_room(collection, room["id"]), collection[0])
        self.assertTrue(rooms.remove_room(collection, room["id"]))
        self.assertFalse(rooms.remove_room(collection, "missing"))
        converted = rooms.room_from_server({"name": "Server", "address": "host:25570"},
                                           "Main")
        self.assertEqual(converted["port"], 25570)
        self.assertEqual(converted["instance"], "Main")

    def test_lan_discovery_packets_and_graceful_failure(self):
        room = rooms.new_room("LAN", "192.168.1.10", 25565, password="private")
        packet = rooms.discovery_packet(room)
        self.assertNotIn(b"private", packet)
        parsed = rooms.parse_discovery(packet)
        self.assertEqual(parsed["name"], "LAN")
        self.assertEqual(parsed["password"], "")
        self.assertIsNone(rooms.parse_discovery(b"not json"))

        class FakeSocket:
            def __init__(self):
                self.closed = False

            def setsockopt(self, *args):
                pass

            def settimeout(self, *args):
                pass

            def bind(self, *args):
                raise OSError("no network")

            def close(self):
                self.closed = True

        fake = FakeSocket()
        with patch.object(rooms.socket, "socket", return_value=fake):
            self.assertEqual(rooms.discover_lan_rooms(0.2), [])
        self.assertTrue(fake.closed)

        class SendSocket(FakeSocket):
            def bind(self, *args):
                pass

            def sendto(self, *args):
                raise OSError("blocked")

        with patch.object(rooms.socket, "socket", return_value=SendSocket()):
            self.assertEqual(rooms.announce_room(room), 0)


# ---------------------------------------------------------------------------
# Customization
# ---------------------------------------------------------------------------

class CustomizationTests(unittest.TestCase):
    def test_colour_normalisation_and_contrast(self):
        self.assertEqual(customization.normalize_hex("#abc"), "#AABBCC")
        self.assertEqual(customization.normalize_hex("3482ff"), "#3482FF")
        self.assertEqual(customization.normalize_hex("not-a-colour", "#000000"), "#000000")
        self.assertGreater(customization.contrast_ratio("#000000", "#FFFFFF"), 20)
        self.assertIn(customization.readable_text("#FFFFFF"), ("#000000", "#FFFFFF"))
        self.assertEqual(len(customization.list_presets()), len(customization.PRESETS))

    def test_presets_save_export_import(self):
        cfg = {"theme": "light", "accent_color": "#3482FF"}
        custom = customization.apply_preset(cfg, "midnight")
        self.assertEqual(cfg["theme"], "dark")
        self.assertEqual(cfg["accent_color"], custom["accent_color"])
        self.assertEqual(customization.from_config(cfg)["preset"], "midnight")

        updated = customization.save_customization(cfg, {
            "preset": "forest", "theme": "light", "accent_color": "#123456",
            "density": "compact", "animations": False, "corner_radius": 99,
            "font_scale": 1, "background": "#ffffff", "sidebar_position": "right",
        })
        self.assertEqual(updated["corner_radius"], 32)
        self.assertEqual(updated["font_scale"], 85)
        self.assertFalse(updated["animations"])
        self.assertEqual(updated["sidebar_position"], "right")
        self.assertTrue(updated["frosted_glass"])
        self.assertEqual(updated["wallpaper_path"], "")
        self.assertEqual(cfg["theme"], "light")

        glass = customization.save_customization(cfg, {
            "preset": "midnight", "theme": "dark", "accent_color": "#7AA2FF",
            "wallpaper_path": "/tmp/andromic-wallpaper.jpg", "frosted_glass": False,
        })
        self.assertEqual(glass["wallpaper_path"], "/tmp/andromic-wallpaper.jpg")
        self.assertFalse(glass["frosted_glass"])

        text = customization.export_theme(updated)
        restored = customization.import_theme(text)
        self.assertEqual(restored["sidebar_position"], "right")
        self.assertEqual(restored["accent_color"], "#123456")
        self.assertEqual(restored["background"], "#FFFFFF")
        with self.assertRaises(ValueError):
            customization.import_theme("{not json")
        with self.assertRaises(ValueError):
            customization.import_theme('{"schema": 1}')

        values = customization.css_values(updated)
        self.assertEqual(values["accent"], "#123456")
        self.assertEqual(values["density"], "compact")
        self.assertEqual(values["animations"], "0")
        self.assertIn("radius", values)

    def test_legacy_config_without_customization(self):
        cfg = {"theme": "dark", "accent_color": "#112233"}
        custom = customization.from_config(cfg)
        self.assertEqual(custom["theme"], "dark")
        self.assertEqual(custom["sidebar_position"], "left")
        self.assertEqual(custom["accent_color"], "#112233")
        normalized = customization.normalize_customization({"theme": "strange"})
        self.assertEqual(normalized["theme"], "light")


# ---------------------------------------------------------------------------
# Packaging / build scripts
# ---------------------------------------------------------------------------

class PackagingTests(unittest.TestCase):
    def test_build_scripts_include_new_modules(self):
        root = Path(__file__).resolve().parents[1]
        shell = (root / "build.sh").read_text("utf-8")
        batch = (root / "build.bat").read_text("utf-8")
        for script in (shell, batch):
            self.assertIn("--collect-submodules andromic", script)
            self.assertIn("--collect-all PySide6", script)
            self.assertIn("assets", script)
            self.assertIn("main.py", script)
        self.assertIn("--icon=assets/icon.png", shell)
        self.assertIn("-march=x86-64 -mtune=generic", shell)
        self.assertIn("Ubuntu 22.04", shell)
        self.assertNotIn('CFLAGS="-march=native', shell)
        self.assertNotIn('CXXFLAGS="-march=native', shell)
        self.assertIn("--icon=assets/icon.ico", batch)

    def test_source_zip_contains_every_new_file(self):
        root = Path(__file__).resolve().parents[1]
        expected = [
            "andromic/core/diagnostics.py",
            "andromic/core/worlds.py",
            "andromic/core/backup.py",
            "andromic/core/rooms.py",
            "andromic/core/customization.py",
            "andromic/ui/pages/worlds.py",
            "andromic/ui/pages/rooms.py",
            "andromic/ui/pages/customization.py",
            "andromic/ui/pages/diagnostics.py",
        ]
        for relative in expected:
            self.assertTrue((root / relative).is_file(), relative)
            py_compile.compile(str(root / relative), doraise=True)
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "release.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for relative in expected + ["main.py", "requirements.txt",
                                            "assets/icon.png", "build.sh", "build.bat"]:
                    archive.write(root / relative, relative)
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
            self.assertTrue(set(expected) <= names)
            self.assertIn("main.py", names)
            self.assertIn("assets/icon.png", names)

    def test_qt_cpu_compatibility_policy_is_pinned(self):
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text("utf-8")
        project = (root / "pyproject.toml").read_text("utf-8")
        version = (root / "andromic" / "__init__.py").read_text("utf-8")
        self.assertIn("PySide6==6.9.3", requirements)
        self.assertIn('dependencies = ["PySide6==6.9.3"]', project)
        self.assertIn('2.1.0b1', version)
        smoke = root / "tools" / "qt_cpu_smoke.py"
        self.assertTrue(smoke.is_file())
        py_compile.compile(str(smoke), doraise=True)

    def test_workflow_runs_legacy_cpu_qt_smoke_test(self):
        root = Path(__file__).resolve().parents[1]
        workflow_path = root / ".github" / "workflows" / "build.yml"
        self.assertTrue(workflow_path.is_file(), "GitHub Actions workflow must be bundled")
        workflow = workflow_path.read_text("utf-8")
        self.assertIn("ubuntu-22.04", workflow)
        self.assertIn("qemu-user", workflow)
        self.assertIn("qemu-x86_64 -cpu Nehalem,-sse4.2,-popcnt", workflow)
        self.assertIn("tools/qt_cpu_smoke.py", workflow)


class ElyIntegrationTests(unittest.TestCase):
    def test_authenticate_builds_yggdrasil_account_without_saving_password(self):
        from andromic.core import ely
        response = {
            "accessToken": "token-value",
            "clientToken": "client-value",
            "selectedProfile": {"id": "0123456789abcdef0123456789abcdef", "name": "ElyPlayer"},
        }
        with patch.object(ely, "_post", return_value=response) as post:
            account = ely.authenticate("mail@example.test", "secret", "client-value", "123456")
        self.assertEqual(post.call_args.args[0], ely.AUTHENTICATE_URL)
        payload = post.call_args.args[1]
        self.assertEqual(payload["password"], "secret:123456")
        self.assertEqual(account["type"], "ely")
        self.assertEqual(account["uuid"], "0123456789abcdef0123456789abcdef")
        self.assertNotIn("password", account)

    def test_authenticate_maps_two_factor_error(self):
        from andromic.core.ely import ElyAuthError
        error = ElyAuthError("Account protected with two factor auth.", status=401)
        self.assertTrue(error.needs_2fa)

    def test_command_uses_ely_credentials_and_agent(self):
        version = {"type": "release", "mainClass": "Main", "arguments": {
            "jvm": ["-cp", "${classpath}"], "game": ["--username", "${auth_player_name}",
                                                           "--uuid", "${auth_uuid}",
                                                           "--token", "${auth_access_token}", "--type", "${user_type}"]}}
        settings = {"width": "1280", "height": "720", "ram": 2048,
                    "optimize_jvm": False, "jvm_args": "", "fullscreen": False}
        account = {"id": "ely-1", "type": "ely", "nick": "ElyPlayer",
                   "uuid": "0123456789abcdef0123456789abcdef", "accessToken": "secret-token"}
        result = command.build_command(version, "1.21.4", "java", settings, "ignored",
                                        "/tmp/game", ["client.jar"], "/tmp/natives", "5",
                                        account=account, authlib_injector="/tmp/authlib.jar")
        self.assertIn("-javaagent:/tmp/authlib.jar=ely.by", result)
        self.assertIn("--username", result)
        self.assertIn("ElyPlayer", result)
        self.assertIn("0123456789abcdef0123456789abcdef", result)
        self.assertIn("secret-token", result)
        self.assertIn("mojang", result)

    def test_post_json_encodes_json_payload(self):
        from andromic.core import net
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return b'{"ok":true}'
        with patch.object(net.urllib.request, "urlopen", return_value=Response()) as opener:
            result = net.post_json("https://example.test", {"hello": "world"})
        self.assertEqual(result, {"ok": True})
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, b'{"hello": "world"}')

    def test_refresh_updates_token_and_keeps_client_token(self):
        from andromic.core import ely
        account = {"id": "ely-old", "type": "ely", "nick": "OldName",
                   "uuid": "0123456789abcdef0123456789abcdef",
                   "accessToken": "old-token", "clientToken": "stable-client"}
        response = {"accessToken": "new-token", "clientToken": "stable-client",
                    "selectedProfile": {"id": "0123456789abcdef0123456789abcdef", "name": "NewName"}}
        with patch.object(ely, "_post", return_value=response) as post:
            ely.refresh_account(account)
        self.assertEqual(post.call_args.args[0], ely.REFRESH_URL)
        self.assertEqual(post.call_args.args[1]["clientToken"], "stable-client")
        self.assertEqual(account["accessToken"], "new-token")
        self.assertEqual(account["nick"], "NewName")

    def test_config_file_is_private_on_posix(self):
        from andromic.core import config
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "config.json"
            with patch.object(config, "CONFIG_FILE", target):
                config.save_config({"accounts": [{"type": "ely", "accessToken": "token"}]})
            if os.name != "nt":
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
