# Releasing Lithopainter

Step-by-step guide for cutting a new Windows installer release.

## Prerequisites (one-time setup)

On the machine you build releases from:

- **Python 3.10–3.13** on PATH, plus a project venv at `.\.venv`
  (created by running `Lithopainter.bat` once).
- **Java 17+** on PATH (needed for the smoke test, not the build itself).
- **Inno Setup 6+** — https://jrsoftware.org/isdl.php
  Default install location is auto-discovered; alternatively put `iscc.exe`
  on PATH.
- **GitHub CLI** — https://cli.github.com — authenticated with `gh auth login`
  (needs `repo` scope for release uploads).
- A clean working tree on `main` with the changes you want to ship merged in.

## Release checklist

### 1. Bump the version

Edit `build/installer.iss`:

```ini
#define MyAppVersion  "1.1.0"   ; ← new version
```

Use semver: `MAJOR.MINOR.PATCH`. Bump MAJOR for breaking workflow changes
(file-format breakage, removed features), MINOR for new features, PATCH for
bug fixes.

Commit the bump on its own:

```powershell
git commit -am "Bump version to 1.1.0"
git push
```

### 2. Build the installer

From the project root:

```powershell
.\build_exe.ps1
```

This:

1. Installs/refreshes PyInstaller in `.\.venv`.
2. Cleans previous `dist/` and `build/work/`.
3. Runs PyInstaller against `build/lithopainter.spec` → `dist/Lithopainter/`.
4. Downloads the latest Adoptium Temurin 21 JRE (Windows x64).
5. Stages the JRE as `dist/Lithopainter/jre/`.
6. Compiles `build/installer.iss` → `installer-out/LithopainterSetup.exe`.

Build time: ~2–5 min (mostly PyInstaller + JRE download).
Output size: ~75–80 MB.

> Note: the JRE is re-downloaded every build. If you're iterating, you can
> skip the download by temporarily commenting out the JRE block in
> `build_exe.ps1` after the first successful build of the day.

### 3. Smoke-test the installer

On the build machine (or a clean Windows VM with no Python/Java installed):

1. Double-click `installer-out\LithopainterSetup.exe`.
2. Confirm: **no UAC prompt**, install completes, Start Menu entry appears,
   app launches automatically at the end.
3. In the app, open any image (e.g. one from `input/`), pick a frame preset,
   hit **Generate**.
4. Confirm an `output/<name>/` folder appears under the install dir
   (default: `%LOCALAPPDATA%\Programs\Lithopainter\`) containing the STLs,
   `.3mf`, and previews. The "Open output folder" button should open it.
5. Click **Engine help** in the app — if Java help text appears, the bundled
   JRE is working (no system Java needed).
6. Uninstall via Start Menu → "Uninstall Lithopainter" and confirm it's
   removed.

If any step fails, fix it before tagging.

### 4. Tag and push

```powershell
git tag v1.1.0
git push origin v1.1.0
```

Tag names follow `v{MyAppVersion}` from the .iss.

### 5. Publish the GitHub release

```powershell
gh release create v1.1.0 `
    installer-out\LithopainterSetup.exe `
    --title "Lithopainter v1.1.0" `
    --notes-file release-notes.md `
    --latest
```

Notes-file format (create `release-notes.md` next to the EXE; it's
ignored by git):

```markdown
## Changes

- New: <feature>
- Fix: <bug>
- Internal: <refactor>

## Install

Download **LithopainterSetup.exe** below and double-click. No Python or
Java install required — everything is bundled.
```

For a quick release without notes, you can use `--generate-notes` to let
GitHub auto-fill from commit messages instead of `--notes-file`.

### 6. Verify the release page

Visit https://github.com/Lenovive/LithoPainter/releases/latest and confirm:

- Title and version match.
- `LithopainterSetup.exe` is attached and downloadable.
- The release is marked **Latest**.

The README's "Download the latest LithopainterSetup.exe" link points at
`/releases`, so a published "Latest" release is what users see first.

## What gets committed vs. ignored

Tracked in git:

- `lithopainter_gui.py`, `bambu_3mf.py`, `requirements.txt`, etc. — source.
- `build/lithopainter.spec` — PyInstaller config.
- `build/installer.iss` — Inno Setup config (contains the version).
- `build_exe.ps1` — build orchestrator.
- `Lithopainter.bat` — source-run launcher (kept for developers).
- `RELEASING.md`, `README.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`.

Ignored (per `.gitignore`):

- `build/work/`, `build/jre.zip`, `build/jre-extract/` — PyInstaller and JRE
  intermediates.
- `dist/` — PyInstaller `--onedir` output.
- `installer-out/` — final installer .exe.

## Troubleshooting

### PyInstaller fails to import `bambu_3mf`

`bambu_3mf` is explicitly listed in `hiddenimports` in
`build/lithopainter.spec`. If you rename or split it, update the spec.

### "java" not found at runtime in the installed app

The bundled JRE should be at `<install>\jre\bin\java.exe`. If the install
landed somewhere unexpected, check `_resolve_java()` in
`lithopainter_gui.py` — it falls back to the system PATH `java` if the
bundled binary is missing.

### Windows Defender flags the installer

PyInstaller-built EXEs are a known source of antivirus false-positives,
especially for unsigned binaries. Options, in increasing effort:

1. Submit the binary to Microsoft for analysis at
   https://www.microsoft.com/wdsi/filesubmission so future scans clear it.
2. Buy a code-signing certificate (~$100–500/yr) and add `signtool` step
   to `build_exe.ps1` between PyInstaller and Inno Setup.

### Installer is much larger than 80 MB

The JRE is ~45 MB and PySide6 is ~60 MB. Compression should bring the
final installer to ~75 MB. If it balloons, check that
`excludes=['tkinter', 'unittest', 'pydoc', 'doctest']` is still in the
spec and that no large dev-only modules slipped into `requirements.txt`.

### Resource (JAR, palette, template) not found in the installed app

PyInstaller puts bundled `datas` under `<install>\_internal\` and sets
`sys._MEIPASS` to that dir at runtime. The `_resource_path()` helper in
`lithopainter_gui.py` resolves paths through `_MEIPASS` when frozen.
If you add a new bundled file, list it in both:

- `build/lithopainter.spec` → `datas=[...]`
- The runtime code that reads it → wrap in `_resource_path("subdir", "file.ext")`
