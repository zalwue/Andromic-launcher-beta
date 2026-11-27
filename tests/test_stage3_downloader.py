"""Stage 3 downloader tests: streaming, .part, verification, retry, cancel, threads."""
import hashlib
import http.server
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from andromic.core import net
from andromic.core.config import DEFAULTS, migrate_config


class _Server:
    def __init__(self, handler):
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path="/x"):
        return f"http://127.0.0.1:{self.port}{path}"

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _quiet(handler):
    handler.log_message = lambda *a, **k: None
    return handler


class StreamingHandler(http.server.BaseHTTPRequestHandler):
    payload = b""
    chunks = 1

    def do_GET(self):
        data = self.payload
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        step = max(1, len(data) // self.chunks)
        for i in range(0, len(data), step):
            try:
                self.wfile.write(data[i:i + step])
                self.wfile.flush()
            except Exception:
                return
            time.sleep(0.001)

    def log_message(self, *args, **kwargs):
        pass


class DownloadPipelineTests(unittest.TestCase):
    def test_streaming_part_atomic_sha1_size_and_skip_valid(self):
        payload = os.urandom(150_000)
        sha1 = hashlib.sha1(payload).hexdigest()
        handler = _quiet(type("H", (StreamingHandler,), {"payload": payload, "chunks": 50}))
        server = _Server(handler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "file.bin"
                net.download(server.url(), dest, sha1=sha1, size=len(payload))
                self.assertEqual(dest.read_bytes(), payload)
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
                # correct file is not re-downloaded
                mtime = dest.stat().st_mtime_ns
                net.download(server.url(), dest, sha1=sha1, size=len(payload))
                self.assertEqual(dest.stat().st_mtime_ns, mtime)
        finally:
            server.stop()

    def test_chunk_size_constant(self):
        self.assertGreaterEqual(net.CHUNK_SIZE, 1024)
        # download streams; it never does resp.read() into memory for files.

    def test_size_mismatch_deletes_part_and_keeps_no_output(self):
        payload = b"hello world" * 100
        handler = _quiet(type("H", (StreamingHandler,), {"payload": payload, "chunks": 4}))
        server = _Server(handler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "f.bin"
                with self.assertRaises((net.DownloadError, IOError)):
                    net.download(server.url(), dest, size=len(payload) + 5, retries=1)
                self.assertFalse(dest.exists())
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
        finally:
            server.stop()

    def test_sha1_mismatch_deletes_part(self):
        payload = b"data" * 1000
        handler = _quiet(type("H", (StreamingHandler,), {"payload": payload, "chunks": 8}))
        server = _Server(handler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "f.bin"
                with self.assertRaises(net.ChecksumMismatch):
                    net.download(server.url(), dest, sha1="0" * 40, retries=1)
                self.assertFalse(dest.exists())
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
        finally:
            server.stop()

    def test_retry_on_temporary_network_error(self):
        payload = os.urandom(4000)
        state = {"n": 0}

        class Flaky(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                state["n"] += 1
                if state["n"] < 3:
                    self.send_response(503)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a, **k):
                pass

        server = _Server(Flaky)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "r.bin"
                net.download(server.url(), dest, retries=5)
                self.assertEqual(dest.read_bytes(), payload)
                self.assertGreaterEqual(state["n"], 3)
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
        finally:
            server.stop()

    def test_no_retry_on_permanent_error(self):
        class NotFound(http.server.BaseHTTPRequestHandler):
            calls = {"n": 0}

            def do_GET(self):
                NotFound.calls["n"] += 1
                self.send_response(404)
                self.end_headers()

            def log_message(self, *a, **k):
                pass

        server = _Server(NotFound)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(Exception):
                    net.download(server.url(), Path(tmp) / "x", retries=5)
                self.assertEqual(NotFound.calls["n"], 1)
                self.assertFalse((Path(tmp) / "x.part").exists())
        finally:
            server.stop()

    def test_cancellation_cleans_part(self):
        payload = os.urandom(64 * 1024 * 4)
        handler = _quiet(type("H", (StreamingHandler,), {"payload": payload, "chunks": 256}))
        server = _Server(handler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                token = net.CancelToken()
                dest = Path(tmp) / "c.bin"
                with self.assertRaises(net.DownloadCancelled):
                    net.download(server.url(), dest, cancel=token,
                                 progress=lambda d, t: token.cancel())
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
                self.assertFalse(dest.exists())
        finally:
            server.stop()

    def test_cancel_token(self):
        token = net.CancelToken()
        self.assertFalse(token.cancelled)
        token.cancel()
        self.assertTrue(token.is_cancelled())
        with self.assertRaises(net.DownloadCancelled):
            token.raise_if_cancelled()
        token.reset()
        self.assertFalse(token.cancelled)

    def test_download_many_progress_speed_eta_and_cleanup(self):
        payload = os.urandom(8192)
        sha1 = hashlib.sha1(payload).hexdigest()
        handler = _quiet(type("H", (StreamingHandler,), {"payload": payload, "chunks": 8}))
        server = _Server(handler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                items = [(server.url(f"/x{i}"), tmp / f"f{i}.bin", sha1, len(payload))
                         for i in range(6)]
                events = []
                rep = net.Reporter(progress=lambda d, t, label="": events.append(("p", d, t)),
                                   download=lambda info: events.append(("d", info)))
                net.download_many(items, rep, "Test", workers=4)
                self.assertTrue(events[-1] == ("p", 6, 6) or events[-1][0] == "d")
                # last file-progress event is complete
                file_events = [e for e in events if e[0] == "p"]
                self.assertEqual(file_events[-1], ("p", 6, 6))
                dl = [e[1] for e in events if e[0] == "d"]
                self.assertTrue(any(getattr(p, "speed_bps", 0) >= 0 for p in dl))
                self.assertTrue(any(getattr(p, "files_total", 0) == 6 for p in dl))
                self.assertTrue(any(getattr(p, "done_bytes", 0) > 0 for p in dl))
                for i in range(6):
                    self.assertEqual((tmp / f"f{i}.bin").read_bytes(), payload)
                self.assertFalse(list(tmp.glob("*.part")))
        finally:
            server.stop()

    def test_download_many_cancel_no_part_left(self):
        payload = os.urandom(8192)
        handler = _quiet(type("H", (StreamingHandler,), {"payload": payload, "chunks": 64}))
        server = _Server(handler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                items = [(server.url(f"/x{i}"), tmp / f"f{i}.bin", None, len(payload))
                         for i in range(20)]
                token = net.CancelToken()
                timer = threading.Timer(0.02, token.cancel)
                timer.start()
                with self.assertRaises(net.DownloadCancelled):
                    net.download_many(items, net.Reporter(), "C", workers=8, cancel=token)
                self.assertFalse(list(tmp.glob("*.part")))
        finally:
            server.stop()


class ThreadModeTests(unittest.TestCase):
    def test_modes_and_defaults(self):
        self.assertEqual(net.THREAD_MODES["economy"], 2)
        self.assertEqual(net.THREAD_MODES["balanced"], 4)
        self.assertEqual(net.THREAD_MODES["fast"], 8)
        self.assertEqual(net.THREAD_MODES["maximum"], 12)
        self.assertIsNone(net.THREAD_MODES["manual"])
        self.assertEqual(net.DEFAULT_THREAD_MODE, "fast")
        self.assertEqual(net.configured_workers({"download_threads": "fast"}), 8)

    def test_resolve_workers(self):
        self.assertEqual(net.resolve_workers(None, {"download_threads": "economy"}), 2)
        self.assertEqual(net.resolve_workers(None, {"download_threads": "balanced"}), 4)
        self.assertEqual(net.resolve_workers(None, {"download_threads": "fast"}), 8)
        self.assertEqual(net.resolve_workers(None, {"download_threads": "maximum"}), 12)
        self.assertEqual(net.resolve_workers(None, {"download_threads": "manual",
                                                    "download_threads_manual": 6}), 6)
        self.assertEqual(net.resolve_workers(None, {"download_threads": "manual",
                                                    "download_threads_manual": 999}), 32)
        self.assertEqual(net.resolve_workers(None, {"download_threads": "manual",
                                                    "download_threads_manual": 0}), 1)
        self.assertEqual(net.resolve_workers(None, {"download_threads": "nonsense"}), 8)
        self.assertEqual(net.resolve_workers(3, {"download_threads": "fast"}), 3)
        self.assertLessEqual(net.resolve_workers(None, {"download_threads": "manual",
                                                         "download_threads_manual": 99999}),
                             net.MAX_WORKERS)

    def test_set_thread_mode_persists_values(self):
        net.set_thread_mode("manual", 7)
        self.assertEqual(net.thread_mode(), "manual")
        self.assertEqual(net.manual_threads(), 7)
        self.assertEqual(net.configured_workers(), 7)
        net.set_thread_mode("fast", 8)

    def test_apply_thread_config(self):
        net.apply_thread_config({"download_threads": "maximum", "download_threads_manual": 5})
        self.assertEqual(net.configured_workers(), 12)
        net.apply_thread_config({"download_threads": "manual", "download_threads_manual": 5})
        self.assertEqual(net.configured_workers(), 5)
        net.apply_thread_config({})

    def test_clamp_workers(self):
        self.assertEqual(net.clamp_workers(-5), 1)
        self.assertEqual(net.clamp_workers(100000), 32)
        self.assertEqual(net.clamp_workers("nope"), 8)
        self.assertEqual(net.clamp_workers(None), 8)


class FormatTests(unittest.TestCase):
    def test_format_bytes_speed_eta(self):
        self.assertEqual(net.format_bytes(0), "0 B")
        self.assertIn("KB", net.format_bytes(2048))
        self.assertIn("MB", net.format_bytes(5 * 1024 * 1024))
        self.assertTrue(net.format_speed(1024).endswith("/s"))
        self.assertEqual(net.format_eta(None), "—")
        self.assertEqual(net.format_eta(45), "45s")
        self.assertIn("m", net.format_eta(125))

    def test_progress_fraction(self):
        p = net.DownloadProgress(done_bytes=50, total_bytes=100)
        self.assertEqual(p.fraction, 0.5)
        p2 = net.DownloadProgress(files_done=1, files_total=4)
        self.assertEqual(p2.fraction, 0.25)


class ConfigMigrationTests(unittest.TestCase):
    def test_defaults_have_download_settings(self):
        self.assertEqual(DEFAULTS["download_threads"], "fast")
        self.assertEqual(DEFAULTS["download_threads_manual"], 8)

    def test_migrate_old_config(self):
        old = {"theme": "dark", "ram": 2048, "servers": [{"name": "X", "address": "example.com"}]}
        out = migrate_config(dict(old))
        self.assertEqual(out["download_threads"], "fast")
        self.assertEqual(out["download_threads_manual"], 8)
        self.assertEqual(out["servers"][0]["address"], "example.com:25565")
        self.assertEqual(out["ram"], 2048)
        self.assertIn("customization", out)

    def test_migrate_invalid_download_values(self):
        out = migrate_config({"download_threads": "bogus", "download_threads_manual": "x"})
        self.assertEqual(out["download_threads"], "fast")
        self.assertEqual(out["download_threads_manual"], 8)
        out = migrate_config({"download_threads": "MANUAL", "download_threads_manual": 99999})
        self.assertEqual(out["download_threads"], "manual")
        self.assertEqual(out["download_threads_manual"], 32)

    def test_migrate_keeps_unknown_keys(self):
        out = migrate_config({"future_key": 123})
        self.assertEqual(out["future_key"], 123)


if __name__ == "__main__":
    unittest.main()
