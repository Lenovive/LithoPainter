import os
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import bambu_3mf

from PySide6.QtWidgets import QApplication

from lithopainter_gui import (
    LithoWindow,
    PRESETS,
    SCRIPT_DIR,
    SINGLE_COLOR_LAYER_HEIGHT,
    SINGLE_COLOR_TEXTURE_MAX_LAYERS,
    _append_frame_stl_to_zip,
    _ascii_stl_bounds,
)


def _write_test_bmp(path: Path, width: int = 12, height: int = 12) -> None:
    row_stride = ((width * 3 + 3) // 4) * 4
    pixel_data = bytearray()
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            r = int(255 * x / max(1, width - 1))
            g = int(255 * y / max(1, height - 1))
            b = int(255 * (x + y) / max(1, width + height - 2))
            row.extend((b, g, r))
        row.extend(b"\0" * (row_stride - width * 3))
        pixel_data.extend(row)

    file_size = 54 + len(pixel_data)
    header = bytearray()
    header.extend(b"BM")
    header.extend(struct.pack("<IHHI", file_size, 0, 0, 54))
    header.extend(struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                              len(pixel_data), 2835, 2835, 0, 0))
    path.write_bytes(header + pixel_data)


class GenerationModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.repo = Path(SCRIPT_DIR)
        cls.output_dir = cls.repo / "output"
        cls.output_dir.mkdir(exist_ok=True)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="selftest-", dir=self.output_dir)
        self.tmp_path = Path(self.tmp.name)
        self.image_path = self.tmp_path / "source.bmp"
        _write_test_bmp(self.image_path)
        self.win = LithoWindow()
        self.win._load_palette()
        self._configure_small_generation(self.win)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _configure_small_generation(win: LithoWindow) -> None:
        win._width_mm = "10"
        win._height_mm = "10"
        win._color_px_w = "1.0"
        win._tex_px_w = "1.0"
        win._layer_thick = "0.10"
        win._layer_count = "5"
        win._backing_layers = "2"
        win._texture_min_layers = "3"
        win._texture_max_layers = "5"
        win._border_mm = "0"
        win._pixel_mode = "ADDITIVE"
        win._distance_method = "CIELab"

    def _run_jar(self, out_zip: Path, palette_path: str | None = None) -> list[str]:
        color, texture = self.win._output_flags()
        cmd = self.win._build_jar_cmd(
            str(self.image_path),
            str(out_zip),
            color=color,
            texture=texture,
            palette_path=palette_path,
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            cmd,
            cwd=SCRIPT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=flags,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(out_zip.exists(), proc.stdout)
        with zipfile.ZipFile(out_zip) as zf:
            return sorted(zf.namelist())

    @staticmethod
    def _command_value(cmd: list[str], flag: str) -> str:
        return cmd[cmd.index(flag) + 1]

    def test_frame_presets_feed_expected_dimensions_to_generation(self) -> None:
        for orientation in ("portrait", "landscape"):
            for key, _label, _dims, preset_w, preset_h in PRESETS:
                with self.subTest(orientation=orientation, preset=key):
                    self.win._crop_orientation = orientation
                    self.win._apply_preset(key)
                    expected_w, expected_h = preset_w, preset_h
                    if orientation == "landscape" and expected_w < expected_h:
                        expected_w, expected_h = expected_h, expected_w
                    elif orientation == "portrait" and expected_w > expected_h:
                        expected_w, expected_h = expected_h, expected_w

                    self.assertEqual(self.win._width_mm, str(expected_w))
                    self.assertEqual(self.win._height_mm, str(expected_h))

                    color, texture = self.win._output_flags()
                    cmd = self.win._build_jar_cmd(
                        str(self.image_path),
                        str(self.tmp_path / f"{key}-{orientation}.zip"),
                        color=color,
                        texture=texture,
                    )
                    self.assertEqual(self._command_value(cmd, "-w"), str(expected_w))
                    self.assertEqual(self._command_value(cmd, "-H"), str(expected_h))

    def test_color_mode_generates_color_stack_and_texture(self) -> None:
        self.win._set_litho_mode("color")
        self.assertEqual(self.win._output_flags(), (True, True))

        entries = self._run_jar(self.tmp_path / "color.zip")

        self.assertIn("image-color-preview.png", entries)
        self.assertIn("image-texture-preview.png", entries)
        self.assertIn("instructions.txt", entries)
        self.assertTrue(any(name == "layer-plate.stl" for name in entries))
        self.assertTrue(any(
            name.startswith("layer-")
            and name.endswith(".stl")
            and "texture" not in name.lower()
            and "plate" not in name.lower()
            for name in entries
        ))
        self.assertTrue(any("texture" in name.lower() for name in entries))

    def test_single_mode_locks_one_filament_and_generates_texture_only(self) -> None:
        self.win._set_litho_mode("single")
        self.win._on_filament_toggled("#C00D1E", True)

        self.assertEqual(self.win._output_flags(), (False, True))
        self.assertEqual(self.win._layer_thick, SINGLE_COLOR_LAYER_HEIGHT)
        self.assertEqual(
            self.win._texture_max_layers,
            SINGLE_COLOR_TEXTURE_MAX_LAYERS,
        )
        self.assertEqual(sum(self.win.color_vars.values()), 1)
        self.assertTrue(self.win.color_vars["#C00D1E"])
        self.assertFalse(self.win._all_on_btn.isEnabled())
        self.assertFalse(self.win._hex_only_btn.isEnabled())
        self.assertFalse(self.win.palette_data["#C00D1E"].get("active", True))
        self.assertTrue(self.win.palette_data["#FFFFFF"].get("active", False))

        tmp_paths: list[str] = []
        try:
            palette_path = self.win._write_single_color_engine_palette(tmp_paths)
            color, texture = self.win._output_flags()
            cmd = self.win._build_jar_cmd(
                str(self.image_path),
                str(self.tmp_path / "single.zip"),
                color=color,
                texture=texture,
                palette_path=palette_path,
            )
            self.assertEqual(self._command_value(cmd, "-b"), "0.10")
            self.assertEqual(self._command_value(cmd, "-M"), "3.200")
            self.assertEqual(cmd[-4:], ["-z", "false", "-Z", "true"])
            entries = self._run_jar(self.tmp_path / "single.zip", palette_path)
        finally:
            for tmp_path in tmp_paths:
                try:
                    Path(tmp_path).unlink()
                except OSError:
                    pass

        self.assertIn("image-texture-preview.png", entries)
        self.assertNotIn("image-color-preview.png", entries)
        self.assertNotIn("instructions.txt", entries)
        stls = [name for name in entries if name.lower().endswith(".stl")]
        self.assertEqual(stls, ["layer-texture-White[PLA Basic].stl"])

    def test_frame_stl_can_be_added_as_separate_output(self) -> None:
        self.win._set_litho_mode("single")
        self.win._on_filament_toggled("#C00D1E", True)

        tmp_paths: list[str] = []
        zip_path = self.tmp_path / "single-with-frame.zip"
        try:
            palette_path = self.win._write_single_color_engine_palette(tmp_paths)
            self._run_jar(zip_path, palette_path)
            frame_name = _append_frame_stl_to_zip(str(zip_path), 1.0, 3.2)
        finally:
            for tmp_path in tmp_paths:
                try:
                    Path(tmp_path).unlink()
                except OSError:
                    pass

        self.assertEqual(frame_name, "layer-frame.stl")
        with zipfile.ZipFile(zip_path) as zf:
            entries = sorted(zf.namelist())
            self.assertIn("layer-frame.stl", entries)
            texture_name = next(
                name for name in entries
                if name.lower().endswith(".stl") and "texture" in name.lower()
            )
            texture_bounds = _ascii_stl_bounds(zf.read(texture_name))
            frame_bounds = _ascii_stl_bounds(zf.read("layer-frame.stl"))

        self.assertIsNotNone(texture_bounds)
        self.assertIsNotNone(frame_bounds)
        self.assertEqual(frame_bounds[:4], texture_bounds[:4])
        self.assertAlmostEqual(frame_bounds[4], texture_bounds[4])
        self.assertAlmostEqual(frame_bounds[5], texture_bounds[4] + 3.2)

    def test_frame_stl_classifies_as_margin_for_3mf_export(self) -> None:
        parts = bambu_3mf.classify_jar_stls([str(self.tmp_path / "layer-frame.stl")])
        self.assertEqual(parts[0]["kind"], "margin")
        self.assertEqual(parts[0]["extruder"], 1)


if __name__ == "__main__":
    unittest.main()
