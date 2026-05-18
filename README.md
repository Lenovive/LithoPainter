# Lithopainter

Lithopainter is a Windows desktop GUI for converting 2D images into
multi-color STL sets for lithophane-style 3D printing. The UI is written in
Python/PySide6. The STL generator is the bundled Java JAR, `lithopainter.jar`,
which still identifies itself internally as PIXEstL.

## Attribution

Lithopainter bundles and shells out to the MIT-licensed
[PIXEstL](https://github.com/gaugo87/PIXEstL) Java engine by
[gaugo87](https://github.com/gaugo87). The upstream PIXEstL copyright notice is
preserved in [LICENSE](LICENSE), and additional attribution details are listed
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The Python/PySide6 desktop GUI, Bambu `.3mf` exporter, launcher, and local
documentation are Lithopainter-specific additions around that engine.

## Quick Start

Run the app from PowerShell or Command Prompt:

```cmd
python lithopainter_gui.py
```

Or double-click:

```cmd
Lithopainter.bat
```

## Requirements

- Python 3.10+
- PySide6: `pip install PySide6`
- Java JRE or JDK on `PATH`
- Pillow: required for crop, border, input conversion, and image adjustments
- NumPy: required for the live print preview

## Project Files

- `lithopainter_gui.py` - PySide6 desktop app and main entry point.
- `lithopainter.jar` - bundled PIXEstL Java STL generator.
- `bambu_3mf.py` - packages generated STLs into a Bambu Studio-compatible
  `.3mf`.
- `resources/filament-palette-0.10mm.json` - filament palette passed to the
  JAR with `-p`.
- `resources/bambu_template/` - Bambu Studio template files used for `.3mf`
  export.
- `input/` - local source images. Image contents are ignored by git except for
  a placeholder file.
- `output/` - generated ZIPs, extracted STL folders, `.3mf` files, and preview
  artifacts.
- `Lithopainter.bat` - Windows launcher.

## Basic Workflow

1. Select an image.
2. Crop, rotate, or adjust it if needed.
3. Pick a frame size or enter exact dimensions.
4. Pick a print profile and quality.
5. Enable the filaments you want.
6. Use `Preflight` to inspect the planned JAR command, active measured
   filaments, ignored hex-only filaments, estimated grids, white status, and
   expected Bambu slot mapping.
7. Generate the STL ZIP.
8. Open the extracted folder or generated `.3mf`.

## Print Profiles

Lithopainter includes profiles that map directly to common PIXEstL workflows:

- `Litho detail` - Lithopainter's detailed default profile.
- `JAR 0.2` - bundled JAR defaults for a 0.2 mm nozzle:
  `-b 0.10`, `-f 0.20`, `-m 0.30`, `-M 1.80`.
- `0.4 nozzle` - PIXEstL's 0.4 mm nozzle guidance:
  `-b 0.12`, `-f 0.24`.
- `Tex only` - texture-only lithophane output using `-z false`.
- `Pixel FULL` - pixel-art output using `-F FULL -Z false`.
- `1 AMS 7 col` - PIXEstL's 7-color / 1-AMS workflow using `-c 4 -l 4`.

The `JAR 0.2` profile follows the bundled JAR usage output. Upstream PIXEstL
documentation may describe older defaults, so Lithopainter treats the bundled
JAR as the local source of truth.

## Advanced Engine Options

The advanced print settings expose PIXEstL options directly:

- `-c` maximum colors per layer
- `-d` color distance method: `CIELab` or `RGB`
- `-C` curve parameter
- `-Y` low-memory mode
- `-n` layer thread limit
- `-N` row thread limit
- `-t` layer thread timeout
- `-T` row thread timeout
- `-z` color layer generation
- `-Z` texture layer generation

Use `Engine help` in the app to run the bundled JAR's help probe and inspect
the exact supported options and defaults.

## Direct JAR Invocation

The GUI shells out to the bundled generator. A minimal direct command is:

```cmd
java -jar lithopainter.jar -p resources\filament-palette-0.10mm.json -w 130 -H 180 -i input\your_image.jpg -o output\your_image.zip
```

The JAR does not implement a formal `--help` flag. Invoking it with `--help`
prints usage and exits non-zero with an "Unrecognized option" message.

## Output

Generation creates a ZIP containing files such as:

- `image-color-preview.png`
- `image-texture-preview.png`
- `layer-<filament>.stl`
- `layer-plate.stl`
- `layer-texture-White[PLA Basic].stl`
- `instructions.txt`

Lithopainter extracts the ZIP into `output/<name>/` and attempts to create a
Bambu Studio-compatible `.3mf` in the same folder.

For PIXEstL's 1-AMS multi-color workflow, Lithopainter reads generated
`instructions.txt` swap lines such as `Cyan-->Matte Ice Blue` and maps the
target filament STL to the source filament's AMS slot in the generated `.3mf`.

## Palette Notes

PIXEstL color lithophanes rely on measured per-layer filament colors. Palette
entries with a `layers` object can participate in ADDITIVE color lithophanes.
Hex-only entries are useful for pixel-art workflows but are ignored by
ADDITIVE color lithophane generation.

The white filament entry `#FFFFFF` should remain active for ADDITIVE color
lithophanes.

## License

This repository is distributed under the MIT License. See [LICENSE](LICENSE).
