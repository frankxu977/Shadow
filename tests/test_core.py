"""Regression tests for registry failures, transitions, and local history."""
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shadow.monitor import CameraApp, Snapshot, Tracker, scan_camera, filetime_to_iso, describe_app
from shadow.storage import Store


def app(name="chrome.exe", start="2026-09-11T10:00:00+00:00"):
    return CameraApp(name, name, "C:\\Apps\\" + name, start)


class TrackerTests(unittest.TestCase):
    def test_start_repeat_stop(self):
        tracker = Tracker()
        camera = app()
        snapshot = Snapshot({camera.identity: camera})
        self.assertEqual(tracker.update(snapshot), ([camera], []))
        self.assertEqual(tracker.update(snapshot), ([], []))
        self.assertEqual(tracker.update(Snapshot()), ([], [camera]))

    def test_failure_does_not_stop_known_app(self):
        tracker = Tracker()
        camera = app()
        tracker.update(Snapshot({camera.identity: camera}))
        self.assertEqual(tracker.update(Snapshot(errors=["Denied"])), ([], []))
        self.assertIn(camera.identity, tracker.active)
        self.assertEqual(tracker.update(Snapshot()), ([], [camera]))

    def test_second_app_and_restart(self):
        tracker = Tracker()
        chrome, zoom = app(), app("zoom.exe")
        tracker.update(Snapshot({chrome.identity: chrome}))
        self.assertEqual(tracker.update(Snapshot({chrome.identity: chrome, zoom.identity: zoom})), ([zoom], []))
        restarted = app(start="2026-09-11T10:10:00+00:00")
        started, stopped = tracker.update(Snapshot({restarted.identity: restarted, zoom.identity: zoom}))
        self.assertEqual(started, [restarted])
        self.assertEqual(stopped, [chrome])


class FakeKey:
    def __init__(self, values=None, children=None, denied=False):
        self.values = values or {}
        self.children = children or {}
        self.denied = denied
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    def __init__(self, root):
        self.root = root
    def OpenKey(self, parent, name, *args):
        key = self.root if parent == "HKCU" else parent.children[name]
        if key is None:
            raise FileNotFoundError("Missing root")
        if key.denied:
            raise PermissionError("Access denied")
        return key
    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], 11
    def EnumKey(self, key, index):
        keys = list(key.children)
        if index >= len(keys):
            error = OSError("No more entries")
            error.winerror = 259
            raise error
        return keys[index]


class RegistryTests(unittest.TestCase):
    def test_denied_sibling_does_not_hide_active_record(self):
        root = FakeKey(children={"denied": FakeKey(denied=True), "good": FakeKey(values={
            "LastUsedTimeStart": 133000000000000000, "LastUsedTimeStop": 0})})
        result = scan_camera(FakeRegistry(root))
        self.assertFalse(result.reliable)
        self.assertIn("good", result.apps)

    def test_missing_root_is_unknown(self):
        self.assertFalse(scan_camera(FakeRegistry(None)).reliable)

    def test_missing_stop_is_unknown(self):
        root = FakeKey(children={"app": FakeKey(values={"LastUsedTimeStart": 4})})
        self.assertFalse(scan_camera(FakeRegistry(root)).reliable)

    def test_empty_root_is_idle(self):
        result = scan_camera(FakeRegistry(FakeKey()))
        self.assertTrue(result.reliable)
        self.assertEqual(result.apps, {})

    def test_names_and_filetime(self):
        record = describe_app(r"NonPackaged\C:#Apps#chrome.exe", None)
        self.assertEqual(record.name, "chrome.exe")
        self.assertEqual(record.path, r"C:\Apps\chrome.exe")
        self.assertIsNone(filetime_to_iso(0))
        self.assertIsNone(filetime_to_iso(10 ** 40))
        self.assertTrue(filetime_to_iso(116444736000000000).startswith("1970-01-01"))


class StorageTests(unittest.TestCase):
    def test_sessions_mute_export_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            store = Store(path)
            store.start(app())
            store.stop(app())
            self.assertEqual(store.rows()[0]["status"], "stopped")
            store.start(app("=unsafe.exe"))
            store.set("muted", ["chrome.exe"])
            store.close()
            store = Store(path)
            self.assertEqual(store.get("muted"), ["chrome.exe"])
            self.assertEqual(store.rows()[0]["status"], "interrupted")
            self.assertIsNone(store.rows()[0]["duration_seconds"])
            target = Path(directory) / "export.csv"
            store.export(target)
            self.assertIn("'=unsafe.exe", target.read_text(encoding="utf-8-sig"))
            store.close()


if __name__ == "__main__":
    unittest.main()
