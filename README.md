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
- When a border is enabled with texture output, the raised frame is appended as
  its own `layer-frame.stl` instead of being baked into the texture STL.
- Single mode locks the UI to one selected filament, sets `-M 3.200`, and
  emits only the texture preview plus one texture STL.

## Output

Generation creates a ZIP containing files such as:

- `image-color-preview.png`
- `image-texture-preview.png`
- `layer-<filament>.stl`
- `layer-plate.stl`
- `layer-texture-White[PLA Basic].stl`
- `layer-frame.stl` (when border + texture output are enabled)
- `instructions.txt`

Lithopainter extracts the ZIP into `output/<name>/` and attempts to create a
Bambu Studio-compatible `.3mf` in the same folder.

For PIXEstL's 1-AMS multi-color workflow, Lithopainter reads generated
`instructions.txt` swap lines such as `Cyan-->Matte Ice Blue` and maps the
target filament STL to the source filament's AMS slot in the generated `.3mf`.

## Palette Reference

The bundled palette lives in `resources/filament-palette-0.10mm.json`. Each
entry is keyed by hex color and describes one physical filament spool.

### Entry format

```json
"#0086D6": {
  "name": "Cyan[PLA Basic]",
  "active": true,
  "layers": {
    "5": { "H": 203, "S": 99, "L": 45.3 },
    "4": { "H": 200, "S": 95, "L": 47.6 },
    "3": { "H": 199, "S": 91, "L": 53.9 },
    "2": { "H": 199, "S": 100, "L": 64.3 },
    "1": { "H": 201, "S": 96, "L": 78.2 }
  }
}
```

| Field | Required | Meaning |
|-------|----------|---------|
| `name` | yes | Display name, conventionally `"Label[FilamentType]"` |
| `active` | yes | Whether the filament is enabled in the palette on load |
| `layers` | for ADDITIVE | Per-stack-depth HSL measurements (see below) |

### Measured vs. hex-only entries

Entries **with** a `layers` object participate in ADDITIVE color lithophane
generation. The engine uses the measured transmittance data to decide how many
layers of each filament to stack for each pixel.

Entries **without** a `layers` object are hex-only. They appear in the palette
UI and can be used as the single print color in Single-color litho mode, but
are ignored by ADDITIVE color generation.

### What the layer data means

Each key in `layers` is a layer count (as a string: `"1"` through `"5"` for
most filaments). The value is the HSL color you see when that many layers of
the filament are printed over a white backer and viewed with a backlight:

- **H** — hue, 0–360 (integer; the JAR truncates decimals)
- **S** — saturation, 0–100 (integer; the JAR truncates decimals)
- **L** — lightness, 0–100 (float; higher = more light passes through)

Layer 1 is the thinnest stack (most light, highest L). Layer 5 is the densest
(least light, lowest L). The engine converts these to CMYK via the same
`hslToCmyk` routine as the JAR and combines stacks additively per pixel.

White (`#FFFFFF`) must remain active for ADDITIVE mode. Its entries span
layers 1–10 because white is used as a base reference across all stack depths.

### Filament groups

The name suffix in brackets is cosmetic grouping only — the engine treats all
measured entries identically regardless of filament type.

**Measured (ADDITIVE-capable) — 16 entries**

| Hex | Name | Active by default | Layer range |
|-----|------|-------------------|-------------|
| `#FFFFFF` | White[PLA Basic] | yes | 1–10 |
| `#0086D6` | Cyan[PLA Basic] | yes | 1–5 |
| `#EC008C` | Magenta[PLA Basic] | yes | 1–5 |
| `#FCE300` | Yellow[PLA Basic] | yes | 1–5 |
| `#000000` | Black[PLA Basic] | no | 4–5 |
| `#A6A9AA` | Silver[PLA Basic] | no | 1–5 |
| `#E7CEB5` | Beige[PLA Basic] | no | 1–5 |
| `#6E3FA3` | Purple[PLA Basic] | no | 1–5 |
| `#FFE34F` | Pale yellow[OVERTURE] | no | 1–5 |
| `#8BD5EE` | Matte Ice Blue[PLA Matte] | no | 1–5 |
| `#E4BDD0` | Matte Sakura Pink[PLA Matte] | no | 1–5 |
| `#D3B7A7` | Matte Latte Brown[PLA Matte] | no | 1–5 |
| `#61C680` | Matte Grass Green[PLA Matte] | no | 1–5 |
| `#BB3D43` | Matte Dark Red[PLA Matte] | no | 1–5 |
| `#F99963` | Matte Mandarin Orange[PLA Matte] | no | 1–5 |
| `#EEE7D4` | Bone White[Custom] | no | 1–5 |

**Hex-only — 30 entries**

PLA Basic: Gold, Bamboo Green, Blue, Red, Green, Orange, Grey, Blue Grey,
Pink, Brown.  
PLA Matte: Matte Lilac Violet, Matte Marine Blue, Matte Scarlet Red,
Matte Lemon Yellow, Matte Ash Grey, Matte Dark Green, Matte Dark Blue,
Matte Dark Brown.  
PLA Silk: Gold, Silver, Copper, Blue.  
PLA Metal: Iridium Gold Metallic, Cobalt Blue Metallic, Oxide Green Metallic,
Copper Brown Metallic, Iron Grey Metallic.  
PLA Sparkle: Alpine Green Sparkle, Crimson Red Sparkle, Onyx Black Sparkle.  
PLA Tough: Lavender Blue, Pine Green, Black, Grey.

### Adding a new filament

**Hex-only** — add an entry with no `layers` object. It will appear in the
palette UI and can be used in Single-color mode:

```json
"#1A2B3C": {
  "name": "Navy Blue[PLA Basic]",
  "active": false
}
```

**ADDITIVE-capable** — you also need to measure the filament's transmittance
at each stack depth:

1. Print five test tiles at 1, 2, 3, 4, and 5 layers thick on a white backer
   (use the same 0.10 mm layer height as the palette filename indicates).
2. Backlight each tile and photograph or measure it in your color tool of
   choice. Record the HSL value you observe.
3. Add an entry using the measured H (integer), S (integer), and L (float)
   values for each depth:

```json
"#1A2B3C": {
  "name": "Navy Blue[PLA Basic]",
  "active": false,
  "layers": {
    "5": { "H": 220, "S": 80, "L": 25.0 },
    "4": { "H": 218, "S": 75, "L": 32.0 },
    "3": { "H": 215, "S": 70, "L": 42.0 },
    "2": { "H": 212, "S": 65, "L": 55.0 },
    "1": { "H": 210, "S": 55, "L": 70.0 }
  }
}
```

The palette file is re-read each time the app starts, so changes take effect
without rebuilding anything.

## License

This repository is distributed under the MIT License. See [LICENSE](LICENSE).
