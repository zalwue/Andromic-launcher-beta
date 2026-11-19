import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from andromic.core import instances, updater
from andromic.core.crash import auto_fix_plan
from andromic.core.importers import _loader_from_pack, import_prism_multimc


class UpdaterTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(updater.is_newer("v1.2.0", "1.1.9"))
        self.assertFalse(updater.is_newer("v1.0.0", "1.0"))

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


if __name__ == "__main__":
    unittest.main()
