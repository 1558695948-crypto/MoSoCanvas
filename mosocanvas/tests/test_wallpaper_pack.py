from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from PIL import Image


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_CLI = SKILL_ROOT.parent / "bin" / "mosocanvas"
# Installed skill archives contain the standalone script, not the repository-level CLI wrapper.
ENTRYPOINT = ([str(REPOSITORY_CLI), "wallpaper-pack"] if REPOSITORY_CLI.is_file()
              else [str(SKILL_ROOT / "scripts" / "wallpaper_pack.py")])


class WallpaperPackTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *ENTRYPOINT, *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_landscape_source_routes_to_computer_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "love-is-fury.png"
            output = root / "pack"
            Image.new("RGB", (160, 100), (112, 12, 18)).save(source)
            (output / "signed").mkdir(parents=True)
            (output / "signed" / "stale-old-output.png").write_bytes(b"stale")

            result = self.run_cli(str(source), "--output-dir", str(output))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["generated_count"], 3)
            self.assertEqual(summary["skipped_count"], 2)
            self.assertTrue(Path(summary["archive"]).is_file())
            with zipfile.ZipFile(summary["archive"]) as archive:
                self.assertNotIn("stale-old-output.png", "\n".join(archive.namelist()))

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["generated"]), 3)
            self.assertEqual({item["family"] for item in manifest["generated"]}, {"computer"})
            self.assertTrue(all(item["signature"]["status"] == "applied" for item in manifest["generated"]))
            for item in manifest["generated"]:
                with Image.open(item["output"]) as image:
                    self.assertEqual(list(image.size), item["dimensions"])

    def test_directory_processes_both_orientation_masters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "masters"
            source_dir.mkdir()
            Image.new("RGB", (100, 160), (20, 20, 20)).save(source_dir / "portrait.png")
            Image.new("RGB", (160, 100), (30, 10, 10)).save(source_dir / "landscape.png")
            output = root / "pack"

            result = self.run_cli(
                str(source_dir),
                "--output-dir",
                str(output),
                "--no-preview",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["generated_count"], 5)
            self.assertEqual(summary["skipped_count"], 5)
            self.assertTrue(Path(summary["archive"]).is_file())
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["sources"]), 2)
            self.assertIsNone(manifest["files"]["preview"])

    def test_force_mismatched_outputs_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "portrait.png"
            output = root / "pack"
            Image.new("RGB", (100, 160), (20, 20, 20)).save(source)

            result = self.run_cli(
                str(source),
                "--output-dir",
                str(output),
                "--include-mismatched",
                "--signature",
                "clean",
                "--no-zip",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["generated_count"], 5)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(all(item["signature"]["status"] == "not-applied" for item in manifest["generated"]))
            self.assertTrue(any(item["family"] == "computer" for item in manifest["generated"]))

    def test_invalid_focus_is_rejected(self) -> None:
        result = self.run_cli("not-an-image.png", "--focus", "2,0.5")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("between 0 and 1", result.stderr)


if __name__ == "__main__":
    unittest.main()
