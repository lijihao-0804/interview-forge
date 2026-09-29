import json
from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ManifestIconTests(unittest.TestCase):
    def test_manifest_icons_exist_and_match_declared_png_dimensions(self):
        manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
        icons = manifest["icons"]
        self.assertTrue(any(icon.get("purpose") == "maskable" for icon in icons))
        for icon in icons:
            path = ROOT / icon["src"]
            self.assertTrue(path.is_file(), icon["src"])
            image = path.read_bytes()
            self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n", icon["src"])
            width, height = struct.unpack(">II", image[16:24])
            expected = tuple(int(value) for value in icon["sizes"].split("x"))
            self.assertEqual((width, height), expected, icon["src"])


if __name__ == "__main__":
    unittest.main()
