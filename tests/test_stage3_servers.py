"""Stage 3 server tests: validation, recommended list, persistence shape."""
import unittest

from andromic.core import servers
from andromic.core.config import migrate_config


class AddressValidationTests(unittest.TestCase):
    def test_default_port_25565(self):
        self.assertEqual(servers.validate_address("mc.example.com"), ("mc.example.com", 25565))
        self.assertEqual(servers.normalize_address("mc.example.com"), "mc.example.com:25565")

    def test_host_port(self):
        self.assertEqual(servers.validate_address("example.com:25566"), ("example.com", 25566))
        self.assertEqual(servers.normalize_address(" example.com:1234 "), "example.com:1234")

    def test_ipv4_and_localhost(self):
        self.assertEqual(servers.validate_address("127.0.0.1:25565"), ("127.0.0.1", 25565))
        self.assertEqual(servers.validate_address("localhost"), ("localhost", 25565))

    def test_ipv6(self):
        self.assertEqual(servers.validate_address("[::1]:25565"), ("::1", 25565))
        self.assertEqual(servers.validate_address("[::1]"), ("::1", 25565))
        self.assertEqual(servers.normalize_address("[::1]:25565"), "[::1]:25565")

    def test_invalid_port_rejected(self):
        for bad in ("host:0", "host:65536", "host:-1", "host:abc", "host:", "host:1.5",
                    "host:99999", "host: 12", "host:12x"):
            with self.assertRaises(ValueError, msg=bad):
                servers.validate_address(bad)

    def test_invalid_host_rejected(self):
        for bad in ("", "   ", "host name", "host:1:2", "http://x", "host/", "host\\",
                    "a b", "[::1", "[::1]x", "[::1]:x"):
            with self.assertRaises(ValueError, msg=bad):
                servers.validate_address(bad)

    def test_non_string_rejected(self):
        with self.assertRaises(ValueError):
            servers.validate_address(None)
        with self.assertRaises(ValueError):
            servers.validate_address(123)


class ServerListTests(unittest.TestCase):
    def test_recommended_servers_present(self):
        self.assertTrue(servers.RECOMMENDED_SERVERS)
        for entry in servers.RECOMMENDED_SERVERS:
            self.assertTrue(entry["name"])
            host, port = servers.validate_address(entry["address"])
            self.assertTrue(host)
            self.assertEqual(port, 25565)
            self.assertTrue(entry.get("recommended"))

    def test_recommended_visible_only_without_custom(self):
        self.assertTrue(servers.recommended_visible([]))
        self.assertFalse(servers.recommended_visible([{"name": "A", "address": "a:25565"}]))
        # recommended-tagged entries don't count as custom
        self.assertTrue(servers.recommended_visible(
            [{"name": "R", "address": "a:25565", "recommended": True}]))

    def test_visible_servers_recommended_then_custom(self):
        self.assertEqual(servers.visible_servers([]), servers.RECOMMENDED_SERVERS)
        custom = [{"name": "A", "address": "a.example.com:25565"}]
        self.assertEqual(servers.visible_servers(custom), custom)
        # removing all custom restores recommendations
        self.assertEqual(servers.visible_servers([]), servers.RECOMMENDED_SERVERS)

    def test_recommended_never_deleted(self):
        lst = [{"name": "A", "address": "a.example.com:25565"}]
        servers.remove_server(lst, 0)
        self.assertEqual(lst, [])
        self.assertTrue(servers.RECOMMENDED_SERVERS)  # source untouched
        self.assertEqual(servers.visible_servers(lst), servers.RECOMMENDED_SERVERS)

    def test_add_edit_remove(self):
        lst = []
        entry = servers.add_server(lst, "My Server", "example.com")
        self.assertEqual(entry, {"name": "My Server", "address": "example.com:25565"})
        servers.add_server(lst, "Other", "example.org:1234")
        self.assertEqual(len(lst), 2)
        servers.edit_server(lst, 0, "Renamed", "example.com:9999")
        self.assertEqual(lst[0], {"name": "Renamed", "address": "example.com:9999"})
        self.assertNotIn("recommended", lst[0])
        removed = servers.remove_server(lst, 0)
        self.assertEqual(removed["name"], "Renamed")
        self.assertEqual(len(lst), 1)
        self.assertIsNone(servers.remove_server(lst, 5))

    def test_add_invalid_raises(self):
        with self.assertRaises(ValueError):
            servers.add_server([], "x", "bad host:99999")
        with self.assertRaises(ValueError):
            servers.add_server([], "x", "")

    def test_normalize_server_entry_repairs(self):
        self.assertEqual(servers.normalize_server_entry("example.com"),
                         {"name": "example.com", "address": "example.com:25565"})
        self.assertEqual(servers.normalize_server_entry({"name": "N", "address": "example.com"}),
                         {"name": "N", "address": "example.com:25565"})
        self.assertIsNone(servers.normalize_server_entry({"name": "N"}))
        self.assertIsNone(servers.normalize_server_entry({"name": "N", "address": "bad host"}))
        self.assertIsNone(servers.normalize_server_entry(42))
        self.assertIsNone(servers.normalize_server_entry({"name": "N", "address": "h:0"}))

    def test_split_address_compatible(self):
        self.assertEqual(servers.split_address("example.com"), ("example.com", 25565))
        self.assertEqual(servers.split_address("example.com:1234"), ("example.com", 1234))
        self.assertEqual(servers.split_address("[::1]:9999"), ("::1", 9999))

    def test_ping_offline_graceful(self):
        result = servers.ping("127.0.0.1:1", timeout=0.5)
        self.assertFalse(result["online"])


class ServerConfigMigrationTests(unittest.TestCase):
    def test_migration_normalises_and_preserves_servers(self):
        cfg = {"servers": [
            {"name": "Good", "address": "example.com"},
            {"name": "", "address": "example.org:1234"},
            {"name": "Broken", "address": "not a host"},
            "junk",
            {"name": "Dup", "address": "example.com"},
        ]}
        out = migrate_config(cfg)
        addrs = [s["address"] for s in out["servers"]]
        self.assertIn("example.com:25565", addrs)
        self.assertIn("example.org:1234", addrs)
        self.assertNotIn("not a host", str(addrs))
        # duplicate (name-insensitive address dup) removed where identical
        self.assertEqual(len(addrs), len(set(addrs)))
        # recommendations are not injected into saved custom list
        self.assertFalse(any(s.get("recommended") for s in out["servers"]))

    def test_migration_servers_not_list(self):
        out = migrate_config({"servers": "nope"})
        self.assertEqual(out["servers"], [])

    def test_recommended_servers_not_removed_by_hiding(self):
        cfg = migrate_config({"servers": [{"name": "A", "address": "a:25565"}]})
        self.assertTrue(servers.RECOMMENDED_SERVERS)
        self.assertFalse(servers.recommended_visible(cfg["servers"]))
        cfg["servers"].clear()
        self.assertTrue(servers.recommended_visible(cfg["servers"]))


if __name__ == "__main__":
    unittest.main()
