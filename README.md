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

## Get Started

### 1. Install the prerequisites (once per machine)

`Lithopainter.bat` will detect these and tell you which is missing.

- **Python 3.10+** — https://www.python.org/downloads/
  During install, tick **Add python.exe to PATH**.
- **Java 17+ runtime** — https://adoptium.net/
  Needed by the bundled STL generator (`lithopainter.jar`).

### 2. Download Lithopainter

Either clone the repo with git:

```cmd
git clone https://github.com/Lenovive/LithoPainter.git
cd LithoPainter
```

Or, if you don't use git, open
[github.com/Lenovive/LithoPainter](https://github.com/Lenovive/LithoPainter),
click the green **Code** button, choose **Download ZIP**, and extract the
folder somewhere you can find it.

### 3. Launch the app

Double-click `Lithopainter.bat`. On first run it will:

1. Verify Python and Java are installed.
2. Create a local virtual environment in `.venv/`.
3. Install the Python dependencies from `requirements.txt` (PySide6,
   Pillow, NumPy).
4. Launch the GUI.

Later runs skip steps 2 and 3 and open the GUI immediately.

### Manual launch (alternative)

If you'd rather skip the launcher, from PowerShell or Command Prompt in
the project folder:

```cmd
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python lithopainter_gui.py
```

### Refreshing dependencies

If `requirements.txt` changes after a `git pull`, delete the `.venv`
folder and re-run `Lithopainter.bat` to rebuild it from scratch.

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
- `Lithopainter.bat` - Windows launcher with first-run dependency setup.
- `requirements.txt` - Python packages installed by the launcher into `.venv/`.

## Basic Workflow

1. Select an image.
2. Crop, rotate, or adjust it if needed.
3. Pick a frame size or enter exact dimensions.
4. Pick a quality preset.
5. Enable the filaments you want.
6. Generate the STL ZIP.
7. Open the extracted folder.

## Frame Sizes, Profile, and Quality

The left pane offers three frame-size presets, a single bundled print profile,
a color/single-color litho type selector, and three quality presets:

- Frame sizes: `Bambu Frame` (108 × 144 mm), `Mini` (54 × 72 mm),
  `Ultra Mini` (27 × 36 mm). Exact dimensions can also be entered directly.
- Print profile: `High Quality Lithophane` (ADDITIVE color mode, 0.10 mm layer
  height, 5 color layers, 2 backing layers, 3–15 texture layers, CIELab color
  distance).
- Litho type: `Color` generates the color stack plus texture. `Single` locks
  the filament picker to one selected print color, exports texture only, and
  sets texture depth to 32 layers at 0.10 mm for a 3.20 mm pane.
- Quality presets: `Draft` (0.30 mm pixel grid), `Balanced` (0.20 mm),
  `Fine` (0.12 mm). These drive both the color and texture pixel widths and
  set a grid-cell cap to keep generation tractable.

For workflows that need values outside these presets, override the engine
options directly through the advanced print settings — see below.

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

Single-color litho mode is implemented by calling the bundled engine with
`-z false -Z true`. There is no separate single-color PIXEstL flag; disabling
color layers while leaving texture enabled makes the JAR emit the printable
one-filament texture STL. The GUI sets single-color mode to 32 texture layers
at 0.10 mm, yielding a 3.20 mm final pane. PIXEstL still requires active
`#FFFFFF` and at least one measured non-white support color during palette
setup, so the GUI uses a temporary engine-safe palette while keeping the user's
one selected print filament in the UI and generated notes.

Use `Engine help` in the app to run the bundled JAR's help probe and inspect
the exact supported options and defaults.

## Direct JAR Invocation

The GUI shells out to the bundled generator. A minimal direct command is:

```cmd
java -jar lithopainter.jar -p resources\filament-palette-0.10mm.json -w 130 -H 180 -i input\your_image.jpg -o output\your_image.zip
```

The JAR does not implement a formal `--help` flag. Invoking it with `--help`
prints usage and exits non-zero with an "Unrecognized option" message.

## Self Tests

Run the generation-mode smoke tests from the repo root:

```cmd
python -m unittest discover -s tests
```

The tests create a tiny temporary BMP in `output/`, run the bundled JAR through
the same command builder used by the GUI, and verify frame presets plus both
ZIP shapes:

- Frame presets feed the expected portrait and landscape dimensions into the
  generated JAR command.
- Color mode emits color preview, texture preview, plate STL, color STLs,
  instructions, and texture STL.
- Single mode locks the UI to one selected filament, sets `-M 3.200`, and
  emits only the texture preview plus one texture STL.

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
