# Lithopainter

GUI front end for converting 2D images into multi-color 3D STL models for
lithophane-style 3D printing. The desktop UI is Python/PySide6; the conversion
engine is the bundled Java JAR, which still identifies itself internally as
PIXEstL.

## Architecture

- `lithopainter_gui.py` - PySide6 desktop app and main entry point.
- `lithopainter.jar` - Java image-to-STL converter. The GUI shells out to
  `java -jar lithopainter.jar ...`.
- `bambu_3mf.py` - Packages extracted STL output into a Bambu Studio-compatible
  `.3mf` project and embeds height-range modifier metadata where possible.
- `resources/filament-palette-0.10mm.json` - Filament color palette passed to
  the JAR with `-p`.
- `resources/bambu_template/` - Bambu Studio template files used by the `.3mf`
  exporter.
- `input/` - Sample/source images.
- `output/` - Default destination for generated ZIPs, extracted STL folders,
  generated `.3mf` files, and preview artifacts.
- `Lithopainter.bat` - Windows launcher. It starts `pythonw lithopainter_gui.py`
  and falls back to `python lithopainter_gui.py`.

## Running

```cmd
python lithopainter_gui.py
```

Or double-click `Lithopainter.bat`.

Direct JAR invocation:

```cmd
java -jar lithopainter.jar -p resources/filament-palette-0.10mm.json -w 130 -H 180 -i input\your_image.jpg -o output\your_image.zip
```

The JAR prints usage when invoked with an unknown option such as `--help`.
Expect a non-zero exit because it does not implement a formal help flag.

## Requirements

- Python 3.10+ (`lithopainter_gui.py` uses modern type-hint syntax).
- PySide6: `pip install PySide6`.
- Java JRE or JDK on `PATH`.
- Pillow: optional for basic launch, required for crop, border, and input format
  conversion during generation.
- NumPy: optional, used with Pillow for the live print/optical preview.

## Known Stale References

- `README.md` still describes the upstream project as "PIXEstL" and references
  `pixestl_gui.py`, `PIXEstL.jar`, and `run.bat`. The actual local files are
  `lithopainter_gui.py`, `lithopainter.jar`, and `Lithopainter.bat`.
- `.claude/settings.local.json` contains historical Claude permission entries
  for PIXEstL-era commands. Treat it as local permission history, not current
  project documentation.

## Notable Code Landmarks

- `THEMES` / `_apply_theme` (`lithopainter_gui.py:50`,
  `lithopainter_gui.py:105`) - light/dark theme dictionaries and QSS refresh.
- `PreviewCanvas` (`lithopainter_gui.py:934`) - image preview, crop overlay, and
  border preview.
- `FilamentRow` / `ColorEditorDialog` (`lithopainter_gui.py:1406`,
  `lithopainter_gui.py:1555`) - palette row widgets and color editing dialog.
- `LithoWindow` (`lithopainter_gui.py:2099`) - main window; orchestrates image
  selection, settings, JAR subprocess execution, ZIP extraction, `.3mf` export,
  and output folder access.
- `_generate_stl` (`lithopainter_gui.py:4581`) - validates inputs, prepares
  cropped/converted images when needed, builds JAR commands, and writes ZIP
  output.
- `_build_bambu_3mf` (`lithopainter_gui.py:4843`) - converts generated STL
  output into a Bambu `.3mf` project using `bambu_3mf.py`.
