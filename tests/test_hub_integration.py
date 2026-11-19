import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from hub_integration import (inspect_template, load_card, validate_card, atomic_write_card, find_photo_element,
                              compare_template_preservation, extract_card_preview, open_card_file)

class HubIntegrationTests(unittest.TestCase):
    def test_real_template_preflight(self):
        report = inspect_template(ROOT / 'Templates' / 'New Card Design.card')
        self.assertEqual(report['photo_object'], 'images.jpg')
        self.assertGreater(report['elements'], 0)

    def test_atomic_round_trip_keeps_all_non_photo_properties(self):
        source = ROOT / 'Templates' / 'New Card Design.card'
        design = load_card(source)
        before = json.dumps(design, sort_keys=True)
        with tempfile.TemporaryDirectory() as tmp:
            target = atomic_write_card(Path(tmp) / 'copy.card', design)
            loaded = load_card(target)
            self.assertEqual(json.dumps(loaded, sort_keys=True), before)
            self.assertNotEqual(target.resolve(), source.resolve())


    def test_template_preservation_comparison(self):
        source = ROOT / 'Templates' / 'New Card Design.card'
        with tempfile.TemporaryDirectory() as tmp:
            target = atomic_write_card(Path(tmp) / 'copy.card', load_card(source))
            report = compare_template_preservation(source, target)
            self.assertTrue(report['structure_unchanged'])

    def test_reject_non_photo_template_changes(self):
        source = ROOT / 'Templates' / 'New Card Design.card'
        with tempfile.TemporaryDirectory() as tmp:
            design = load_card(source)
            design['front']['elements'][0]['x'] = float(design['front']['elements'][0].get('x', 0)) + 1
            target = atomic_write_card(Path(tmp) / 'changed.card', design)
            with self.assertRaises(ValueError):
                compare_template_preservation(source, target)

    def test_preview_can_be_extracted(self):
        source = ROOT / 'Templates' / 'New Card Design.card'
        with tempfile.TemporaryDirectory() as tmp:
            target = extract_card_preview(source, Path(tmp) / 'preview.png')
            self.assertTrue(target.is_file())
            self.assertGreater(target.stat().st_size, 100)

    def test_preflight_reports_photo_dimensions(self):
        report = inspect_template(ROOT / 'Templates' / 'New Card Design.card')
        self.assertGreater(report['photo_images']['base64image']['width'], 32)
        self.assertGreater(report['photo_images']['originalBase64Image']['height'], 32)

    def test_missing_or_duplicate_photo_object_rejected(self):
        design = load_card(ROOT / 'Templates' / 'New Card Design.card')
        element = find_photo_element(design)
        design['front']['elements'].remove(element)
        with self.assertRaises(ValueError):
            validate_card(design)

if __name__ == '__main__':
    unittest.main()
