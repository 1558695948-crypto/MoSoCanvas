from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageCms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from composite_region import composite
from image_contract import sha256
from preflight_validate import validate_preservation_checks
from verify_mask_preservation import verify


class ImageRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source, self.crop, self.mask, self.output = [self.base / name for name in ("source.png", "crop.png", "mask.png", "output.png")]
        self.icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGBA", (9, 9), (51, 61, 71, 81)).save(self.source, icc_profile=self.icc)
        Image.new("RGBA", (3, 3), (151, 161, 171, 181)).save(self.crop, icc_profile=self.icc)
        mask = Image.new("L", (3, 3), 255)
        mask.putpixel((0, 0), 0)
        mask.putpixel((1, 0), 128)
        mask.save(self.mask)

    def repair(self):
        composite(self.source, self.crop, self.mask, (2, 3), self.output)
        return verify(self.source, self.output, self.mask, (2, 3))

    def test_rgba_icc_and_source_immutability(self):
        before = sha256(self.source)
        report = self.repair()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["outside_mask_alpha_changed_pixels"], 0)
        self.assertEqual(report["changed_pixels"], 8)
        self.assertEqual(before, sha256(self.source))
        with Image.open(self.output) as out:
            self.assertEqual(out.mode, "RGBA")
            self.assertEqual(out.info["icc_profile"], self.icc)
            self.assertEqual(out.getpixel((2, 3)), (51, 61, 71, 81))
            self.assertEqual(out.getpixel((3, 3)), (101, 111, 121, 131))

    def test_alpha_only_damage_outside_mask_is_detected(self):
        self.repair()
        with Image.open(self.output) as im:
            out = im.copy()
        out.putpixel((0, 0), (51, 61, 71, 82))
        out.save(self.output, icc_profile=self.icc)
        report = verify(self.source, self.output, self.mask, (2, 3))
        self.assertEqual(report["status"], "block")
        self.assertEqual(report["outside_mask_alpha_changed_pixels"], 1)

    def test_icc_loss_is_detected_even_with_identical_pixels(self):
        self.repair()
        with Image.open(self.output) as im:
            raw = Image.frombytes(im.mode, im.size, im.tobytes())
        raw.save(self.output)
        report = verify(self.source, self.output, self.mask, (2, 3))
        self.assertTrue(report["outside_mask_preserved_exactly"])
        self.assertFalse(report["protected_region_verified"])

    def test_rgb_source_can_accept_rgba_patch(self):
        Image.new("RGB", (9, 9), (51, 61, 71)).save(self.source, icc_profile=self.icc)
        self.assertEqual(self.repair()["status"], "pass")
        with Image.open(self.output) as out:
            self.assertEqual(out.getpixel((0, 0))[3], 255)
            self.assertEqual(out.getpixel((3, 4))[3], 181)

    def test_invalid_bounds_mask_or_overwrite_is_rejected(self):
        for origin, output in (((-1, 0), self.output), ((8, 8), self.output), ((2, 3), self.source), ((2, 3), self.base / "lossy.jpg")):
            with self.assertRaises(ValueError):
                composite(self.source, self.crop, self.mask, origin, output)
        Image.new("RGBA", (3, 3), (255, 255, 255, 0)).save(self.mask)
        with self.assertRaisesRegex(ValueError, "grayscale"):
            self.repair()

    def test_fully_editable_mask_does_not_prove_preservation(self):
        Image.new("L", (9, 9), 255).save(self.mask)
        report = verify(self.source, self.source, self.mask)
        self.assertEqual(report["protected_pixels"], 0)
        self.assertEqual(report["status"], "block")

    def test_hard_link_output_cannot_modify_approved_parent(self):
        self.output.hardlink_to(self.source)
        before = sha256(self.source)
        with self.assertRaisesRegex(ValueError, "hard-link"):
            self.repair()
        self.assertEqual(sha256(self.source), before)

    def test_png_color_key_transparency_survives(self):
        Image.new("RGB", (9, 9), (51, 61, 71)).save(self.source, transparency=(51, 61, 71), icc_profile=self.icc)
        self.assertEqual(self.repair()["status"], "pass")
        with Image.open(self.output) as out:
            self.assertEqual(out.getpixel((0, 0))[3], 0)

    def test_preflight_recomputes_and_rejects_stale_or_forged_reports(self):
        report = self.repair()
        path = self.base / "report.json"
        path.write_text(json.dumps(report))
        state = {"approved_checkpoint": {"role": "approved-output", "source_ref": "source.png", "sha256": sha256(self.source)},
                 "verification": [{"method": "decoded-rgba-and-icc", "status": "pass", "evidence_ref": "report.json"}],
                 "preservation_checks": [{"source_ref": "source.png", "candidate_ref": "output.png", "mask_ref": "mask.png",
                                          "mask_origin": [2, 3], "report_ref": "report.json"}]}
        blockers = []
        validate_preservation_checks(state, self.base, blockers)
        self.assertEqual(blockers, [])
        report["outside_mask_changed_pixels"] = 18
        path.write_text(json.dumps(report))
        validate_preservation_checks(state, self.base, blockers)
        self.assertTrue(blockers)
        path.write_text(json.dumps(self.repair()))
        Image.new("RGBA", (9, 9), (1, 2, 3, 4)).save(self.output)
        blockers = []
        validate_preservation_checks(state, self.base, blockers)
        self.assertTrue(blockers)

    def test_preservation_pass_without_report_cannot_pass_preflight(self):
        blockers = []
        validate_preservation_checks({"verification": [{"method": "decoded-rgba-and-icc", "status": "pass"}]}, self.base, blockers)
        self.assertTrue(blockers)


if __name__ == "__main__":
    unittest.main()
