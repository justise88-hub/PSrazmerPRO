"""Smoke tests for PSrazmer PRO 2.7 data and template invariants.
Run with: python -m unittest discover -s tests
"""
import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "Templates" / "New Card Design.card"

class CoreInvariantTests(unittest.TestCase):
    def test_template_has_single_photo_object(self):
        design = json.loads(TEMPLATE.read_text(encoding="utf-8-sig"))
        elements = design.get("front", {}).get("elements", [])
        photos = [e for e in elements if e.get("name") == "Image" and e.get("fileName", "").lower() == "images.jpg"]
        self.assertEqual(len(photos), 1)
        self.assertTrue(photos[0].get("base64image", "").startswith("data:image/"))

    def test_sqlite_unique_number_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite3"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE employees(id INTEGER PRIMARY KEY, badge_number TEXT)")
            con.execute("CREATE UNIQUE INDEX ux_badge ON employees(badge_number) WHERE badge_number<>''")
            con.execute("CREATE TABLE audit_log(id INTEGER PRIMARY KEY, event_type TEXT NOT NULL)")
            con.execute("INSERT INTO employees(badge_number) VALUES(?)", ("000101",))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO employees(badge_number) VALUES(?)", ("000101",))
            con.execute("INSERT INTO audit_log(event_type) VALUES(?)", ("employee_created",))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 1)
            con.close()

if __name__ == "__main__":
    unittest.main()


class UpdateVersionTests(unittest.TestCase):
    def test_version_comparison_normalizes_trailing_zeroes(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        from version_utils import version_tuple
        self.assertEqual(version_tuple("2.8"), version_tuple("2.8.0"))
        self.assertGreater(version_tuple("2.8.1"), version_tuple("2.8.0"))
        self.assertGreater(version_tuple("3.0.0"), version_tuple("2.99.9"))


class ResponsiveLayoutTests(unittest.TestCase):
    def test_startup_size_adapts_to_common_monitor_sizes(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        from version_utils import startup_window_metrics
        small = startup_window_metrics(800, 600)
        full_hd = startup_window_metrics(1920, 1080)
        self.assertLessEqual(small[2], 800)
        self.assertLessEqual(small[3], 600)
        self.assertEqual(full_hd[2:], (1440, 940))

    def test_startup_size_rejects_invalid_monitor(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        from version_utils import startup_window_metrics
        with self.assertRaises(ValueError):
            startup_window_metrics(0, 1080)
