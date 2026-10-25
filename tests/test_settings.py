import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ds2port.settings import load_connection_settings, save_connection_settings, settings_path


class ConnectionSettings(unittest.TestCase):
    def test_missing_or_damaged_preferences_do_not_prevent_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for content in (None, b"{broken", b"\xff", b"[]", b"null"):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_bytes(content)
                    saved = load_connection_settings(path)
                    self.assertEqual(saved, {"host": "", "username": "root", "save_password": False, "password": ""})

    def test_password_is_not_saved_without_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_connection_settings(" 192.0.2.10 ", " root ", "one-time-password", False, path)
            saved = load_connection_settings(path)
            self.assertEqual((saved["host"], saved["username"]), ("192.0.2.10", "root"))
            self.assertEqual(saved["password"], "")
            self.assertNotIn("password", json.loads(path.read_text(encoding="utf-8")))
            self.assertNotIn("one-time-password", path.read_text(encoding="utf-8"))

    def test_opt_in_round_trips_unicode_and_password_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences/settings.json"
            password = "  テスト用 パスワード  "
            save_connection_settings("192.0.2.20", "plumos", password, True, path)
            self.assertEqual(load_connection_settings(path), {
                "host": "192.0.2.20", "username": "plumos", "save_password": True, "password": password})

    def test_disabling_storage_removes_previously_saved_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_connection_settings("192.0.2.10", "root", "old-saved-password", True, path)
            save_connection_settings("192.0.2.30", "plumos", "old-saved-password", False, path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("password", data)
            self.assertFalse(data["save_password"])
            self.assertEqual(load_connection_settings(path)["host"], "192.0.2.30")

    def test_malformed_opt_in_never_restores_a_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for opt_in in (False, "true", 1, None):
                with self.subTest(opt_in=opt_in):
                    path.write_text(json.dumps({"save_password": opt_in, "password": "hidden", "host": []}), encoding="utf-8")
                    saved = load_connection_settings(path)
                    self.assertFalse(saved["save_password"])
                    self.assertEqual(saved["password"], "")
                    self.assertEqual(saved["host"], "")

    def test_failed_replace_preserves_previous_settings_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_connection_settings("192.0.2.10", "root", "", False, path)
            original = path.read_bytes()
            with patch("ds2port.settings.os.replace", side_effect=PermissionError("read only")):
                with self.assertRaises(PermissionError):
                    save_connection_settings("192.0.2.20", "root", "temporary-password", True, path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_preferences_use_the_user_profile_instead_of_the_executable_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertEqual(settings_path(), Path(directory) / "ds2port-v90s/settings.json")


if __name__ == "__main__":
    unittest.main()
