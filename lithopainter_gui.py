#!/usr/bin/env python3
"""Lithopainter GUI — PySide6 redesign matching the Litho design system."""

import colorsys
import copy
import json
import os
import re
import subprocess
import tempfile
import threading
import traceback
import zipfile

import bambu_3mf

try:
    from PySide6.QtCore import (
        Qt, QSize, QRect, QPoint, QTimer, QSettings, Signal, QObject,
        QMetaObject, Q_ARG, QUrl,
    )
except ImportError as _exc:
    import sys
    sys.stderr.write(
        "\nLithopainter: required package PySide6 is not installed "
        f"({_exc.name or _exc}).\n\n"
        "Easiest fix: close this window and double-click Lithopainter.bat —\n"
        "it will create a .venv and install everything for you.\n\n"
        "Manual fix: pip install -r requirements.txt\n\n"
    )
    sys.exit(1)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QFontDatabase, QPixmap,
    QImage, QPainterPath, QCursor, QFontMetrics, QTransform,
    QDoubleValidator, QIntValidator,
)
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QDialog, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QFrame, QFileDialog, QSizePolicy, QSplitter,
    QMessageBox, QTextEdit, QAbstractScrollArea, QGridLayout,
    QStackedWidget, QSlider, QComboBox,
)

try:
    from PIL import Image, ImageEnhance
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JAR_PATH   = os.path.join(SCRIPT_DIR, "lithopainter.jar")

# ── Theme ─────────────────────────────────────────────────────────────────────
THEMES = {
    "light": {
        "bg":       "#F4F2EE",
        "panel":    "#FBFAF7",
        "panel_2":  "#FFFFFF",
        "ink":      "#0A0A0A",
        "ink_2":    "#2A2A28",
        "mid":      "#6B6963",
        "dim":      "#A4A29B",
        "line":     "#E5E2DC",
        "line_2":   "#EFEDE7",
        "hover":    "#F0EEE8",
        "selected": "#ECEAE3",
        "ok":       "#3F6B4A",
        "err":      "#8A4242",
        "warn":     "#8A7B3E",
        "on_ink":   "#F4F2EE",
        "log_bg":   "#0B0B0A",
        "log_fg":   "#E9E6DE",
        "log_dim":  "#8E8B82",
        "log_ok":   "#C9D7BD",
        "log_err":  "#E1B1A8",
    },
    "dark": {
        "bg":       "#111110",
        "panel":    "#181816",
        "panel_2":  "#1E1D1B",
        "ink":      "#EDEBE5",
        "ink_2":    "#D6D3CB",
        "mid":      "#8E8B82",
        "dim":      "#5C5A53",
        "line":     "#2A2926",
        "line_2":   "#221F1C",
        "hover":    "#232220",
        "selected": "#2A2826",
        "ok":       "#8FBD8F",
        "err":      "#D89A9A",
        "warn":     "#C9B36E",
        "on_ink":   "#111110",
        "log_bg":   "#0B0B0A",
        "log_fg":   "#E9E6DE",
        "log_dim":  "#8E8B82",
        "log_ok":   "#C9D7BD",
        "log_err":  "#E1B1A8",
    },
}

_settings   = QSettings("Litho", "Litho")
_theme_name = "dark"
T: dict = THEMES[_theme_name].copy()
_theme_cbs: list = []


def _apply_theme(name: str) -> None:
    global _theme_name
    _theme_name = name
    T.update(THEMES[name])
    _settings.setValue("theme", name)
    app = QApplication.instance()
    if app:
        app.setStyleSheet(_global_qss())
    for cb in _theme_cbs:
        try:
            cb()
        except Exception:
            pass


def _on_theme(fn):
    _theme_cbs.append(fn)
    return fn


def _global_qss() -> str:
    return f"""
QWidget {{
    font-family: 'Inter Tight', 'Inter', 'Segoe UI', Arial;
    font-size: 13px;
    color: {T['ink']};
    background: transparent;
}}
QMainWindow, QDialog {{
    background: {T['bg']};
}}
QScrollBar:vertical {{
    width: 8px;
    background: {T['panel']};
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {T['line']};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {T['dim']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QLineEdit {{
    background: {T['panel_2']};
    border: 1px solid {T['line']};
    border-radius: 6px;
    padding: 0 8px;
    min-height: 22px;
    color: {T['ink']};
    selection-background-color: {T['selected']};
}}
QLineEdit:focus {{
    border-color: {T['ink_2']};
    outline: none;
}}
QTextEdit {{
    background: {T['log_bg']};
    border: none;
    color: {T['log_fg']};
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
    padding: 10px 12px;
}}
QPushButton {{
    background: {T['panel_2']};
    border: 1px solid {T['line']};
    border-radius: 6px;
    padding: 0 8px;
    min-height: 20px;
    color: {T['ink_2']};
    font-size: 11px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {T['hover']};
}}
QPushButton:pressed {{
    background: {T['selected']};
}}
QPushButton:disabled {{
    color: {T['dim']};
}}
"""


# ── Validation helper ─────────────────────────────────────────────────────────
def _wire_validator(inp: QLineEdit, validator) -> None:
    inp.setValidator(validator)
    def _check():
        ok = inp.hasAcceptableInput() or not inp.text().strip()
        inp.setStyleSheet("" if ok else f"border: 1.5px solid {T['err']};")
    inp.textChanged.connect(_check)


# ── Font helpers ──────────────────────────────────────────────────────────────
def _load_fonts() -> None:
    for name in ("Inter Tight", "JetBrains Mono"):
        QFontDatabase.addApplicationFont(name)


def _uf(px: int, w: int = 400) -> QFont:
    f = QFont("Inter Tight")
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(w))
    return f


def _mf(px: int, w: int = 400) -> QFont:
    f = QFont("JetBrains Mono")
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(w))
    return f


# ── Color preview quantization ────────────────────────────────────────────────
def _srgb_decode(rgb01):
    """sRGB encoded [0,1] → linear-light [0,1]."""
    a = 0.055
    return np.where(
        rgb01 <= 0.04045,
        rgb01 / 12.92,
        ((rgb01 + a) / (1 + a)) ** 2.4,
    )


def _linear_to_lab(linear):
    """Linear-light RGB → CIE L*a*b* (D65). Vectorised over leading axes."""
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ], dtype=np.float32)
    xyz = linear @ M.T
    white = np.array([0.95047, 1.00000, 1.08883], dtype=np.float32)
    r = xyz / white
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    f = np.where(r > eps, np.cbrt(np.maximum(r, 0.0)), (kappa * r + 16.0) / 116.0)
    L = 116.0 * f[..., 1] - 16.0
    a_ = 500.0 * (f[..., 0] - f[..., 1])
    b_ = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a_, b_], axis=-1)


def _srgb_to_lab(rgb01):
    """sRGB encoded [0,1] → CIE L*a*b* (D65).

    Done manually because PIL's "LAB" mode wraps a/b past ±127 for saturated
    colours and produces garbage distances.
    """
    return _linear_to_lab(_srgb_decode(rgb01))


# Cap how big a preview we run through the picker; bounds memory per chunk.
# Higher values preserve more live-preview detail at the cost of refresh time.
_PREVIEW_MAX_PIXELS = 4_000_000
# Exhaustive ADDITIVE-mode enumeration bails to monochrome-only candidates
# if it grows past this. Most CMY+W setups stay well below.
_MAX_STACK_CANDIDATES = 5000
# Cap the source grid generated for the live preview before quantization.
_PREVIEW_MAX_GRID_CELLS = _PREVIEW_MAX_PIXELS


_JAR_HUE_ONE_SIXTH = 0.1666666716337204
_JAR_HUE_ONE_THIRD = 0.3333333432674408
_JAR_HUE_TWO_THIRD = 0.6666666865348816


def _hue_to_rgb(p, q, t):
    """JAR's hueToRgb helper — used inside hslToCmyk."""
    if t < 0:
        t += 1
    if t > 1:
        t -= 1
    if t < _JAR_HUE_ONE_SIXTH:
        return p + (q - p) * 6.0 * t
    if t < 0.5:
        return q
    if t < _JAR_HUE_TWO_THIRD:
        return p + (q - p) * (_JAR_HUE_TWO_THIRD - t) * 6.0
    return p


def _hsl_to_cmyk(h, s, l):
    """Verbatim port of PIXEstL's `ColorUtil.hslToCmyk`.

    H ∈ [0, 360), S/L ∈ [0, 100]. Returns (C, M, Y, K) ∈ [0, 1].
    """
    s /= 100.0
    l /= 100.0
    if s == 0:
        return (0.0, 0.0, 0.0, 1.0 - l)
    q = l * (1.0 + s) if l < 0.5 else l + s - l * s
    p = 2.0 * l - q
    hk = h / 360.0
    r = _hue_to_rgb(p, q, hk + _JAR_HUE_ONE_THIRD)
    g = _hue_to_rgb(p, q, hk)
    b = _hue_to_rgb(p, q, hk - _JAR_HUE_ONE_THIRD)
    c = 1.0 - r
    m = 1.0 - g
    y = 1.0 - b
    k = min(c, m, y)
    if k >= 1.0 - 1e-9:
        return (0.0, 0.0, 0.0, k)
    c = (c - k) / (1.0 - k)
    m = (m - k) / (1.0 - k)
    y = (y - k) / (1.0 - k)
    return (c, m, y, k)


def _palette_color_layers(palette_data, active_hexes, max_layers):
    """Build PIXEstL's `ColorLayer` list for ADDITIVE mode: one entry per
    `(filament, layer_count)` pair in the JSON, with CMYK pre-computed.

    Returns `(entries, n_filaments)` where each entry is
    `(filament_idx, layer_count, (C, M, Y, K))`.
    """
    entries = []
    filament_idx = 0
    for hx in active_hexes:
        info = palette_data.get(hx, {}) or {}
        layers = info.get("layers") if isinstance(info, dict) else None
        if isinstance(layers, dict):
            for k, hsl in layers.items():
                try:
                    n = int(k)
                except (TypeError, ValueError):
                    continue
                if n < 1 or n > max_layers:
                    continue
                try:
                    # The JAR calls JSONObject.getInt("H"/"S") and
                    # getDouble("L"). Decimal H/S values are truncated there.
                    h = int(float(hsl["H"]))
                    s = int(float(hsl["S"]))
                    l = float(hsl["L"])
                except (TypeError, KeyError, ValueError):
                    continue
                entries.append((filament_idx, n, _hsl_to_cmyk(h, s, l)))
        # In ADDITIVE mode the JAR ignores active palette entries that do not
        # have measured per-layer data. Do the same here; treating flat hex
        # values as one-layer colors makes the preview optimistic and wrong.
        filament_idx += 1
    return entries, filament_idx


def _apply_source_border(img, border_mm: float, out_w_mm: float,
                         border_rgb: tuple[int, int, int]):
    """Apply the same source-space border transform used before JAR export."""
    if border_mm <= 0 or out_w_mm <= 0:
        return img
    Wpx, Hpx = img.size
    if Wpx <= 0 or Hpx <= 0:
        return img
    px_per_mm = Wpx / out_w_mm
    bw = int(round(border_mm * px_per_mm))
    bh = int(round(border_mm * px_per_mm))
    inner_w = max(1, Wpx - 2 * bw)
    inner_h = max(1, Hpx - 2 * bh)
    if bw <= 0 or bh <= 0 or inner_w <= 1 or inner_h <= 1:
        return img
    inner = img.resize((inner_w, inner_h), Image.LANCZOS)
    canvas = Image.new("RGB", (Wpx, Hpx), border_rgb)
    canvas.paste(inner, (bw, bh))
    return canvas


def _ascii_stl_bounds(stl_data: bytes | str) -> tuple[float, float, float, float, float, float] | None:
    """Return min/max XYZ bounds for an ASCII STL blob."""
    if isinstance(stl_data, bytes):
        text = stl_data.decode("utf-8", errors="replace")
    else:
        text = stl_data
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    found = False
    for line in text.splitlines():
        s = line.lstrip()
        if not s.startswith("vertex"):
            continue
        parts = s.split()
        if len(parts) < 4:
            continue
        try:
            x = float(parts[1])
            y = float(parts[2])
            z = float(parts[3])
        except ValueError:
            continue
        found = True
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        min_z = min(min_z, z)
        max_z = max(max_z, z)
    if not found:
        return None
    return min_x, max_x, min_y, max_y, min_z, max_z


def _fmt_stl_float(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _triangle_normal(a, b, c) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    mag = (nx * nx + ny * ny + nz * nz) ** 0.5
    if mag <= 0:
        return 0.0, 0.0, 0.0
    return nx / mag, ny / mag, nz / mag


def _build_frame_stl(
    bounds: tuple[float, float, float, float, float, float],
    border_mm: float,
    frame_height_mm: float,
    solid_name: str = "layer-frame",
) -> str | None:
    """Build a rectangular raised frame aligned to an existing texture STL."""
    x0, x1, y0, y1, z0, _z1 = bounds
    outer_w = x1 - x0
    outer_h = y1 - y0
    if outer_w <= 0 or outer_h <= 0 or border_mm <= 0 or frame_height_mm <= 0:
        return None
    z1 = z0 + frame_height_mm
    inset = min(border_mm, outer_w / 2.0, outer_h / 2.0)
    if inset <= 0:
        return None

    lines: list[str] = [f"solid {solid_name}"]

    def add_triangle(a, b, c) -> None:
        nx, ny, nz = _triangle_normal(a, b, c)
        lines.append(
            f"  facet normal {_fmt_stl_float(nx)} {_fmt_stl_float(ny)} {_fmt_stl_float(nz)}"
        )
        lines.append("    outer loop")
        for vx, vy, vz in (a, b, c):
            lines.append(
                "      vertex "
                f"{_fmt_stl_float(vx)} {_fmt_stl_float(vy)} {_fmt_stl_float(vz)}"
            )
        lines.append("    endloop")
        lines.append("  endfacet")

    def add_quad(a, b, c, d) -> None:
        add_triangle(a, b, c)
        add_triangle(a, c, d)

    def add_box(bx0: float, bx1: float, by0: float, by1: float) -> None:
        add_quad((bx0, by0, z1), (bx1, by0, z1), (bx1, by1, z1), (bx0, by1, z1))
        add_quad((bx0, by0, z0), (bx0, by1, z0), (bx1, by1, z0), (bx1, by0, z0))
        add_quad((bx0, by0, z0), (bx1, by0, z0), (bx1, by0, z1), (bx0, by0, z1))
        add_quad((bx0, by1, z0), (bx0, by1, z1), (bx1, by1, z1), (bx1, by1, z0))
        add_quad((bx0, by0, z0), (bx0, by0, z1), (bx0, by1, z1), (bx0, by1, z0))
        add_quad((bx1, by0, z0), (bx1, by1, z0), (bx1, by1, z1), (bx1, by0, z1))

    if inset * 2.0 >= outer_w or inset * 2.0 >= outer_h:
        add_box(x0, x1, y0, y1)
    else:
        ix0, ix1 = x0 + inset, x1 - inset
        iy0, iy1 = y0 + inset, y1 - inset

        # Top and bottom ring faces, split into four rectangular bands.
        bands = [
            (x0, x1, y0, iy0),
            (x0, x1, iy1, y1),
            (x0, ix0, iy0, iy1),
            (ix1, x1, iy0, iy1),
        ]
        for bx0, bx1, by0, by1 in bands:
            add_quad((bx0, by0, z1), (bx1, by0, z1), (bx1, by1, z1), (bx0, by1, z1))
            add_quad((bx0, by0, z0), (bx0, by1, z0), (bx1, by1, z0), (bx1, by0, z0))

        # Outer side walls.
        add_quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))
        add_quad((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0))
        add_quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0))
        add_quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))

        # Inner hole walls face into the opening.
        add_quad((ix0, iy0, z0), (ix0, iy0, z1), (ix1, iy0, z1), (ix1, iy0, z0))
        add_quad((ix0, iy1, z0), (ix1, iy1, z0), (ix1, iy1, z1), (ix0, iy1, z1))
        add_quad((ix0, iy0, z0), (ix0, iy1, z0), (ix0, iy1, z1), (ix0, iy0, z1))
        add_quad((ix1, iy0, z0), (ix1, iy0, z1), (ix1, iy1, z1), (ix1, iy1, z0))

    lines.append(f"endsolid {solid_name}")
    return "\n".join(lines) + "\n"


def _unique_zip_name(existing: set[str], desired: str) -> str:
    if desired not in existing:
        return desired
    root, ext = os.path.splitext(desired)
    i = 2
    while f"{root}-{i}{ext}" in existing:
        i += 1
    return f"{root}-{i}{ext}"


def _append_frame_stl_to_zip(
    zip_path: str,
    border_mm: float,
    frame_height_mm: float,
    frame_name: str = "layer-frame.stl",
) -> str | None:
    """Append a separate raised frame STL using the texture STL as alignment."""
    if border_mm <= 0 or frame_height_mm <= 0:
        return None
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        names = set(zf.namelist())
        texture_name = next(
            (
                name for name in zf.namelist()
                if name.lower().endswith(".stl")
                and "texture" in os.path.basename(name).lower()
            ),
            None,
        )
        if texture_name is None:
            return None
        texture_data = zf.read(texture_name)
        bounds = _ascii_stl_bounds(texture_data)
        if bounds is None:
            return None
        out_name = _unique_zip_name(names, frame_name)
        solid_name = os.path.splitext(os.path.basename(out_name))[0]
        frame_stl = _build_frame_stl(bounds, border_mm, frame_height_mm, solid_name)
        if frame_stl is None:
            return None
        zf.writestr(out_name, frame_stl)
        return out_name


def _enumerate_stacks(entries, n_filaments, n_total_layers, max_candidates):
    """Enumerate every valid ColorCombi: each filament contributes at most
    one entry, total layer counts sum to exactly `n_total_layers`. Returns
    `(stacks, overflowed)` where `stacks` is a list of tuples of entry
    indices; bails out at `max_candidates`.
    """
    by_filament = [[] for _ in range(n_filaments)]
    for i, (fi, n, _cmyk) in enumerate(entries):
        by_filament[fi].append((n, i))

    stacks = []
    overflow = [False]

    def recurse(filament_idx, remaining, chosen):
        if overflow[0]:
            return
        if remaining == 0:
            if chosen:
                stacks.append(tuple(chosen))
                if len(stacks) >= max_candidates:
                    overflow[0] = True
            return
        if filament_idx >= n_filaments:
            return
        recurse(filament_idx + 1, remaining, chosen)
        for n, ei in by_filament[filament_idx]:
            if n <= remaining:
                chosen.append(ei)
                recurse(filament_idx + 1, remaining - n, chosen)
                chosen.pop()

    recurse(0, n_total_layers, [])
    return stacks, overflow[0]


def _jar_stack_preview(img, palette_data, active_hexes, n_total_layers,
                       max_pixels: int = _PREVIEW_MAX_PIXELS):
    """Render an ADDITIVE-mode preview matching PIXEstL's `-F ADDITIVE`.

    Per pixel: pick the `ColorCombi` (a multi-filament stack with one entry
    per filament summing to `n_total_layers`) whose rendered colour is
    closest to the target in CIE L*a*b*. Rendered colour is the JAR's exact
    arithmetic: additive CMYK across all layers (each channel clipped at
    1.0), then `R = (1−C)(1−K)·255`, etc.

    Falls back to monochrome-only stacks if the exhaustive enumeration
    blows past `_MAX_STACK_CANDIDATES`.
    """
    if not HAS_NUMPY or not active_hexes or n_total_layers <= 0:
        return img

    entries, n_filaments = _palette_color_layers(
        palette_data, active_hexes, n_total_layers,
    )
    if not entries:
        return img

    stacks, overflowed = _enumerate_stacks(
        entries, n_filaments, n_total_layers, _MAX_STACK_CANDIDATES,
    )
    if overflowed or not stacks:
        stacks = [(i,) for i, (_fi, n, _cmyk) in enumerate(entries)
                  if n == n_total_layers]
        if not stacks:
            stacks = [(i,) for i in range(len(entries))]

    entry_cmyk = np.asarray([cmyk for _fi, _n, cmyk in entries],
                            dtype=np.float32)                   # (E, 4)

    stack_cmyk = np.zeros((len(stacks), 4), dtype=np.float32)
    for si, stack in enumerate(stacks):
        for ei in stack:
            stack_cmyk[si] += entry_cmyk[ei]
    np.minimum(stack_cmyk, 1.0, out=stack_cmyk)

    one_minus_k = 1.0 - stack_cmyk[:, 3:4]
    stack_rgb = np.concatenate([
        (1.0 - stack_cmyk[:, 0:1]) * one_minus_k,
        (1.0 - stack_cmyk[:, 1:2]) * one_minus_k,
        (1.0 - stack_cmyk[:, 2:3]) * one_minus_k,
    ], axis=1)                                                  # (S, 3) in [0,1]
    stack_lab = _srgb_to_lab(stack_rgb)                         # (S, 3)

    src_w, src_h = img.size
    if src_w * src_h > max_pixels:
        scale = (max_pixels / (src_w * src_h)) ** 0.5
        small = img.resize(
            (max(1, int(src_w * scale)), max(1, int(src_h * scale))),
            Image.NEAREST,
        )
    else:
        small = img

    src_rgb = np.asarray(small.convert("RGB"), dtype=np.float32) / 255.0
    target_lab = _srgb_to_lab(src_rgb)                          # (H, W, 3)
    H, W = src_rgb.shape[:2]
    pixels_lab = target_lab.reshape(-1, 3)

    sl2 = (stack_lab * stack_lab).sum(axis=1)
    out_idx = np.empty(pixels_lab.shape[0], dtype=np.int32)
    # Keep the temporary distance matrix bounded as preview resolution grows.
    max_scores_per_chunk = 30_000_000
    CHUNK = max(1024, min(50_000, max_scores_per_chunk // max(1, len(stacks))))
    for start in range(0, pixels_lab.shape[0], CHUNK):
        end = min(start + CHUNK, pixels_lab.shape[0])
        score = sl2[None, :] - 2.0 * (pixels_lab[start:end] @ stack_lab.T)
        out_idx[start:end] = score.argmin(axis=1)

    stack_rgb_u8 = np.clip(stack_rgb * 255.0, 0.0, 255.0).astype(np.uint8)
    out = stack_rgb_u8[out_idx].reshape(H, W, 3)
    out_img = Image.fromarray(out, mode="RGB")
    if out_img.size != img.size:
        out_img = out_img.resize(img.size, Image.NEAREST)
    return out_img


# ── Dividers ──────────────────────────────────────────────────────────────────
def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {T['line_2']}; border: none;")
    _on_theme(lambda: line.setStyleSheet(f"background: {T['line_2']}; border: none;"))
    return line


def _vline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(1)
    line.setStyleSheet(f"background: {T['line']}; border: none;")
    _on_theme(lambda: line.setStyleSheet(f"background: {T['line']}; border: none;"))
    return line


# ── Custom widgets ────────────────────────────────────────────────────────────

class BrandMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = QColor(T["ink"])
        p.setPen(QPen(ink, 1.25))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, 24, 24, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(ink))
        p.drawRect(5, 9, 16, 1)
        p.drawRect(5, 15, 16, 1)
        p.end()


class ThemeToggle(QWidget):
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 28)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg   = QColor(T["panel_2"])
        line = QColor(T["line"])
        ink  = QColor(T["ink"])
        mid  = QColor(T["mid"])

        p.setPen(QPen(line, 1))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(0, 0, 64, 28, 6, 6)

        # active pill
        if _theme_name == "light":
            pill_x = 1
        else:
            pill_x = 33
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(T["selected"])))
        p.drawRoundedRect(pill_x, 1, 30, 26, 5, 5)

        p.setFont(_uf(13))
        p.setPen(QPen(ink if _theme_name == "light" else mid))
        p.drawText(QRect(1, 1, 30, 26), Qt.AlignmentFlag.AlignCenter, "☀")
        p.setPen(QPen(ink if _theme_name == "dark" else mid))
        p.drawText(QRect(33, 1, 30, 26), Qt.AlignmentFlag.AlignCenter, "☾")
        p.end()

    def mousePressEvent(self, _):
        new = "dark" if _theme_name == "light" else "light"
        self.changed.emit(new)


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(34, 20)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool) -> None:
        self._checked = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._checked:
            track = QColor(T["ink"])
        else:
            track = QColor(T["line"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(0, 2, 34, 16, 8, 8)
        thumb_x = 16 if self._checked else 2
        p.setBrush(QBrush(QColor("#FFFFFF") if self._checked else QColor(T["mid"])))
        p.drawEllipse(thumb_x, 3, 14, 14)
        p.end()

    def mousePressEvent(self, _):
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self._checked)


class PresetChip(QWidget):
    selected = Signal(str)

    def __init__(self, key: str, label: str, dims: str, parent=None):
        super().__init__(parent)
        self._key    = key
        self._label  = label
        self._dims   = dims
        self._active = False
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def setActive(self, v: bool):
        self._active = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(T["selected"] if self._active else T["panel_2"])
        border = QColor(T["ink"] if self._active else T["line"])
        p.setPen(QPen(border, 1))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(0, 0, self.width(), 52, 6, 6)
        p.setPen(QPen(QColor(T["ink"])))
        p.setFont(_uf(12, 500))
        p.drawText(QRect(10, 6, self.width() - 20, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)
        p.setFont(_mf(10))
        p.setPen(QPen(QColor(T["mid"])))
        p.drawText(QRect(10, 28, self.width() - 20, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._dims)
        p.end()

    def mousePressEvent(self, _):
        self.selected.emit(self._key)


class LayerChip(QWidget):
    selected = Signal(str)

    def __init__(self, key: str, label: str, hint: str, parent=None,
                 width: int = 44):
        super().__init__(parent)
        self._key    = key
        self._label  = label
        self._hint   = hint
        self._active = False
        self.setFixedSize(width, 30)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def setActive(self, v: bool):
        self._active = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(T["selected"] if self._active else T["panel_2"])
        border = QColor(T["ink"] if self._active else T["line"])
        p.setPen(QPen(border, 1))
        p.setBrush(QBrush(bg))
        w, h = self.width(), self.height()
        p.drawRoundedRect(0, 0, w, h, 4, 4)
        p.setPen(QPen(QColor(T["ink"])))
        p.setFont(_mf(10, 500))
        p.drawText(QRect(0, 2, w, 14), Qt.AlignmentFlag.AlignCenter, self._label)
        p.setFont(_uf(8))
        p.setPen(QPen(QColor(T["mid"])))
        p.drawText(QRect(0, 16, w, 12), Qt.AlignmentFlag.AlignCenter, self._hint)
        p.end()

    def mousePressEvent(self, _):
        self.selected.emit(self._key)


class PanelHead(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self.setFixedHeight(40)
        self._extra: QWidget | None = None
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 0, 16, 0)
        self._layout.setSpacing(8)
        lbl = QLabel(title.upper())
        lbl.setFont(_uf(10, 600))
        lbl.setStyleSheet(f"color: {T['mid']}; background: transparent; letter-spacing: 0.14em;")
        _on_theme(lambda: lbl.setStyleSheet(f"color: {T['mid']}; background: transparent; letter-spacing: 0.14em;"))
        self._layout.addWidget(lbl)
        self._layout.addStretch()

    def add_right(self, w: QWidget):
        self._layout.addWidget(w)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setPen(QPen(QColor(T["line_2"]), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class DrawerTab(QWidget):
    """Vertical drawer-handle tab. Sits between a side pane and the center
    canvas, stays visible when the pane is collapsed, click toggles."""

    clicked = Signal()

    def __init__(self, label: str, side: str, parent=None):
        super().__init__(parent)
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got {side!r}")
        self._label = label
        self._side = side
        self._open = True
        self._hover = False
        self.setFixedWidth(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setToolTip(f"Show or hide the {label.lower()} pane")
        _on_theme(lambda: self.update())

    def set_open(self, is_open: bool) -> None:
        if self._open == is_open:
            return
        self._open = is_open
        self.update()

    def is_open(self) -> bool:
        return self._open

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._open:
            bg = QColor(T["selected"])
            fg = QColor(T["ink"])
        elif self._hover:
            bg = QColor(T["hover"])
            fg = QColor(T["ink_2"])
        else:
            bg = QColor(T["panel_2"])
            fg = QColor(T["mid"])

        p.fillRect(self.rect(), bg)
        p.setPen(QPen(QColor(T["line"]), 1))
        if self._side == "left":
            p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        else:
            p.drawLine(0, 0, 0, self.height())

        if self._side == "left":
            arrow = "◀" if self._open else "▶"
        else:
            arrow = "▶" if self._open else "◀"

        p.setPen(QPen(fg))
        f = _uf(11, 600)
        p.setFont(f)
        fm = QFontMetrics(f)
        label_text = self._label.upper()
        text_w = fm.horizontalAdvance(label_text)
        arrow_w = fm.horizontalAdvance(arrow)
        gap = 8
        total = text_w + gap + arrow_w

        p.save()
        p.translate(self.width() / 2, self.height() / 2)
        if self._side == "left":
            p.rotate(-90)
        else:
            p.rotate(90)
        x = -total / 2
        baseline = fm.ascent() - (fm.ascent() + fm.descent()) / 2
        p.drawText(QPoint(int(x), int(baseline)), arrow)
        p.drawText(QPoint(int(x + arrow_w + gap), int(baseline)), label_text)
        p.restore()
        p.end()


class SourceCard(QWidget):
    browse_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self._thumb: QPixmap | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        self._thumb_lbl = QLabel()
        self._thumb_lbl.setFixedSize(40, 40)
        self._thumb_lbl.setStyleSheet(
            f"background: {T['line']}; border-radius: 4px;"
        )
        _on_theme(lambda: self._thumb_lbl.setStyleSheet(
            f"background: {T['line']}; border-radius: 4px;"
        ))
        lay.addWidget(self._thumb_lbl)

        right = QVBoxLayout()
        right.setSpacing(4)
        self._name_lbl = QLabel("No image selected")
        self._name_lbl.setFont(_uf(11, 500))
        self._name_lbl.setStyleSheet(f"color: {T['ink']}; background: transparent;")
        _on_theme(lambda: self._name_lbl.setStyleSheet(f"color: {T['ink']}; background: transparent;"))
        right.addWidget(self._name_lbl)

        self._meta_lbl = QLabel("")
        self._meta_lbl.setFont(_mf(10))
        self._meta_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: self._meta_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        right.addWidget(self._meta_lbl)

        browse_btn = QPushButton("Browse image…")
        browse_btn.setFont(_uf(10, 500))
        browse_btn.setFixedHeight(20)
        browse_btn.clicked.connect(self.browse_clicked)
        right.addWidget(browse_btn)
        lay.addLayout(right)

    def set_image(self, path: str, size: tuple):
        name = os.path.basename(path)
        if len(name) > 28:
            name = name[:25] + "…"
        self._name_lbl.setText(name)
        if size:
            self._meta_lbl.setText(f"{size[0]} × {size[1]} px")
        pix = QPixmap(path)
        if not pix.isNull():
            pix = pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
            w, h = pix.width(), pix.height()
            if w > 40 or h > 40:
                x = (w - 40) // 2
                y = (h - 40) // 2
                pix = pix.copy(x, y, 40, 40)
            self._thumb_lbl.setPixmap(pix)


class AdjustmentControl(QFrame):
    valueChanged = Signal(int)

    def __init__(
        self,
        label: str,
        low_label: str,
        mid_label: str,
        high_label: str,
        tooltip: str,
        formatter=None,
        parent=None,
    ):
        super().__init__(parent)
        self._base_tooltip = tooltip
        self._formatter = formatter or self._signed_value
        self._enabled = True
        self.setObjectName("AdjustmentControl")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(62)
        self.setToolTip(tooltip)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 4)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._label = QLabel(label)
        self._label.setFont(_uf(10, 500))
        top.addWidget(self._label)
        top.addStretch()

        self._value_lbl = QLabel(self._formatter(0))
        self._value_lbl.setFont(_mf(10, 500))
        self._value_lbl.setFixedWidth(46)
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._value_lbl)
        lay.addLayout(top)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(-100, 100)
        self._slider.setValue(0)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(10)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.setTickInterval(50)
        self._slider.setToolTip(tooltip)
        self._slider.valueChanged.connect(self._on_slider_value_changed)
        lay.addWidget(self._slider)

        scale = QHBoxLayout()
        scale.setSpacing(0)
        self._low_lbl = QLabel(low_label)
        self._mid_lbl = QLabel(mid_label)
        self._high_lbl = QLabel(high_label)
        for lbl, align in (
            (self._low_lbl, Qt.AlignmentFlag.AlignLeft),
            (self._mid_lbl, Qt.AlignmentFlag.AlignCenter),
            (self._high_lbl, Qt.AlignmentFlag.AlignRight),
        ):
            lbl.setFont(_mf(9))
            lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            scale.addWidget(lbl, 1)
        lay.addLayout(scale)

        self._apply_theme()
        _on_theme(self._apply_theme)

    @staticmethod
    def _signed_value(value: int) -> str:
        return "0" if value == 0 else f"{value:+d}"

    def _on_slider_value_changed(self, value: int) -> None:
        self._update_value(value)
        self.valueChanged.emit(value)

    def _update_value(self, value: int) -> None:
        self._value_lbl.setText(self._formatter(value))
        self._apply_theme()

    def setValue(self, value: int) -> None:
        old = self._slider.blockSignals(True)
        self._slider.setValue(value)
        self._slider.blockSignals(old)
        self._update_value(value)

    def value(self) -> int:
        return self._slider.value()

    def setControlEnabled(self, enabled: bool, disabled_tooltip: str = "") -> None:
        self._enabled = enabled
        self._slider.setEnabled(enabled)
        tip = self._base_tooltip if enabled else disabled_tooltip
        for widget in (self, self._slider, self._label, self._value_lbl):
            widget.setToolTip(tip)
        self._apply_theme()

    def _apply_theme(self) -> None:
        active = self.value() != 0
        border = T["ink_2"] if active and self._enabled else T["line"]
        bg = T["panel_2"] if self._enabled else T["panel"]
        self.setStyleSheet(f"""
            QFrame#AdjustmentControl {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)
        label_color = T["ink"] if self._enabled else T["dim"]
        scale_color = T["mid"] if self._enabled else T["dim"]
        self._label.setStyleSheet(f"color: {label_color}; background: transparent;")
        for lbl in (self._low_lbl, self._mid_lbl, self._high_lbl):
            lbl.setStyleSheet(f"color: {scale_color}; background: transparent;")

        value_bg = T["selected"] if active and self._enabled else T["panel"]
        value_color = T["ink"] if active and self._enabled else scale_color
        self._value_lbl.setStyleSheet(f"""
            background: {value_bg};
            color: {value_color};
            border: 1px solid {T['line']};
            border-radius: 4px;
            padding: 1px 0;
        """)

        handle_border = T["ink"] if self._enabled else T["dim"]
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: {T['line']};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {T['line']};
                border-radius: 3px;
            }}
            QSlider::add-page:horizontal {{
                background: {T['line']};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 16px;
                height: 16px;
                margin: -6px 0;
                background: {T['panel_2']};
                border: 2px solid {handle_border};
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                border-color: {T['ink']};
            }}
            QSlider::handle:horizontal:disabled {{
                background: {T['panel']};
                border-color: {T['dim']};
            }}
        """)


class PreviewCanvas(QWidget):
    image_dropped = Signal(str)
    crop_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._pix: QPixmap | None = None
        self._image_size: tuple | None = None
        self._scale   = 1.0
        self._offset  = (0, 0)
        self._crop    = None   # (x, y, w, h) in original px
        self._drag    = None
        self._dragging = False
        self._hover_handle = None
        self._drop_hover = False
        self._border_frac: tuple | None = None   # (fx, fy) — border as fraction of crop w/h

    def load_image(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            return False
        self._pix = pix
        self._image_size = (pix.width(), pix.height())
        self._crop = None
        self._fit()
        return True

    def set_pixmap(self, pix: QPixmap, keep_crop: bool = False) -> None:
        """Load a pre-processed pixmap (e.g. after rotation / adjustments)."""
        old_crop = self._crop
        self._pix = pix
        self._image_size = (pix.width(), pix.height())
        self._crop = self._clamp_crop(old_crop) if keep_crop and old_crop else None
        self._fit()
        self.update()

    def _fit(self):
        if not self._pix:
            return
        cw, ch = self.width(), self.height()
        iw, ih = self._pix.width(), self._pix.height()
        scale = min(cw / iw, ch / ih)
        self._scale = scale
        pw, ph = int(iw * scale), int(ih * scale)
        self._offset = ((cw - pw) // 2, (ch - ph) // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()
        self.update()

    def set_crop(self, rect):
        self._crop = self._clamp_crop(rect)
        self.update()
        self.crop_changed.emit(self._crop)

    def crop(self):
        return self._crop

    def crop_pixmap(self) -> QPixmap | None:
        if not self._pix or not self._crop:
            return None
        cx, cy, cw, ch = self._crop
        rect = QRect(
            int(round(cx)),
            int(round(cy)),
            max(1, int(round(cw))),
            max(1, int(round(ch))),
        )
        rect = rect.intersected(QRect(0, 0, self._pix.width(), self._pix.height()))
        if rect.isEmpty():
            return None
        return self._pix.copy(rect)

    def _clamp_crop(self, rect):
        if not rect or not self._image_size:
            return rect
        x, y, w, h = rect
        iw, ih = self._image_size
        w = max(1.0, min(float(w), float(iw)))
        h = max(1.0, min(float(h), float(ih)))
        x = max(0.0, min(float(x), float(iw) - w))
        y = max(0.0, min(float(y), float(ih) - h))
        return (x, y, w, h)

    def set_border_preview(self, border_mm: float, out_w_mm: float, out_h_mm: float):
        """Set the border overlay. border_mm <= 0 or invalid dims → no overlay."""
        if border_mm > 0 and out_w_mm > 0 and out_h_mm > 0:
            fx = max(0.0, min(0.5, border_mm / out_w_mm))
            fy = max(0.0, min(0.5, border_mm / out_h_mm))
            self._border_frac = (fx, fy)
        else:
            self._border_frac = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(T["panel_2"])
        p.fillRect(self.rect(), bg)

        if not self._pix or not self._image_size:
            if self._drop_hover:
                p.setPen(QPen(QColor(T["ink_2"]), 2, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(self.rect().adjusted(8, 8, -8, -8), 8, 8)
            p.setFont(_uf(12))
            p.setPen(QPen(QColor(T["ink_2"] if self._drop_hover else T["dim"])))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drop an image or click Browse")
            p.end()
            return

        ox, oy = self._offset
        s = self._scale
        iw, ih = self._image_size
        pw, ph = int(iw * s), int(ih * s)

        scaled = self._pix.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(ox, oy, scaled)

        if not self._crop:
            p.end()
            return

        cx, cy, cw, ch = self._crop
        x1 = int(ox + cx * s)
        y1 = int(oy + cy * s)
        x2 = int(x1 + cw * s)
        y2 = int(y1 + ch * s)

        # Scrim outside crop
        scrim = QColor(0, 0, 0, 130)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(scrim))
        for rx, ry, rw, rh in [
            (ox,  oy,  pw, y1 - oy),
            (ox,  y2,  pw, oy + ph - y2),
            (ox,  y1,  x1 - ox, y2 - y1),
            (x2,  y1,  ox + pw - x2, y2 - y1),
        ]:
            if rw > 0 and rh > 0:
                p.drawRect(rx, ry, rw, rh)

        # White border
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(x1, y1, x2 - x1, y2 - y1)

        # White border preview (matches generated lithophane border)
        if self._border_frac:
            fx, fy = self._border_frac
            bw_px = int(round((x2 - x1) * fx))
            bh_px = int(round((y2 - y1) * fy))
            if bw_px > 0 and bh_px > 0 and (x2 - x1) > 2 * bw_px and (y2 - y1) > 2 * bh_px:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 255, 255, 235)))
                p.drawRect(x1, y1, x2 - x1, bh_px)                   # top
                p.drawRect(x1, y2 - bh_px, x2 - x1, bh_px)           # bottom
                p.drawRect(x1, y1 + bh_px, bw_px, y2 - y1 - 2 * bh_px)        # left
                p.drawRect(x2 - bw_px, y1 + bh_px, bw_px, y2 - y1 - 2 * bh_px) # right
                p.setPen(QPen(QColor(0, 0, 0, 160), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(x1 + bw_px, y1 + bh_px,
                           x2 - x1 - 2 * bw_px, y2 - y1 - 2 * bh_px)

        # Thirds guides
        p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine))
        for i in (1, 2):
            gx = x1 + (x2 - x1) * i // 3
            gy = y1 + (y2 - y1) * i // 3
            p.drawLine(gx, y1, gx, y2)
            p.drawLine(x1, gy, x2, gy)

        # Corner handles
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        hs = 6
        for hx, hy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            p.drawLine(hx - hs, hy, hx + hs, hy)
            p.drawLine(hx, hy - hs, hx, hy + hs)

        # Drop-hover overlay
        if self._drop_hover:
            p.setPen(QPen(QColor(T["ink_2"]), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(4, 4, -4, -4), 6, 6)

        # Dimension tag
        if cw > 0 and ch > 0:
            tag = f"{int(round(cw))} × {int(round(ch))}"
            p.setFont(_mf(10))
            fm = QFontMetrics(p.font())
            tw = fm.horizontalAdvance(tag) + 12
            th = 20
            tx = x1 + (x2 - x1 - tw) // 2
            ty = y1 - th - 4
            if ty < oy:
                ty = y1 + 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(0, 0, 0, 170)))
            p.drawRoundedRect(tx, ty, tw, th, 4, 4)
            p.setPen(QPen(QColor("#FFFFFF")))
            p.drawText(QRect(tx, ty, tw, th), Qt.AlignmentFlag.AlignCenter, tag)

        p.end()

    def _img_pos(self, ev_x, ev_y):
        ox, oy = self._offset
        s = self._scale
        return (ev_x - ox) / s, (ev_y - oy) / s

    def _crop_screen_rect(self) -> tuple[float, float, float, float] | None:
        if not self._crop:
            return None
        cx, cy, cw, ch = self._crop
        s, (ox, oy) = self._scale, self._offset
        x1, y1 = ox + cx * s, oy + cy * s
        x2, y2 = x1 + cw * s, y1 + ch * s
        return x1, y1, x2, y2

    def _hit_test_crop(self, x: float, y: float) -> str | None:
        rect = self._crop_screen_rect()
        if rect is None:
            return None
        x1, y1, x2, y2 = rect
        tol = 10
        corners = {
            "tl": (x1, y1),
            "tr": (x2, y1),
            "bl": (x1, y2),
            "br": (x2, y2),
        }
        for handle, (hx, hy) in corners.items():
            if abs(x - hx) <= tol and abs(y - hy) <= tol:
                return handle
        if x1 <= x <= x2 and y1 <= y <= y2:
            return "move"
        return None

    def _update_hover_cursor(self, x: float, y: float) -> None:
        hit = self._hit_test_crop(x, y)
        self._hover_handle = hit
        if hit in {"tl", "br"}:
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif hit in {"tr", "bl"}:
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif hit == "move":
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _resize_crop_from_corner(self, handle: str, img_x: float, img_y: float) -> None:
        if not self._drag or not self._image_size:
            return
        _mode, _start_x, _start_y, orig = self._drag
        ox, oy, ow, oh = orig
        iw, ih = self._image_size
        aspect = ow / oh if oh > 0 else 1.0
        min_w = min(32.0, max(8.0, iw))
        min_h = min(32.0, max(8.0, ih))

        if handle in {"tl", "bl"}:
            anchor_x = ox + ow
            max_w = anchor_x
        else:
            anchor_x = ox
            max_w = iw - anchor_x

        if handle in {"tl", "tr"}:
            anchor_y = oy + oh
            max_h = anchor_y
        else:
            anchor_y = oy
            max_h = ih - anchor_y

        raw_w = max(min_w, abs(img_x - anchor_x))
        raw_h = max(min_h, abs(img_y - anchor_y))
        if raw_w / aspect <= raw_h:
            new_w = raw_w
            new_h = new_w / aspect
        else:
            new_h = raw_h
            new_w = new_h * aspect

        new_w = min(new_w, max_w, max_h * aspect)
        new_h = new_w / aspect
        if new_w < min_w or new_h < min_h:
            return

        x = anchor_x - new_w if handle in {"tl", "bl"} else anchor_x
        y = anchor_y - new_h if handle in {"tl", "tr"} else anchor_y
        self._crop = self._clamp_crop((x, y, new_w, new_h))
        self.update()
        self.crop_changed.emit(self._crop)

    def mousePressEvent(self, ev):
        if not self._crop or not self._image_size:
            return
        hit = self._hit_test_crop(ev.x(), ev.y())
        if hit:
            cx, cy, cw, ch = self._crop
            self._drag = (hit, ev.x(), ev.y(), (cx, cy, cw, ch))
            self._dragging = True
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def mouseMoveEvent(self, ev):
        if not self._crop or not self._image_size:
            return
        if not self._dragging or not self._drag:
            self._update_hover_cursor(ev.x(), ev.y())
            return
        mode, sx, sy, orig = self._drag
        if mode in {"tl", "tr", "bl", "br"}:
            img_x, img_y = self._img_pos(ev.x(), ev.y())
            self._resize_crop_from_corner(mode, img_x, img_y)
            return
        ocx, ocy, cw, ch = orig
        s = self._scale
        dx = (ev.x() - sx) / s
        dy = (ev.y() - sy) / s
        iw, ih = self._image_size
        nx = max(0.0, min(ocx + dx, iw - cw))
        ny = max(0.0, min(ocy + dy, ih - ch))
        self._crop = (nx, ny, cw, ch)
        self.update()
        self.crop_changed.emit(self._crop)

    def mouseReleaseEvent(self, _):
        self._drag = None
        self._dragging = False
        self._update_hover_cursor(self.mapFromGlobal(QCursor.pos()).x(),
                                  self.mapFromGlobal(QCursor.pos()).y())

    # ── Drag-and-drop ─────────────────────────────────────────────────────────
    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}

    def _drop_path(self, event) -> str | None:
        if not event.mimeData().hasUrls():
            return None
        for url in event.mimeData().urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if os.path.splitext(p)[1].lower() in self._IMAGE_EXTS:
                    return p
        return None

    def dragEnterEvent(self, event):
        if self._drop_path(event):
            event.acceptProposedAction()
            self._drop_hover = True
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._drop_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_hover = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drop_hover = False
        self.update()
        path = self._drop_path(event)
        if path:
            event.acceptProposedAction()
            self.image_dropped.emit(path)


class JarPreviewPanel(QWidget):
    """Shows a fitted image preview with a small metadata header."""

    def __init__(self, title: str = "PRINT PREVIEW",
                 empty_text: str = "Load an image to see the print preview",
                 parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._title = title
        self._preview_pix: QPixmap | None = None
        self._meta_text: str = ""
        self._empty_text: str = empty_text

    def set_preview(self, pix: QPixmap | None, meta_text: str = "") -> None:
        self._preview_pix = pix
        self._meta_text = meta_text
        self.update()

    def clear(self) -> None:
        self.set_preview(None, "")

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(T["panel_2"]))

        # Header strip with metadata.
        header_h = 28
        header_rect = QRect(0, 0, self.width(), header_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(T["panel"])))
        p.drawRect(header_rect)
        p.setPen(QPen(QColor(T["line_2"])))
        p.drawLine(0, header_h, self.width(), header_h)
        p.setFont(_mf(10, 600))
        p.setPen(QPen(QColor(T["mid"])))
        title = self._title
        if self._meta_text:
            title = f"{title}  ·  {self._meta_text}"
        p.drawText(header_rect.adjusted(12, 0, -12, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)

        # Body region for the preview pixmap.
        body = QRect(0, header_h, self.width(), self.height() - header_h)

        if self._preview_pix is None or self._preview_pix.isNull():
            p.setFont(_uf(12))
            p.setPen(QPen(QColor(T["dim"])))
            p.drawText(body, Qt.AlignmentFlag.AlignCenter, self._empty_text)
            p.end()
            return

        # Fit the preview into the body with aspect ratio preserved, letterboxing.
        pad = 12
        avail_w = max(1, body.width() - 2 * pad)
        avail_h = max(1, body.height() - 2 * pad)
        pw, ph = self._preview_pix.width(), self._preview_pix.height()
        if pw <= 0 or ph <= 0:
            p.end()
            return
        scale = min(avail_w / pw, avail_h / ph)
        dw = max(1, int(pw * scale))
        dh = max(1, int(ph * scale))
        dx = body.x() + (body.width() - dw) // 2
        dy = body.y() + (body.height() - dh) // 2

        transform = (
            Qt.TransformationMode.SmoothTransformation
            if scale < 1.0
            else Qt.TransformationMode.FastTransformation
        )
        scaled = self._preview_pix.scaled(
            dw, dh,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            transform,
        )
        p.drawPixmap(dx, dy, scaled)

        # Thin frame so it reads as the "print" rectangle.
        p.setPen(QPen(QColor(T["line"]), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(dx, dy, dw - 1, dh - 1)

        p.end()


class FilamentRow(QWidget):
    toggled        = Signal(str, bool)
    edit_requested = Signal(str)

    def __init__(self, hex_code: str, name: str, material: str, active: bool,
                 layer_count: int = 0, muted: bool = False, parent=None):
        super().__init__(parent)
        self._hex      = hex_code
        self._name     = name
        self._material = material
        self._active   = active
        self._layer_count = layer_count
        self._muted    = muted
        self._hover    = False
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)

    def isChecked(self) -> bool:
        return self._active

    def setChecked(self, v: bool):
        self._active = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg = QColor(T["hover"] if self._hover else T["panel_2"])
        p.fillRect(self.rect(), bg)

        # checkbox
        cb_x, cb_y = 12, 12
        p.setPen(QPen(QColor(T["line"]), 1))
        p.setBrush(QBrush(QColor(T["panel_2"])))
        p.drawRoundedRect(cb_x, cb_y, 16, 16, 3, 3)
        if self._active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(T["ink"])))
            p.drawRoundedRect(cb_x, cb_y, 16, 16, 3, 3)
            p.setPen(QPen(QColor(T["on_ink"]), 2))
            p.drawLine(cb_x + 4, cb_y + 8, cb_x + 7, cb_y + 11)
            p.drawLine(cb_x + 7, cb_y + 11, cb_x + 12, cb_y + 5)

        # swatch
        sw_x = 38
        try:
            sc = QColor(self._hex)
        except Exception:
            sc = QColor(T["mid"])
        p.setPen(QPen(QColor(T["line"]), 1))
        p.setBrush(QBrush(sc))
        p.drawRoundedRect(sw_x, 11, 18, 18, 4, 4)

        # material tag / edit button (swaps on hover)
        tag_w = 72
        tag_x = self.width() - tag_w - 8

        # layer-count badge, sits just to the left of the material tag
        badge_w = 30
        badge_x = tag_x - 4 - badge_w
        alpha = 90 if self._muted else (255 if self._active else 120)

        # name (must end before the badge)
        name_right = badge_x - 8
        p.setFont(_uf(12, 500))
        ink = QColor(T["ink"])
        ink.setAlpha(alpha)
        p.setPen(QPen(ink))
        p.drawText(QRect(64, 0, max(0, name_right - 64), 40),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._name)

        # Layer-count chip
        mid = QColor(T["mid"])
        mid.setAlpha(alpha)
        p.setFont(_mf(9))
        p.setPen(QPen(QColor(T["line"])))
        p.setBrush(QBrush(QColor(T["panel"])))
        p.drawRoundedRect(badge_x, 11, badge_w, 18, 3, 3)
        p.setPen(QPen(mid))
        badge_text = f"{self._layer_count}L" if self._layer_count > 0 else "—"
        p.drawText(QRect(badge_x, 11, badge_w, 18), Qt.AlignmentFlag.AlignCenter, badge_text)

        # material tag / edit button (swaps on hover)
        if self._hover:
            p.setPen(QPen(QColor(T["ink"]), 1))
            p.setBrush(QBrush(QColor(T["selected"])))
            p.drawRoundedRect(tag_x, 11, tag_w, 18, 3, 3)
            p.setFont(_uf(11))
            p.setPen(QPen(QColor(T["ink"])))
            p.drawText(QRect(tag_x, 11, tag_w, 18), Qt.AlignmentFlag.AlignCenter, "Edit ✎")
        else:
            p.setFont(_mf(9))
            p.setPen(QPen(QColor(T["line"])))
            p.setBrush(QBrush(QColor(T["panel"])))
            p.drawRoundedRect(tag_x, 11, tag_w, 18, 3, 3)
            p.setPen(QPen(mid))
            p.drawText(QRect(tag_x, 11, tag_w, 18), Qt.AlignmentFlag.AlignCenter, self._material[:12])

        p.end()

    def enterEvent(self, _):
        self._hover = True
        self.update()

    def leaveEvent(self, _):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        tag_w  = 72
        tag_x  = self.width() - tag_w - 8
        if self._hover and QRect(tag_x, 11, tag_w, 18).contains(e.position().toPoint()):
            self.edit_requested.emit(self._hex)
            return
        self._active = not self._active
        self.update()
        self.toggled.emit(self._hex, self._active)


class FilamentSectionHeader(QWidget):
    """Small section divider in the filament list."""

    def __init__(self, title: str, count: int, parent=None):
        super().__init__(parent)
        self._title = title
        self._count = count
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_count(self, count: int) -> None:
        self._count = count
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T["panel"]))
        p.setPen(QPen(QColor(T["line_2"])))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.setFont(_mf(9, 600))
        p.setPen(QPen(QColor(T["mid"])))
        text = f"{self._title}  ·  {self._count}"
        p.drawText(QRect(16, 0, self.width() - 32, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.end()


class ColorEditorDialog(QDialog):
    """Edit or add a palette color and its per-layer HSL transmittance values.

    Based on the PIXEstL palette format: https://github.com/gaugo87/PIXEstL
    Each color has layers 1-5 (1 = top/transparent, 5 = deepest/opaque).
    Each layer carries H (0-360), S (0-100), L (0-100) that map image brightness
    to 3D-print layer thickness when the lithophane is backlit.
    """

    def __init__(self, hex_code: str, info: dict, is_new: bool = False, parent=None):
        super().__init__(parent)
        self._orig_hex = hex_code
        self._is_new   = is_new
        self._deleted  = False
        self._data     = copy.deepcopy(info)

        self.setWindowTitle("Add color" if is_new else "Edit color")
        self.setMinimumWidth(540)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._build_header())
        lay.addWidget(_hline())
        lay.addWidget(self._build_basic())
        lay.addWidget(_hline())
        lay.addWidget(self._build_layers_section())
        lay.addWidget(_hline())
        lay.addWidget(self._build_footer())

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(72)
        w.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda: w.setStyleSheet(f"background: {T['panel']};"))
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(16)

        self._hdr_swatch = QLabel()
        self._hdr_swatch.setFixedSize(48, 48)
        lay.addWidget(self._hdr_swatch)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self._hdr_name = QLabel()
        self._hdr_name.setFont(_uf(15, 600))
        self._hdr_name.setStyleSheet(f"color: {T['ink']}; background: transparent;")
        _on_theme(lambda: self._hdr_name.setStyleSheet(f"color: {T['ink']}; background: transparent;"))
        info_col.addWidget(self._hdr_name)
        self._hdr_sub = QLabel()
        self._hdr_sub.setFont(_mf(10))
        self._hdr_sub.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: self._hdr_sub.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        info_col.addWidget(self._hdr_sub)
        lay.addLayout(info_col)
        lay.addStretch()
        return w

    # ── Basic fields ──────────────────────────────────────────────────────────
    def _build_basic(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 14, 20, 16)
        lay.setSpacing(10)

        sec = QLabel("BASIC")
        sec.setFont(_uf(10, 600))
        sec.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;")
        _on_theme(lambda: sec.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;"))
        lay.addWidget(sec)

        def _lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setFont(_uf(12))
            l.setFixedWidth(64)
            l.setStyleSheet(f"color: {T['mid']}; background: transparent;")
            _on_theme(lambda lb=l: lb.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
            return l

        # Hex row
        hex_row = QHBoxLayout()
        hex_row.setSpacing(10)
        hex_row.addWidget(_lbl("Hex"))
        self._hex_input = QLineEdit(self._orig_hex)
        self._hex_input.setFont(_mf(12))
        self._hex_input.setFixedHeight(32)
        self._hex_input.textChanged.connect(self._refresh_header)
        hex_row.addWidget(self._hex_input, 1)
        pick_btn = QPushButton("Pick…")
        pick_btn.setFont(_uf(11))
        pick_btn.setFixedSize(56, 32)
        pick_btn.clicked.connect(self._pick_color)
        hex_row.addWidget(pick_btn)
        lay.addLayout(hex_row)

        # Name / material
        full_name = self._data.get("name", "")
        m = re.match(r"^(.*?)\[([^\]]+)\]$", full_name)
        name_only = m.group(1).strip() if m else full_name
        mat_only  = m.group(2)          if m else ""

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_row.addWidget(_lbl("Name"))
        self._name_input = QLineEdit(name_only)
        self._name_input.setFont(_uf(12))
        self._name_input.setFixedHeight(32)
        self._name_input.textChanged.connect(self._refresh_header)
        name_row.addWidget(self._name_input, 1)
        lay.addLayout(name_row)

        mat_row = QHBoxLayout()
        mat_row.setSpacing(10)
        mat_row.addWidget(_lbl("Material"))
        self._mat_input = QLineEdit(mat_only)
        self._mat_input.setFont(_uf(12))
        self._mat_input.setFixedHeight(32)
        self._mat_input.setPlaceholderText("e.g. PLA Basic")
        mat_row.addWidget(self._mat_input, 1)
        lay.addLayout(mat_row)

        self._refresh_header()
        return w

    # ── Layer transmittance ───────────────────────────────────────────────────
    def _build_layers_section(self) -> QWidget:
        outer = QWidget()
        outer.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(outer)
        vlay.setContentsMargins(20, 14, 20, 16)
        vlay.setSpacing(12)

        hrow = QHBoxLayout()
        sec = QLabel("TRANSMITTANCE LAYERS")
        sec.setFont(_uf(10, 600))
        sec.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;")
        _on_theme(lambda: sec.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;"))
        hrow.addWidget(sec)
        hrow.addStretch()
        hint = QLabel("5 = deepest (opaque)  ·  1 = top (transparent)")
        hint.setFont(_uf(10))
        hint.setStyleSheet(f"color: {T['dim']}; background: transparent;")
        _on_theme(lambda: hint.setStyleSheet(f"color: {T['dim']}; background: transparent;"))
        hrow.addWidget(hint)
        vlay.addLayout(hrow)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedHeight(295)
        scroll.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        ilay = QVBoxLayout(inner)
        ilay.setContentsMargins(0, 0, 8, 0)
        ilay.setSpacing(8)

        layers = self._data.get("layers", {})
        self._layer_controls: dict = {}

        for n in range(5, 0, -1):
            key = str(n)
            ld  = layers.get(key, {})
            h   = float(ld.get("H", 0.0))
            s   = float(ld.get("S", 100.0))
            l   = float(ld.get("L", 50.0))
            lw, ctrls = self._make_layer_row(n, h, s, l)
            self._layer_controls[key] = ctrls
            ilay.addWidget(lw)

        ilay.addStretch()
        scroll.setWidget(inner)
        vlay.addWidget(scroll)
        return outer

    def _make_layer_row(self, num: int, h: float, s: float, l: float):
        labels = {
            5: "Layer 5  ·  Deepest",
            4: "Layer 4",
            3: "Layer 3",
            2: "Layer 2",
            1: "Layer 1  ·  Top",
        }

        w = QWidget()
        w.setStyleSheet(f"background: {T['panel_2']}; border-radius: 6px;")
        _on_theme(lambda: w.setStyleSheet(f"background: {T['panel_2']}; border-radius: 6px;"))
        vlay = QVBoxLayout(w)
        vlay.setContentsMargins(12, 8, 12, 10)
        vlay.setSpacing(4)

        # Title row + live HSL swatch
        tr = QHBoxLayout()
        tr.setSpacing(8)
        title = QLabel(labels[num])
        title.setFont(_uf(11, 600))
        title.setStyleSheet(f"color: {T['ink']}; background: transparent;")
        _on_theme(lambda lb=title: lb.setStyleSheet(f"color: {T['ink']}; background: transparent;"))
        tr.addWidget(title)
        tr.addStretch()
        swatch = QLabel()
        swatch.setFixedSize(36, 16)
        swatch.setStyleSheet(f"border-radius: 3px; background: hsl({h:.0f}, {s:.0f}%, {l:.0f}%);")
        tr.addWidget(swatch)
        vlay.addLayout(tr)

        def _slider_ss():
            return f"""
                QSlider::groove:horizontal {{
                    height: 4px; background: {T['line']}; border-radius: 2px;
                }}
                QSlider::handle:horizontal {{
                    width: 13px; height: 13px; margin: -5px 0;
                    background: {T['ink']}; border-radius: 6px;
                }}
                QSlider::sub-page:horizontal {{
                    background: {T['dim']}; border-radius: 2px;
                }}
            """

        def _hsl_row(lbl_text: str, init: float, max_f: float):
            r = QHBoxLayout()
            r.setSpacing(6)
            lbl = QLabel(lbl_text)
            lbl.setFont(_uf(10, 600))
            lbl.setFixedWidth(14)
            lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
            _on_theme(lambda lb=lbl: lb.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
            r.addWidget(lbl)

            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setMinimum(0)
            sl.setMaximum(int(max_f * 10))
            sl.setValue(int(round(init * 10)))
            sl.setFixedHeight(18)
            sl.setStyleSheet(_slider_ss())
            _on_theme(lambda s=sl: s.setStyleSheet(_slider_ss()))
            r.addWidget(sl, 1)

            inp = QLineEdit(f"{init:.1f}")
            inp.setFont(_mf(10))
            inp.setFixedSize(56, 26)
            inp.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            r.addWidget(inp)
            return r, sl, inp

        hr, h_sl, h_inp = _hsl_row("H", h, 360.0)
        sr, s_sl, s_inp = _hsl_row("S", s, 100.0)
        lr, l_sl, l_inp = _hsl_row("L", l, 100.0)

        vlay.addLayout(hr)
        vlay.addLayout(sr)
        vlay.addLayout(lr)

        # Sync helpers — closures capture this call frame's slider/input refs
        def _sl_changed(sl, inp):
            val = sl.value() / 10.0
            inp.blockSignals(True)
            inp.setText(f"{val:.1f}")
            inp.blockSignals(False)
            _refresh_swatch()

        def _inp_changed(sl, inp):
            try:
                val = max(0.0, min(sl.maximum() / 10.0, float(inp.text())))
                sl.blockSignals(True)
                sl.setValue(int(round(val * 10)))
                sl.blockSignals(False)
            except ValueError:
                pass
            _refresh_swatch()

        def _refresh_swatch():
            hv = h_sl.value() / 10.0
            sv = s_sl.value() / 10.0
            lv = l_sl.value() / 10.0
            swatch.setStyleSheet(
                f"border-radius: 3px; background: hsl({hv:.0f}, {sv:.0f}%, {lv:.0f}%);"
            )

        h_sl.valueChanged.connect(lambda _: _sl_changed(h_sl, h_inp))
        s_sl.valueChanged.connect(lambda _: _sl_changed(s_sl, s_inp))
        l_sl.valueChanged.connect(lambda _: _sl_changed(l_sl, l_inp))
        h_inp.editingFinished.connect(lambda: _inp_changed(h_sl, h_inp))
        s_inp.editingFinished.connect(lambda: _inp_changed(s_sl, s_inp))
        l_inp.editingFinished.connect(lambda: _inp_changed(l_sl, l_inp))

        ctrls = {"swatch": swatch, "H": (h_sl, h_inp), "S": (s_sl, s_inp), "L": (l_sl, l_inp)}
        return w, ctrls

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(52)
        w.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda: w.setStyleSheet(f"background: {T['panel']};"))
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 9, 20, 9)
        lay.setSpacing(8)

        if not self._is_new:
            del_btn = QPushButton("Delete color")
            del_btn.setFont(_uf(12))
            del_btn.setFixedHeight(34)
            _del_ss = lambda: f"""
                QPushButton {{
                    background: transparent; border: 1px solid {T['err']};
                    border-radius: 6px; color: {T['err']}; padding: 0 12px; height: 34px;
                }}
                QPushButton:hover {{ background: {T['err']}; color: {T['on_ink']}; }}
            """
            del_btn.setStyleSheet(_del_ss())
            _on_theme(lambda b=del_btn: b.setStyleSheet(_del_ss()))
            del_btn.clicked.connect(self._do_delete)
            lay.addWidget(del_btn)

        lay.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(_uf(12))
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        lay.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setFont(_uf(12, 600))
        save_btn.setFixedHeight(34)
        _save_ss = lambda: f"""
            QPushButton {{
                background: {T['ink']}; color: {T['on_ink']}; border: none;
                border-radius: 6px; padding: 0 20px; height: 34px;
            }}
            QPushButton:hover {{ background: {T['ink_2']}; }}
        """
        save_btn.setStyleSheet(_save_ss())
        _on_theme(lambda b=save_btn: b.setStyleSheet(_save_ss()))
        save_btn.clicked.connect(self.accept)
        lay.addWidget(save_btn)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _refresh_header(self):
        hex_val  = self._hex_input.text().strip() if hasattr(self, "_hex_input") else self._orig_hex
        name_val = self._name_input.text().strip() if hasattr(self, "_name_input") else ""
        c = QColor(hex_val)
        if c.isValid():
            self._hdr_swatch.setStyleSheet(f"border-radius: 8px; background: {hex_val};")
        self._hdr_name.setText(name_val or hex_val)
        self._hdr_sub.setText(hex_val)

    def _pick_color(self):
        current = QColor(self._hex_input.text())
        if not current.isValid():
            current = QColor(self._orig_hex)
        chosen = QColorDialog.getColor(current, self, "Pick color")
        if chosen.isValid():
            self._hex_input.setText(chosen.name().upper())

    def _do_delete(self):
        self._deleted = True
        self.accept()

    def get_result(self):
        """Return (new_hex, updated_info) or (None, None) if the color was deleted."""
        if self._deleted:
            return None, None

        raw = self._hex_input.text().strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        new_hex = raw.upper()

        name = self._name_input.text().strip()
        mat  = self._mat_input.text().strip()
        full = f"{name}[{mat}]" if mat else name

        layers = {}
        for key, ctrls in self._layer_controls.items():
            h_sl, _ = ctrls["H"]
            s_sl, _ = ctrls["S"]
            l_sl, _ = ctrls["L"]
            layers[key] = {
                "H": round(h_sl.value() / 10.0, 1),
                "S": round(s_sl.value() / 10.0, 1),
                "L": round(l_sl.value() / 10.0, 1),
            }

        info = {**self._data, "name": full, "active": self._data.get("active", True), "layers": layers}
        return new_hex, info


class ConsoleWidget(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(_mf(12))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {T['log_bg']};
                color: {T['log_fg']};
                border: none;
                padding: 10px 12px;
                font-family: 'JetBrains Mono', Consolas, monospace;
                font-size: 12px;
            }}
        """)
        _on_theme(lambda: self.setStyleSheet(f"""
            QTextEdit {{
                background: {T['log_bg']};
                color: {T['log_fg']};
                border: none;
                padding: 10px 12px;
                font-family: 'JetBrains Mono', Consolas, monospace;
                font-size: 12px;
            }}
        """))

    def append_msg(self, msg: str, tag: str = ""):
        colors = {
            "ok":  T["log_ok"],
            "err": T["log_err"],
            "dim": T["log_dim"],
        }
        col = colors.get(tag, T["log_fg"])
        msg_html = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.moveCursor(self.textCursor().MoveOperation.End)
        self.insertHtml(f'<span style="color:{col};">{msg_html}</span>')
        self.moveCursor(self.textCursor().MoveOperation.End)


class StatusPill(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._color = T["mid"]
        self.setFixedHeight(22)
        fm = QFontMetrics(_mf(10))
        self.setFixedWidth(fm.horizontalAdvance(text) + 26)

    def set_state(self, text: str, color: str):
        self._text  = text
        self._color = color
        fm = QFontMetrics(_mf(10))
        self.setFixedWidth(fm.horizontalAdvance(text) + 26)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(T["line"]), 1))
        p.setBrush(QBrush(QColor(T["panel_2"])))
        p.drawRoundedRect(0, 0, self.width(), 22, 11, 11)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(self._color)))
        p.drawEllipse(8, 8, 6, 6)
        p.setFont(_mf(10, 500))
        p.setPen(QPen(QColor(T["ink_2"])))
        p.drawText(QRect(20, 0, self.width() - 22, 22), Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()


# ── Presets & Layer heights ───────────────────────────────────────────────────
PRESETS = [
    ("bambu_frame", "Bambu Frame", "108 × 144 mm", 108, 144),
    ("mini",        "Mini",        "54 × 72 mm",    54,  72),
    ("ultra_mini",  "Ultra Mini",  "27 × 36 mm",    27,  36),
]

LAYER_HEIGHTS = [
    ("0.08", "0.08", "fine"),
    ("0.10", "0.10", "std"),
    ("0.12", "0.12", "0.4n"),
    ("0.16", "0.16", "draft"),
]

QUALITY_PRESETS = [
    ("draft",    "Draft",    "0.30 mm", "0.30", "0.30", 1_000_000),
    ("balanced", "Balanced", "0.20 mm", "0.20", "0.20", 4_000_000),
    ("fine",     "Fine",     "0.12 mm", "0.12", "0.12", 8_000_000),
]

LITHO_MODES = [
    ("color", "Color", "multi"),
    ("single", "Single", "1 color"),
]

SINGLE_COLOR_LAYER_HEIGHT = "0.10"
SINGLE_COLOR_TEXTURE_MAX_LAYERS = "32"

PRINT_PROFILES = [
    ("litho", "High Quality Lithophane", "", {
        "quality": "balanced", "layer_height": "0.10", "color_px": "0.20",
        "tex_px": "0.20", "layers": "5", "backing": "2", "tex_min": "3",
        "tex_max": "15", "fine_layer": "0.04", "border": "2",
        "pixel_mode": "ADDITIVE", "output_mode": "both", "color_number": "",
        "distance": "CIELab", "curve": "",
    }),
]

def _safe_dirname(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80]


# ── Main window ───────────────────────────────────────────────────────────────
class LithoWindow(QMainWindow):
    _LEFT_PANE_DEFAULT = 340
    _RIGHT_PANE_DEFAULT = 175
    _LEFT_PANE_MIN = 260
    _RIGHT_PANE_MIN = 160
    _CENTER_PANE_MIN = 320
    _DRAWER_TAB_WIDTH = 22

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Litho — Image to 3D STL")
        self.resize(1456, 820)
        self.setMinimumSize(760, 560)

        # State
        self._image_path:    str   = ""
        self._image_size:    tuple = None
        self._image_aspect:  float = None
        self._updating_dims: bool  = False
        self.palette_data:   dict  = {}
        self.color_vars:     dict  = {}   # hex -> bool (mutable via FilamentRow)
        self._filament_rows: dict  = {}   # hex -> FilamentRow
        self._filament_row_section: dict = {}  # hex -> "measured" | "flat"
        self._filament_section_headers: dict = {}  # section -> FilamentSectionHeader
        self._single_color_hex = "#FFFFFF"
        self._proc = None
        self.output_dir = os.path.join(SCRIPT_DIR, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        self._default_palette = os.path.join(
            SCRIPT_DIR, "resources", "filament-palette-0.10mm.json"
        )
        self._palette_path = self._default_palette
        self._active_preset     = "bambu_frame"
        self._active_layer_h    = "0.10"
        self._active_quality    = "balanced"
        self._active_print_profile = "litho"
        self._preview_cell_cap  = 4_000_000
        self._last_preview_capped = False
        self._last_preview_requested: tuple | None = None
        self._last_preview_actual: tuple | None = None
        self._show_hex_only = False
        self._width_mm:  str = "108"
        self._height_mm: str = "144"
        self._lock_ratio: bool = False
        self._color_px_w:  str = "0.2"
        self._tex_px_w:    str = "0.2"
        self._layer_thick:    str = "0.10"
        self._layer_count:    str = "5"
        self._backing_layers:     str = "2"
        self._texture_min_layers: str = "3"
        self._texture_max_layers: str = "15"
        self._fine_layer_h:       str = "0.04"
        self._border_mm:          str = "2"
        self._pixel_mode:         str = "ADDITIVE"
        self._output_mode:        str = "both"
        self._color_number:       str = ""
        self._distance_method:    str = "CIELab"
        self._curve:              str = ""
        self._low_memory:         bool = False
        self._layer_threads:      str = ""
        self._row_threads:        str = ""
        self._layer_timeout:      str = ""
        self._row_timeout:        str = ""
        self._left_pane_last_width = self._LEFT_PANE_DEFAULT
        self._right_pane_last_width = self._RIGHT_PANE_DEFAULT

        # Rotation & image adjustments (non-destructive, applied at preview + export)
        self._rotation:       int = 0   # 0 | 90 | 180 | 270 (clockwise degrees)
        self._image_size_orig: tuple = None   # pre-rotation original dimensions
        # Crop frame orientation — chosen independently of image rotation.
        # "landscape" forces W ≥ H; "portrait" forces W ≤ H.
        self._crop_orientation: str = "portrait" if float(self._height_mm) >= float(self._width_mm) else "landscape"
        self._adj_exposure:   int = 0   # -100 to +100
        self._adj_highlights: int = 0
        self._adj_shadows:    int = 0
        self._adj_saturation: int = 0
        self._adj_tint:       int = 0   # -100 green … +100 magenta
        self._adj_color_temp: int = 0   # -100 cool  … +100 warm

        self._build_window()
        _on_theme(self._on_theme_changed)

        geom = _settings.value("window_geometry")
        if geom:
            self.restoreGeometry(geom)

        QTimer.singleShot(0, self._load_palette)
        QTimer.singleShot(0, self._update_z_stat)

    # ── Window assembly ───────────────────────────────────────────────────────

    def _build_window(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet(f"background: {T['bg']};")
        _on_theme(lambda: root.setStyleSheet(f"background: {T['bg']};"))

        vlay = QVBoxLayout(root)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        topbar = self._build_topbar()
        vlay.addWidget(topbar)
        vlay.addWidget(_hline())

        left   = self._build_left()
        center = self._build_center()
        right  = self._build_right()

        center.setMinimumWidth(self._CENTER_PANE_MIN)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        center.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._left_tab.clicked.connect(self._toggle_left_pane)
        self._right_tab.clicked.connect(self._toggle_right_pane)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setChildrenCollapsible(False)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet(self._main_splitter_qss())
        _on_theme(lambda s=splitter: s.setStyleSheet(self._main_splitter_qss()))
        splitter.splitterMoved.connect(self._on_main_splitter_moved)
        splitter.setSizes([
            self._LEFT_PANE_DEFAULT,
            941,
            self._RIGHT_PANE_DEFAULT,
        ])

        self._main_splitter = splitter
        self._left_pane = left
        self._right_pane = right

        vlay.addWidget(splitter, 1)
        vlay.addWidget(_hline())
        vlay.addWidget(self._build_footer())
        QTimer.singleShot(0, self._restore_main_splitter_state)

    def _toggle_left_pane(self) -> None:
        content = getattr(self, "_left_content", None)
        if content is None:
            return
        self._set_side_pane_visible("left", not content.isVisible())

    def _toggle_right_pane(self) -> None:
        content = getattr(self, "_right_content", None)
        if content is None:
            return
        self._set_side_pane_visible("right", not content.isVisible())

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda: bar.setStyleSheet(f"background: {T['panel']};"))
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(16)

        # Brand
        lay.addWidget(BrandMark())
        name_lbl = QLabel("Litho")
        name_lbl.setFont(_uf(14, 600))
        name_lbl.setStyleSheet(f"color: {T['ink']}; background: transparent;")
        _on_theme(lambda: name_lbl.setStyleSheet(f"color: {T['ink']}; background: transparent;"))
        lay.addWidget(name_lbl)

        sub_lbl = QLabel("Image → 3D STL")
        sub_lbl.setFont(_uf(12))
        sub_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: sub_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        lay.addWidget(sub_lbl)

        lay.addWidget(_vline())

        self._status_pill = StatusPill("Ready")
        lay.addWidget(self._status_pill)

        lay.addStretch()

        return bar

    def _main_splitter_qss(self) -> str:
        return f"""
            QSplitter::handle {{
                background: {T['line']};
            }}
            QSplitter::handle:hover {{
                background: {T['dim']};
            }}
        """

    def _settings_bool(self, key: str, default: bool) -> bool:
        value = _settings.value(key, default)
        if isinstance(value, str):
            return value.lower() not in {"0", "false", "no", "off"}
        return bool(value)

    def _settings_int(self, key: str, default: int) -> int:
        value = _settings.value(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _restore_main_splitter_state(self) -> None:
        splitter = getattr(self, "_main_splitter", None)
        if splitter is None:
            return

        self._left_pane_last_width = max(
            self._LEFT_PANE_MIN,
            self._settings_int("left_pane_last_width", self._LEFT_PANE_DEFAULT),
        )
        self._right_pane_last_width = max(
            self._RIGHT_PANE_MIN,
            self._settings_int("right_pane_last_width", self._RIGHT_PANE_DEFAULT),
        )

        restored = False
        state = _settings.value("main_splitter_state")
        if state:
            try:
                restored = splitter.restoreState(state)
            except TypeError:
                restored = False
        if not restored:
            splitter.setSizes([
                self._LEFT_PANE_DEFAULT,
                max(
                    self._CENTER_PANE_MIN,
                    self.width() - self._LEFT_PANE_DEFAULT - self._RIGHT_PANE_DEFAULT,
                ),
                self._RIGHT_PANE_DEFAULT,
            ])

        if not self._settings_bool("left_pane_visible", True):
            self._set_side_pane_visible("left", False)
        if not self._settings_bool("right_pane_visible", True):
            self._set_side_pane_visible("right", False)

        self._sync_pane_toggles()

    def _on_main_splitter_moved(self, _pos: int, _index: int) -> None:
        splitter = getattr(self, "_main_splitter", None)
        if splitter is None:
            return
        sizes = splitter.sizes()
        if len(sizes) != 3:
            return
        left_open = getattr(self, "_left_content", None) is not None and self._left_content.isVisible()
        right_open = getattr(self, "_right_content", None) is not None and self._right_content.isVisible()
        if left_open and sizes[0] > self._DRAWER_TAB_WIDTH:
            self._left_pane_last_width = sizes[0]
        if right_open and sizes[2] > self._DRAWER_TAB_WIDTH:
            self._right_pane_last_width = sizes[2]
        _settings.setValue("left_pane_visible", left_open)
        _settings.setValue("right_pane_visible", right_open)
        _settings.setValue("left_pane_last_width", self._left_pane_last_width)
        _settings.setValue("right_pane_last_width", self._right_pane_last_width)
        self._sync_pane_toggles()

    def _set_side_pane_visible(self, side: str, visible: bool) -> None:
        splitter = getattr(self, "_main_splitter", None)
        if splitter is None:
            return
        sizes = splitter.sizes()
        if len(sizes) != 3:
            return

        tab_width = self._DRAWER_TAB_WIDTH
        if side == "left":
            index = 0
            last_attr = "_left_pane_last_width"
            default_width = self._LEFT_PANE_DEFAULT
            min_width = self._LEFT_PANE_MIN + tab_width
            setting_key = "left_pane_visible"
            content = getattr(self, "_left_content", None)
        else:
            index = 2
            last_attr = "_right_pane_last_width"
            default_width = self._RIGHT_PANE_DEFAULT
            min_width = self._RIGHT_PANE_MIN + tab_width
            setting_key = "right_pane_visible"
            content = getattr(self, "_right_content", None)

        current = sizes[index]
        currently_open = content is not None and content.isVisible()

        if visible:
            if not currently_open:
                if content is not None:
                    content.setVisible(True)
                desired = max(min_width, getattr(self, last_attr, default_width))
                total = max(1, sum(sizes))
                other_index = 2 if index == 0 else 0
                max_desired = max(
                    min_width,
                    total - sizes[other_index] - self._CENTER_PANE_MIN,
                )
                desired = min(desired, max_desired)
                sizes[index] = desired
                sizes[1] = max(self._CENTER_PANE_MIN, sizes[1] - (desired - current))
                splitter.setSizes(sizes)
        else:
            if currently_open:
                if current > tab_width:
                    setattr(self, last_attr, current)
                if content is not None:
                    content.setVisible(False)
                sizes[1] += (current - tab_width)
                sizes[index] = tab_width
                splitter.setSizes(sizes)

        _settings.setValue(setting_key, visible)
        _settings.setValue("left_pane_last_width", self._left_pane_last_width)
        _settings.setValue("right_pane_last_width", self._right_pane_last_width)
        self._sync_pane_toggles()

    def _sync_pane_toggles(self) -> None:
        left_tab = getattr(self, "_left_tab", None)
        left_content = getattr(self, "_left_content", None)
        if left_tab is not None and left_content is not None:
            left_tab.set_open(left_content.isVisible())
        right_tab = getattr(self, "_right_tab", None)
        right_content = getattr(self, "_right_content", None)
        if right_tab is not None and right_content is not None:
            right_tab.set_open(right_content.isVisible())

    def _build_left(self) -> QWidget:
        col = QWidget()
        col.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda: col.setStyleSheet(f"background: {T['panel']};"))
        col.setMinimumWidth(self._LEFT_PANE_MIN)
        vlay = QVBoxLayout(col)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # Source head
        vlay.addWidget(PanelHead("Settings"))

        # Source card
        self._source_card = SourceCard()
        self._source_card.browse_clicked.connect(self._browse_image)
        vlay.addWidget(self._source_card)
        vlay.addWidget(_hline())

        # Scrollable parameters
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        ilay = QVBoxLayout(inner)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(0)

        ilay.addWidget(self._make_image_tools_group())
        ilay.addWidget(_hline())
        ilay.addWidget(self._make_frame_group())
        ilay.addWidget(_hline())
        ilay.addWidget(self._make_engine_group())
        ilay.addWidget(_hline())
        ilay.addWidget(self._make_resolution_group())
        ilay.addStretch()

        scroll.setWidget(inner)
        vlay.addWidget(scroll, 1)

        self._left_content = col
        self._left_tab = DrawerTab("Settings", side="left")

        outer = QWidget()
        outer.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda w=outer: w.setStyleSheet(f"background: {T['panel']};"))
        olay = QHBoxLayout(outer)
        olay.setContentsMargins(0, 0, 0, 0)
        olay.setSpacing(0)
        olay.addWidget(col, 1)
        olay.addWidget(self._left_tab)
        return outer

    def _make_image_tools_group(self) -> QWidget:
        grp = QWidget()
        grp.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(grp)
        vlay.setContentsMargins(10, 8, 10, 10)
        vlay.setSpacing(6)

        # Collapsible content container
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content.hide()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(5)

        # Header row
        head_row = QHBoxLayout()
        head_row.setSpacing(6)

        chevron = QPushButton("▶")
        chevron.setFixedSize(18, 18)
        chevron.setFont(_uf(9))
        chevron.setFlat(True)
        chevron.setStyleSheet("background: transparent; border: none; padding: 0;")
        chevron.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(chevron)

        head = QLabel("Image settings")
        head.setFont(_uf(10, 600))
        head.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;")
        _on_theme(lambda: head.setStyleSheet(
            f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;"))
        head.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(head)
        head_row.addStretch()
        reset_btn = QPushButton("Reset all")
        reset_btn.setFixedHeight(18)
        reset_btn.setFont(_uf(9))
        reset_btn.setToolTip("Reset all adjustments to zero")
        reset_btn.clicked.connect(self._reset_adjustments)
        head_row.addWidget(reset_btn)
        vlay.addLayout(head_row)

        def _toggle_image_tools():
            expanded = content.isVisible()
            content.setVisible(not expanded)
            chevron.setText("▶" if expanded else "▼")

        chevron.clicked.connect(_toggle_image_tools)
        head.mousePressEvent = lambda _e: _toggle_image_tools()

        # Rotate row
        rot_row = QHBoxLayout()
        rot_row.setSpacing(6)
        rot_lbl = QLabel("Rotate")
        rot_lbl.setFont(_uf(11))
        rot_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: rot_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        rot_row.addWidget(rot_lbl)
        rot_row.addStretch()
        fit_crop_btn = QPushButton("Fit crop")
        fit_crop_btn.setFixedSize(56, 22)
        fit_crop_btn.setFont(_uf(10))
        fit_crop_btn.setToolTip("Reset and center the crop box")
        fit_crop_btn.clicked.connect(self._recenter_crop)
        rot_row.addWidget(fit_crop_btn)
        rot_left = QPushButton("↺")
        rot_left.setFixedSize(28, 22)
        rot_left.setFont(_uf(13))
        rot_left.setToolTip("Rotate image 90° counter-clockwise (crop frame stays put)")
        rot_left.clicked.connect(lambda: self._on_rotate(-90))
        rot_right = QPushButton("↻")
        rot_right.setFixedSize(28, 22)
        rot_right.setFont(_uf(13))
        rot_right.setToolTip("Rotate image 90° clockwise (crop frame stays put)")
        rot_right.clicked.connect(lambda: self._on_rotate(90))
        rot_row.addWidget(rot_left)
        rot_row.addWidget(rot_right)
        content_lay.addLayout(rot_row)

        # Crop orientation row — choose landscape or portrait crop frame
        crop_row = QHBoxLayout()
        crop_row.setSpacing(6)
        crop_lbl = QLabel("Crop")
        crop_lbl.setFont(_uf(11))
        crop_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: crop_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        crop_row.addWidget(crop_lbl)
        crop_row.addStretch()

        def _toggle_btn_ss() -> str:
            return (
                f"QPushButton {{"
                f" background: {T['panel_2']}; color: {T['ink_2']};"
                f" border: 1px solid {T['line']}; border-radius: 4px; padding: 0 6px;"
                f"}}"
                f"QPushButton:hover {{ background: {T['hover']}; }}"
                f"QPushButton:checked {{"
                f" background: {T['selected']}; color: {T['ink']};"
                f" border: 1px solid {T['ink']};"
                f"}}"
            )

        self._land_btn = QPushButton("▭ Landscape")
        self._land_btn.setFixedSize(86, 22)
        self._land_btn.setFont(_uf(10))
        self._land_btn.setCheckable(True)
        self._land_btn.setToolTip("Landscape crop frame (wider than tall)")
        self._land_btn.setStyleSheet(_toggle_btn_ss())
        self._land_btn.clicked.connect(lambda: self._set_crop_orientation("landscape"))
        crop_row.addWidget(self._land_btn)

        self._port_btn = QPushButton("▯ Portrait")
        self._port_btn.setFixedSize(74, 22)
        self._port_btn.setFont(_uf(10))
        self._port_btn.setCheckable(True)
        self._port_btn.setToolTip("Portrait crop frame (taller than wide)")
        self._port_btn.setStyleSheet(_toggle_btn_ss())
        self._port_btn.clicked.connect(lambda: self._set_crop_orientation("portrait"))
        crop_row.addWidget(self._port_btn)

        _on_theme(lambda: (
            self._land_btn.setStyleSheet(_toggle_btn_ss()),
            self._port_btn.setStyleSheet(_toggle_btn_ss()),
        ))

        content_lay.addLayout(crop_row)
        self._sync_orientation_buttons()

        def _signed_value(value: int) -> str:
            return "0" if value == 0 else f"{value:+d}"

        def _exposure_value(value: int) -> str:
            ev = value / 50.0
            return "0 EV" if value == 0 else f"{ev:+.1f} EV"

        def _saturation_value(value: int) -> str:
            return f"{1.0 + value / 100.0:.1f}x"

        adj_specs = [
            ("Temperature", "Color temperature", "_adj_color_temp",
             "-100 cool", "0", "+100 warm", _signed_value),
            ("Tint", "Green to magenta color bias", "_adj_tint",
             "-100 green", "0", "+100 magenta", _signed_value),
            ("Exposure", "Overall brightness", "_adj_exposure",
             "-2 EV", "0", "+2 EV", _exposure_value),
            ("Highlights", "Bright-tone lift or recover", "_adj_highlights",
             "-100 recover", "0", "+100 bright", _signed_value),
            ("Shadows", "Dark-tone lift or crush", "_adj_shadows",
             "-100 crush", "0", "+100 lift", _signed_value),
            ("Saturation", "Color intensity", "_adj_saturation",
             "0x gray", "1x", "2x vivid", _saturation_value),
        ]
        self._adj_sliders: dict = {}

        no_pil_tip = "Install Pillow for live adjustments (pip install pillow)"

        for label, tooltip, attr, low, mid, high, formatter in adj_specs:
            control = AdjustmentControl(
                label, low, mid, high, tooltip, formatter, parent=grp
            )
            control.setControlEnabled(HAS_PIL, no_pil_tip)

            def _make_handler(a):
                def _handler(v):
                    setattr(self, a, v)
                    self._schedule_canvas_refresh()
                return _handler

            control.valueChanged.connect(_make_handler(attr))
            self._adj_sliders[attr] = control
            content_lay.addWidget(control)

        vlay.addWidget(content)
        return grp

    def _make_frame_group(self) -> QWidget:
        grp = QWidget()
        grp.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(grp)
        vlay.setContentsMargins(10, 8, 10, 10)
        vlay.setSpacing(6)

        # Collapsible content container
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content.hide()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(6)

        # Header row
        head_row = QHBoxLayout()
        head_row.setSpacing(6)

        chevron = QPushButton("▶")
        chevron.setFixedSize(18, 18)
        chevron.setFont(_uf(9))
        chevron.setFlat(True)
        chevron.setStyleSheet("background: transparent; border: none; padding: 0;")
        chevron.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(chevron)

        head = QLabel("Frame presets")
        head.setFont(_uf(10, 600))
        head.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;")
        _on_theme(lambda: head.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;"))
        head.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(head)
        head_row.addStretch()
        vlay.addLayout(head_row)

        def _toggle_frame():
            expanded = content.isVisible()
            content.setVisible(not expanded)
            chevron.setText("▶" if expanded else "▼")

        chevron.clicked.connect(_toggle_frame)
        head.mousePressEvent = lambda _e: _toggle_frame()

        # Preset chips — 2 columns
        self._preset_chips: dict = {}
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (key, label, dims, _w, _h) in enumerate(PRESETS):
            chip = PresetChip(key, label, dims)
            chip.setActive(key == self._active_preset)
            chip.selected.connect(self._apply_preset)
            self._preset_chips[key] = chip
            grid.addWidget(chip, i // 2, i % 2)
        content_lay.addLayout(grid)

        # Width / height inputs
        dim_row = QHBoxLayout()
        dim_row.setSpacing(6)
        w_lbl = QLabel("W")
        w_lbl.setFont(_uf(10))
        w_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: w_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        dim_row.addWidget(w_lbl)
        self._w_input = QLineEdit(self._width_mm)
        self._w_input.setFixedWidth(46)
        self._w_input.setFixedHeight(24)
        self._w_input.setFont(_mf(10))
        self._w_input.setToolTip("Print width in millimetres")
        _wire_validator(self._w_input, QDoubleValidator(0.1, 9999.0, 2))
        self._w_input.textChanged.connect(self._on_w_changed)
        dim_row.addWidget(self._w_input)
        dim_row.addSpacing(4)
        h_lbl = QLabel("H")
        h_lbl.setFont(_uf(10))
        h_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: h_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        dim_row.addWidget(h_lbl)
        self._h_input = QLineEdit(self._height_mm)
        self._h_input.setFixedWidth(46)
        self._h_input.setFixedHeight(24)
        self._h_input.setFont(_mf(10))
        self._h_input.setToolTip("Print height in millimetres (leave blank to derive from width + aspect ratio)")
        _wire_validator(self._h_input, QDoubleValidator(0.1, 9999.0, 2))
        self._h_input.textChanged.connect(self._on_h_changed)
        dim_row.addWidget(self._h_input)
        unit_lbl = QLabel("mm")
        unit_lbl.setFont(_uf(10))
        unit_lbl.setStyleSheet(f"color: {T['dim']}; background: transparent;")
        _on_theme(lambda: unit_lbl.setStyleSheet(f"color: {T['dim']}; background: transparent;"))
        dim_row.addWidget(unit_lbl)
        dim_row.addStretch()

        content_lay.addLayout(dim_row)

        # Lock toggle on its own row
        lock_row = QHBoxLayout()
        lock_row.setSpacing(6)
        lock_lbl = QLabel("Lock ratio")
        lock_lbl.setFont(_uf(10))
        lock_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: lock_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        self._lock_switch = ToggleSwitch(self._lock_ratio)
        self._lock_switch.toggled.connect(self._on_lock_toggled)
        lock_row.addWidget(lock_lbl)
        lock_row.addStretch()
        lock_row.addWidget(self._lock_switch)
        content_lay.addLayout(lock_row)

        vlay.addWidget(content)
        return grp

    def _make_engine_group(self) -> QWidget:
        grp = QWidget()
        grp.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(grp)
        vlay.setContentsMargins(10, 8, 10, 10)
        vlay.setSpacing(6)

        # Collapsible content container
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content.hide()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(6)

        # Header row
        head_row = QHBoxLayout()
        head_row.setSpacing(6)

        chevron = QPushButton("▶")
        chevron.setFixedSize(18, 18)
        chevron.setFont(_uf(9))
        chevron.setFlat(True)
        chevron.setStyleSheet("background: transparent; border: none; padding: 0;")
        chevron.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(chevron)

        head = QLabel("Engine")
        head.setFont(_uf(10, 600))
        head.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;")
        _on_theme(lambda: head.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;"))
        head.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(head)
        head_row.addStretch()
        vlay.addLayout(head_row)

        def _toggle_engine():
            expanded = content.isVisible()
            content.setVisible(not expanded)
            chevron.setText("▶" if expanded else "▼")

        chevron.clicked.connect(_toggle_engine)
        head.mousePressEvent = lambda _e: _toggle_engine()

        # Layer height chips
        lh_lbl = QLabel("Layer height")
        lh_lbl.setFont(_uf(10))
        lh_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: lh_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        content_lay.addWidget(lh_lbl)
        lh_row = QHBoxLayout()
        lh_row.setSpacing(4)
        self._layer_chips: dict = {}
        for key, label, hint in LAYER_HEIGHTS:
            chip = LayerChip(key, label, hint)
            chip.setActive(key == self._active_layer_h)
            chip.selected.connect(self._apply_layer_height)
            self._layer_chips[key] = chip
            lh_row.addWidget(chip)
        lh_row.addStretch()
        content_lay.addLayout(lh_row)
        vlay.addWidget(content)
        return grp

    def _make_resolution_group(self) -> QWidget:
        grp = QWidget()
        grp.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(grp)
        vlay.setContentsMargins(10, 8, 10, 10)
        vlay.setSpacing(6)

        # Collapsible content container
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content.hide()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(6)

        # Header row
        head_row = QHBoxLayout()
        head_row.setSpacing(6)

        chevron = QPushButton("▶")
        chevron.setFixedSize(18, 18)
        chevron.setFont(_uf(9))
        chevron.setFlat(True)
        chevron.setStyleSheet("background: transparent; border: none; padding: 0;")
        chevron.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(chevron)

        head = QLabel("Print settings")
        head.setFont(_uf(10, 600))
        head.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;")
        _on_theme(lambda: head.setStyleSheet(f"color: {T['mid']}; letter-spacing: 0.12em; background: transparent;"))
        head.setCursor(Qt.CursorShape.PointingHandCursor)
        head_row.addWidget(head)
        head_row.addStretch()
        reset_btn = QPushButton("Reset defaults")
        reset_btn.setFixedHeight(18)
        reset_btn.setFont(_uf(9))
        reset_btn.setToolTip("Restore print settings to the recommended defaults")
        reset_btn.clicked.connect(self._reset_print_defaults)
        head_row.addWidget(reset_btn)
        vlay.addLayout(head_row)

        def _toggle_print():
            expanded = content.isVisible()
            content.setVisible(not expanded)
            chevron.setText("▶" if expanded else "▼")

        chevron.clicked.connect(_toggle_print)
        head.mousePressEvent = lambda _e: _toggle_print()

        self._profile_chips: dict = {}
        profile_lbl = QLabel("Profile:  High Quality Lithophane")
        profile_lbl.setFont(_uf(11))
        profile_lbl.setStyleSheet(f"color: {T['ink']}; background: transparent;")
        _on_theme(lambda: profile_lbl.setStyleSheet(f"color: {T['ink']}; background: transparent;"))
        content_lay.addWidget(profile_lbl)

        litho_mode_lbl = QLabel("Litho type")
        litho_mode_lbl.setFont(_uf(11))
        litho_mode_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: litho_mode_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        content_lay.addWidget(litho_mode_lbl)

        litho_mode_row = QHBoxLayout()
        litho_mode_row.setSpacing(6)
        self._litho_mode_chips: dict = {}
        for key, label, hint in LITHO_MODES:
            chip = LayerChip(key, label, hint, width=68)
            chip.setActive(key == self._current_litho_mode())
            chip.selected.connect(self._set_litho_mode)
            self._litho_mode_chips[key] = chip
            litho_mode_row.addWidget(chip)
        litho_mode_row.addStretch()
        content_lay.addLayout(litho_mode_row)

        quality_lbl = QLabel("Quality")
        quality_lbl.setFont(_uf(11))
        quality_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: quality_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        content_lay.addWidget(quality_lbl)

        quality_row = QHBoxLayout()
        quality_row.setSpacing(6)
        self._quality_chips: dict = {}
        for key, label, hint, _color_px, _tex_px, _cap in QUALITY_PRESETS:
            chip = LayerChip(key, "Bal" if key == "balanced" else label, hint)
            chip.setActive(key == self._active_quality)
            chip.selected.connect(self._apply_quality_preset)
            self._quality_chips[key] = chip
            quality_row.addWidget(chip)
        quality_row.addStretch()
        content_lay.addLayout(quality_row)

        def _field(target_layout, lbl_text, val) -> QLineEdit:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(lbl_text)
            lbl.setFont(_uf(10))
            lbl.setMinimumWidth(0)
            lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
            _on_theme(lambda: lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
            inp = QLineEdit(val)
            inp.setFont(_mf(10))
            inp.setFixedSize(54, 24)
            row.addWidget(lbl)
            row.addWidget(inp)
            row.addStretch()
            target_layout.addLayout(row)
            return inp

        self._color_px_input = _field(content_lay, "Color pixel size", self._color_px_w)
        self._color_px_input.setToolTip(
            "Width of one colour pixel in mm.\n"
            "Smaller = finer colour detail; must be ≥ your nozzle diameter."
        )
        _wire_validator(self._color_px_input, QDoubleValidator(0.01, 10.0, 3))
        def _on_color_px_changed(v: str) -> None:
            self._color_px_w = v
            if not getattr(self, "_updating_quality_fields", False):
                self._active_quality = "custom"
                self._sync_quality_chips()
            self._schedule_color_preview_refresh()
            self._update_setting_warnings()
        self._color_px_input.textChanged.connect(_on_color_px_changed)

        self._tex_px_input = _field(content_lay, "Texture pixel size", self._tex_px_w)
        self._tex_px_input.setToolTip(
            "Width of one texture pixel in mm.\n"
            "Controls the surface relief resolution."
        )
        _wire_validator(self._tex_px_input, QDoubleValidator(0.01, 10.0, 3))
        def _on_tex_px_changed(v: str) -> None:
            self._tex_px_w = v
            if not getattr(self, "_updating_quality_fields", False):
                self._active_quality = "custom"
                self._sync_quality_chips()
            self._update_setting_warnings()
        self._tex_px_input.textChanged.connect(_on_tex_px_changed)

        self._layer_thick_input = _field(content_lay, "Layer height", self._layer_thick)
        self._layer_thick_input.setToolTip(
            "Thickness of each colour / backing layer in mm.\n"
            "Should match your slicer layer height (e.g. 0.10 or 0.20).\n\n"
            "Note: the texture is exported as a continuous mesh, not stepped\n"
            "layers. You can apply variable layer height in your slicer\n"
            "(e.g. 0.04 mm on top of a 0.10 mm base) to print a finer\n"
            "surface finish without regenerating the STL."
        )
        _wire_validator(self._layer_thick_input, QDoubleValidator(0.01, 1.0, 3))
        def _on_layer_thick_changed(v: str) -> None:
            self._layer_thick = v
            self._update_z_stat()
            self._update_setting_warnings()
        self._layer_thick_input.textChanged.connect(_on_layer_thick_changed)

        self._layer_count_input = _field(content_lay, "Color layers", self._layer_count)
        self._layer_count_input.setToolTip(
            "Number of colour layers to generate.\n"
            "5 matches the PIXEstL default and the measured palette depth."
        )
        _wire_validator(self._layer_count_input, QIntValidator(1, 99))
        def _on_layer_count_changed(v: str) -> None:
            self._layer_count = v
            self._schedule_color_preview_refresh()
            self._update_z_stat()
            self._update_setting_warnings()
        self._layer_count_input.textChanged.connect(_on_layer_count_changed)

        self._border_input = _field(content_lay, "Border", self._border_mm)
        self._border_input.setToolTip(
            "Width of the solid border added around the print in mm.\n"
            "Set to 0 for no border."
        )
        _wire_validator(self._border_input, QDoubleValidator(0.0, 50.0, 2))
        def _on_border_changed(v: str) -> None:
            self._border_mm = v
            self._refresh_border_preview()
            self._schedule_color_preview_refresh()
            self._update_setting_warnings()
        self._border_input.textChanged.connect(_on_border_changed)

        self._settings_warning_label = QLabel("")
        self._settings_warning_label.setWordWrap(True)
        self._settings_warning_label.setFont(_uf(10))
        self._settings_warning_label.setStyleSheet(
            f"color: {T['warn']}; background: transparent;"
        )
        _on_theme(lambda: self._settings_warning_label.setStyleSheet(
            f"color: {T['warn']}; background: transparent;"
        ))
        self._settings_warning_label.hide()
        content_lay.addWidget(self._settings_warning_label)

        adv_toggle = QPushButton("Show advanced")
        adv_toggle.setCheckable(True)
        adv_toggle.setFixedHeight(28)
        adv_toggle.setFont(_uf(11, 500))
        content_lay.addWidget(adv_toggle)
        self._advanced_toggle = adv_toggle

        adv = QWidget()
        adv.setStyleSheet("background: transparent;")
        adv_lay = QVBoxLayout(adv)
        adv_lay.setContentsMargins(0, 0, 0, 0)
        adv_lay.setSpacing(10)
        adv.hide()
        self._advanced_settings_widget = adv

        def _toggle_advanced(checked: bool) -> None:
            adv.setVisible(checked)
            adv_toggle.setText("Hide advanced" if checked else "Show advanced")
        adv_toggle.clicked.connect(_toggle_advanced)

        self._backing_input = _field(adv_lay, "Backing layers", self._backing_layers)
        self._backing_input.setToolTip(
            "Number of solid backing layers behind the colour stack.\n"
            "Total backing thickness = backing layers × layer thickness.\n"
            "2 layers (default) ≈ 0.20 mm at a 0.10 mm layer height."
        )
        _wire_validator(self._backing_input, QIntValidator(0, 99))
        def _on_backing_changed(v: str) -> None:
            self._backing_layers = v
            self._update_z_stat()
            self._update_setting_warnings()
        self._backing_input.textChanged.connect(_on_backing_changed)

        self._tex_min_input = _field(adv_lay, "Texture min", self._texture_min_layers)
        self._tex_min_input.setToolTip(
            "Minimum texture layers (relief floor at the brightest pixels).\n"
            "Total floor = texture min × layer thickness.\n"
            "3 layers (default) ≈ 0.30 mm at a 0.10 mm layer height."
        )
        _wire_validator(self._tex_min_input, QIntValidator(0, 999))
        def _on_tex_min_changed(v: str) -> None:
            self._texture_min_layers = v
            self._update_z_stat()
            self._update_setting_warnings()
        self._tex_min_input.textChanged.connect(_on_tex_min_changed)

        self._tex_max_input = _field(adv_lay, "Texture max", self._texture_max_layers)
        self._tex_max_input.setToolTip(
            "Maximum texture layers (relief ceiling at the darkest pixels).\n"
            "Total relief height = texture max × layer thickness.\n"
            "15 layers (default) ≈ 1.50 mm at a 0.10 mm layer height."
        )
        _wire_validator(self._tex_max_input, QIntValidator(0, 999))
        def _on_tex_max_changed(v: str) -> None:
            self._texture_max_layers = v
            self._update_z_stat()
            self._update_setting_warnings()
        self._tex_max_input.textChanged.connect(_on_tex_max_changed)

        self._fine_layer_input = _field(adv_lay, "Bambu texture layer", self._fine_layer_h)
        self._fine_layer_input.setToolTip(
            "Bambu .3mf height-range layer height for the texture region.\n"
            "0.04 mm is the typical value Bambu's lithophane maker uses.\n"
            "Set to match your nominal layer height to disable fine-layer behavior."
        )
        _wire_validator(self._fine_layer_input, QDoubleValidator(0.01, 1.0, 3))
        def _on_fine_layer_changed(v: str) -> None:
            self._fine_layer_h = v
            self._update_setting_warnings()
        self._fine_layer_input.textChanged.connect(_on_fine_layer_changed)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_lbl = QLabel("Pixel mode")
        mode_lbl.setFont(_uf(11))
        mode_lbl.setFixedWidth(148)
        mode_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: mode_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        self._pixel_mode_combo = QComboBox()
        self._pixel_mode_combo.addItems(["ADDITIVE", "FULL"])
        self._pixel_mode_combo.setCurrentText(self._pixel_mode)
        self._pixel_mode_combo.setFixedHeight(32)
        self._pixel_mode_combo.currentTextChanged.connect(self._on_pixel_mode_changed)
        mode_row.addWidget(mode_lbl)
        mode_row.addWidget(self._pixel_mode_combo)
        mode_row.addStretch()
        adv_lay.addLayout(mode_row)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        output_lbl = QLabel("Output")
        output_lbl.setFont(_uf(11))
        output_lbl.setFixedWidth(148)
        output_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: output_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        self._output_mode_combo = QComboBox()
        self._output_mode_combo.addItem("Color litho", "both")
        self._output_mode_combo.addItem("Color only", "color_only")
        self._output_mode_combo.addItem("Single color litho", "texture_only")
        self._set_combo_data(self._output_mode_combo, self._output_mode)
        self._output_mode_combo.setFixedHeight(32)
        self._output_mode_combo.currentIndexChanged.connect(
            lambda _i: self._on_output_mode_changed(self._output_mode_combo.currentData())
        )
        output_row.addWidget(output_lbl)
        output_row.addWidget(self._output_mode_combo)
        output_row.addStretch()
        adv_lay.addLayout(output_row)

        distance_row = QHBoxLayout()
        distance_row.setSpacing(8)
        distance_lbl = QLabel("Color distance")
        distance_lbl.setFont(_uf(11))
        distance_lbl.setFixedWidth(148)
        distance_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: distance_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        self._distance_combo = QComboBox()
        self._distance_combo.addItems(["CIELab", "RGB"])
        self._distance_combo.setCurrentText(self._distance_method)
        self._distance_combo.setFixedHeight(32)
        self._distance_combo.currentTextChanged.connect(self._on_distance_changed)
        distance_row.addWidget(distance_lbl)
        distance_row.addWidget(self._distance_combo)
        distance_row.addStretch()
        adv_lay.addLayout(distance_row)

        self._color_number_input = _field(adv_lay, "Max colors/layer", self._color_number)
        self._color_number_input.setPlaceholderText("none")
        self._color_number_input.setToolTip("PIXEstL -c. Leave blank for no per-layer color limit.")
        _wire_validator(self._color_number_input, QIntValidator(1, 99))
        self._color_number_input.textChanged.connect(self._on_color_number_changed)

        self._curve_input = _field(adv_lay, "Curve", self._curve)
        self._curve_input.setPlaceholderText("none")
        self._curve_input.setToolTip("PIXEstL -C curve parameter. Leave blank for no curve.")
        _wire_validator(self._curve_input, QDoubleValidator(-9999.0, 9999.0, 4))
        self._curve_input.textChanged.connect(lambda v: setattr(self, "_curve", v))

        low_mem_row = QHBoxLayout()
        low_mem_row.setSpacing(8)
        low_mem_lbl = QLabel("Low memory")
        low_mem_lbl.setFont(_uf(11))
        low_mem_lbl.setFixedWidth(148)
        low_mem_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
        _on_theme(lambda: low_mem_lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
        self._low_memory_switch = ToggleSwitch(self._low_memory)
        self._low_memory_switch.setToolTip("PIXEstL -Y. Uses temp files to reduce memory pressure.")
        self._low_memory_switch.toggled.connect(self._on_low_memory_changed)
        low_mem_row.addWidget(low_mem_lbl)
        low_mem_row.addWidget(self._low_memory_switch)
        low_mem_row.addStretch()
        adv_lay.addLayout(low_mem_row)

        self._layer_threads_input = _field(adv_lay, "Layer threads", self._layer_threads)
        self._layer_threads_input.setPlaceholderText("JAR")
        self._layer_threads_input.setToolTip("PIXEstL -n. Blank uses the bundled JAR default.")
        _wire_validator(self._layer_threads_input, QIntValidator(1, 999))
        self._layer_threads_input.textChanged.connect(lambda v: setattr(self, "_layer_threads", v))

        self._row_threads_input = _field(adv_lay, "Row threads", self._row_threads)
        self._row_threads_input.setPlaceholderText("JAR")
        self._row_threads_input.setToolTip("PIXEstL -N. Blank uses the bundled JAR default.")
        _wire_validator(self._row_threads_input, QIntValidator(1, 999))
        self._row_threads_input.textChanged.connect(lambda v: setattr(self, "_row_threads", v))

        self._layer_timeout_input = _field(adv_lay, "Layer timeout", self._layer_timeout)
        self._layer_timeout_input.setPlaceholderText("JAR")
        self._layer_timeout_input.setToolTip("PIXEstL -t in seconds. Blank uses the bundled JAR default.")
        _wire_validator(self._layer_timeout_input, QIntValidator(1, 999999))
        self._layer_timeout_input.textChanged.connect(lambda v: setattr(self, "_layer_timeout", v))

        self._row_timeout_input = _field(adv_lay, "Row timeout", self._row_timeout)
        self._row_timeout_input.setPlaceholderText("JAR")
        self._row_timeout_input.setToolTip("PIXEstL -T in seconds. Blank uses the bundled JAR default.")
        _wire_validator(self._row_timeout_input, QIntValidator(1, 999999))
        self._row_timeout_input.textChanged.connect(lambda v: setattr(self, "_row_timeout", v))

        content_lay.addWidget(adv)
        vlay.addWidget(content)
        self._update_setting_warnings()
        return grp

    def _build_center(self) -> QWidget:
        col = QWidget()
        col.setStyleSheet(f"background: {T['bg']};")
        _on_theme(lambda: col.setStyleSheet(f"background: {T['bg']};"))
        vlay = QVBoxLayout(col)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        head = PanelHead("Crop & preview")
        vlay.addWidget(head)

        self._canvas = PreviewCanvas()
        self._canvas.image_dropped.connect(self._set_image_path)
        self._canvas.crop_changed.connect(self._on_crop_changed)

        self._source_preview_panel = JarPreviewPanel(
            "CROPPED SOURCE",
            "Adjust the crop to preview the source image",
        )
        self._jar_panel = JarPreviewPanel()
        if not (HAS_PIL and HAS_NUMPY):
            self._jar_panel.set_empty_text(
                "Install Pillow + NumPy for live print preview"
            )

        preview_split = QSplitter(Qt.Orientation.Vertical)
        preview_split.addWidget(self._source_preview_panel)
        preview_split.addWidget(self._jar_panel)
        preview_split.setStretchFactor(0, 1)
        preview_split.setStretchFactor(1, 1)
        preview_split.setChildrenCollapsible(False)
        preview_split.setHandleWidth(1)
        preview_split.setStyleSheet(
            f"QSplitter::handle {{ background: {T['line_2']}; }}"
        )
        _on_theme(lambda s=preview_split: s.setStyleSheet(
            f"QSplitter::handle {{ background: {T['line_2']}; }}"
        ))

        stage_split = QSplitter(Qt.Orientation.Horizontal)
        stage_split.addWidget(self._canvas)
        stage_split.addWidget(preview_split)
        stage_split.setStretchFactor(0, 1)
        stage_split.setStretchFactor(1, 1)
        stage_split.setChildrenCollapsible(False)
        stage_split.setHandleWidth(1)
        stage_split.setStyleSheet(
            f"QSplitter::handle {{ background: {T['line_2']}; }}"
        )
        _on_theme(lambda s=stage_split: s.setStyleSheet(
            f"QSplitter::handle {{ background: {T['line_2']}; }}"
        ))
        self._stage_split = stage_split
        vlay.addWidget(stage_split, 1)

        def _init_stage_split_sizes(s=stage_split):
            half = s.width() // 2
            if half > 0:
                s.setSizes([half, half])
        QTimer.singleShot(0, _init_stage_split_sizes)

        # Stage footer
        stage_foot = QWidget()
        stage_foot.setFixedHeight(44)
        stage_foot.setStyleSheet(f"background: {T['panel']}; border-top: 1px solid {T['line_2']};")
        _on_theme(lambda: stage_foot.setStyleSheet(f"background: {T['panel']}; border-top: 1px solid {T['line_2']};"))
        sf_lay = QHBoxLayout(stage_foot)
        sf_lay.setContentsMargins(16, 0, 16, 0)
        sf_lay.setSpacing(16)

        self._stat_labels: dict = {}
        for key, init in (("res", "—"), ("size", "—"), ("crop", "—"), ("z", "—")):
            lbl = QLabel(f"{key.upper()}: {init}")
            lbl.setFont(_mf(10))
            lbl.setStyleSheet(f"color: {T['mid']}; background: transparent;")
            _on_theme(lambda l=lbl: l.setStyleSheet(f"color: {T['mid']}; background: transparent;"))
            self._stat_labels[key] = lbl
            sf_lay.addWidget(lbl)

        sf_lay.addStretch()

        vlay.addWidget(stage_foot)
        return col

    def _build_right(self) -> QWidget:
        col = QWidget()
        col.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda: col.setStyleSheet(f"background: {T['panel']};"))
        col.setMinimumWidth(self._RIGHT_PANE_MIN)
        vlay = QVBoxLayout(col)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        head = PanelHead("Filaments")

        # All on/off and add buttons in head
        on_btn  = QPushButton("All on")
        off_btn = QPushButton("All off")
        add_btn = QPushButton("+ Add")
        self._all_on_btn = on_btn
        self._all_off_btn = off_btn
        on_btn.setFixedHeight(24)
        off_btn.setFixedHeight(24)
        add_btn.setFixedHeight(24)
        on_btn.setFont(_uf(11))
        off_btn.setFont(_uf(11))
        add_btn.setFont(_uf(11))
        on_btn.clicked.connect(lambda: self._set_all(True))
        off_btn.clicked.connect(lambda: self._set_all(False))
        add_btn.clicked.connect(self._add_new_color)
        head.add_right(on_btn)
        head.add_right(off_btn)
        head.add_right(add_btn)
        vlay.addWidget(head)

        # Filter input
        filter_row = QWidget()
        filter_row.setFixedHeight(40)
        filter_row.setStyleSheet(f"background: {T['panel']}; border-bottom: 1px solid {T['line_2']};")
        _on_theme(lambda: filter_row.setStyleSheet(f"background: {T['panel']}; border-bottom: 1px solid {T['line_2']};"))
        fl = QHBoxLayout(filter_row)
        fl.setContentsMargins(12, 4, 12, 4)
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Filter filaments…")
        self._filter_input.setFont(_uf(12))
        self._filter_input.setFixedHeight(30)
        self._filter_input.textChanged.connect(self._filter_filaments)
        fl.addWidget(self._filter_input)
        vlay.addWidget(filter_row)

        self._hex_only_btn = QPushButton("Show hex-only filaments")
        self._hex_only_btn.setCheckable(True)
        self._hex_only_btn.setChecked(self._show_hex_only)
        self._hex_only_btn.setFixedHeight(30)
        self._hex_only_btn.setFont(_uf(11, 500))
        self._hex_only_btn.setToolTip(
            "Hex-only palette entries are ignored by ADDITIVE mode unless they have measured layer data."
        )
        self._hex_only_btn.clicked.connect(self._toggle_hex_only_filaments)
        vlay.addWidget(self._hex_only_btn)

        # Scrollable filament list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {T['panel_2']};")
        _on_theme(lambda: scroll.setStyleSheet(f"background: {T['panel_2']};"))

        self._filament_container = QWidget()
        self._filament_container.setStyleSheet(f"background: {T['panel_2']};")
        _on_theme(lambda: self._filament_container.setStyleSheet(f"background: {T['panel_2']};"))
        self._filament_layout = QVBoxLayout(self._filament_container)
        self._filament_layout.setContentsMargins(0, 0, 0, 0)
        self._filament_layout.setSpacing(0)
        self._filament_layout.addStretch()

        scroll.setWidget(self._filament_container)
        vlay.addWidget(scroll, 1)

        # Count label
        self._filament_count_lbl = QLabel("0 filaments")
        self._filament_count_lbl.setFont(_uf(10))
        self._filament_count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._filament_count_lbl.setFixedHeight(28)
        self._filament_count_lbl.setStyleSheet(f"color: {T['dim']}; background: {T['panel']}; border-top: 1px solid {T['line_2']};")
        _on_theme(lambda: self._filament_count_lbl.setStyleSheet(f"color: {T['dim']}; background: {T['panel']}; border-top: 1px solid {T['line_2']};"))
        vlay.addWidget(self._filament_count_lbl)

        self._right_content = col
        self._right_tab = DrawerTab("Filaments", side="right")

        outer = QWidget()
        outer.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda w=outer: w.setStyleSheet(f"background: {T['panel']};"))
        olay = QHBoxLayout(outer)
        olay.setContentsMargins(0, 0, 0, 0)
        olay.setSpacing(0)
        olay.addWidget(self._right_tab)
        olay.addWidget(col, 1)
        return outer

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        foot.setFixedHeight(56)
        foot.setStyleSheet(f"background: {T['panel']};")
        _on_theme(lambda: foot.setStyleSheet(f"background: {T['panel']};"))
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(10)

        open_btn = QPushButton("Open output folder")
        open_btn.setFont(_uf(12, 500))
        open_btn.setFixedHeight(36)
        open_btn.clicked.connect(self._open_output_folder)
        lay.addWidget(open_btn)

        help_btn = QPushButton("Engine help")
        help_btn.setFont(_uf(12, 500))
        help_btn.setFixedHeight(36)
        help_btn.clicked.connect(self._show_engine_help)
        lay.addWidget(help_btn)

        lay.addStretch()

        # Console toggle
        self._console_visible = False
        console_btn = QPushButton("Console")
        console_btn.setFont(_uf(12, 500))
        console_btn.setFixedHeight(36)
        console_btn.setCheckable(True)
        console_btn.clicked.connect(self._toggle_console)
        lay.addWidget(console_btn)
        self._console_btn = console_btn

        lay.addWidget(_vline())

        self._run_btn = QPushButton("  Generate STL  ")
        self._run_btn.setFont(_uf(13, 600))
        self._run_btn.setFixedHeight(38)
        self._run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {T['ink']};
                color: {T['on_ink']};
                border: none;
                border-radius: 6px;
                padding: 0 20px;
            }}
            QPushButton:hover {{ background: {T['ink_2']}; }}
            QPushButton:disabled {{ background: {T['dim']}; color: {T['bg']}; }}
        """)
        _on_theme(lambda: self._run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {T['ink']};
                color: {T['on_ink']};
                border: none;
                border-radius: 6px;
                padding: 0 20px;
            }}
            QPushButton:hover {{ background: {T['ink_2']}; }}
            QPushButton:disabled {{ background: {T['dim']}; color: {T['bg']}; }}
        """))
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._on_run_btn_clicked)
        lay.addWidget(self._run_btn)

        # Console (overlay above footer)
        self._console = ConsoleWidget()
        self._console.setFixedHeight(200)
        self._console.hide()
        self._console_widget = self._console

        return foot

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        _settings.setValue("window_geometry", self.saveGeometry())
        splitter = getattr(self, "_main_splitter", None)
        if splitter is not None:
            sizes = splitter.sizes()
            if len(sizes) == 3:
                if sizes[0] > 0:
                    self._left_pane_last_width = sizes[0]
                if sizes[2] > 0:
                    self._right_pane_last_width = sizes[2]
                _settings.setValue("left_pane_visible", sizes[0] > 0)
                _settings.setValue("right_pane_visible", sizes[2] > 0)
            _settings.setValue("left_pane_last_width", self._left_pane_last_width)
            _settings.setValue("right_pane_last_width", self._right_pane_last_width)
            _settings.setValue("main_splitter_state", splitter.saveState())
        if self._proc is not None:
            self._proc.terminate()
        super().closeEvent(event)

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _on_theme_changed(self):
        self.update()

    # ── Console ───────────────────────────────────────────────────────────────
    def _toggle_console(self, checked: bool):
        self._console_visible = checked
        if checked:
            self._console.show()
            self._console.raise_()
        else:
            self._console.hide()

    def _log(self, msg: str, tag: str = "") -> None:
        QMetaObject.invokeMethod(
            self, "_do_log",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, msg),
            Q_ARG(str, tag),
        )

    @staticmethod
    def _qt_slot_log():
        pass

    def _do_log(self, msg: str, tag: str):
        self._console.append_msg(msg, tag)
        if not self._console_visible:
            self._console_btn.setChecked(True)
            self._toggle_console(True)

    # Expose as Qt slot
    from PySide6.QtCore import Slot
    _do_log = Slot(str, str)(_do_log)

    # ── Image browse ──────────────────────────────────────────────────────────
    def _browse_image(self) -> None:
        start_dir = _settings.value("last_image_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", start_dir,
            "Image files (*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tiff);;All files (*.*)"
        )
        if not path:
            return
        _settings.setValue("last_image_dir", os.path.dirname(path))
        self._set_image_path(path)

    def _set_image_path(self, path: str) -> None:
        self._image_path = path
        self._rotation = 0
        self._load_image(path)
        self._run_btn.setEnabled(True)
        if hasattr(self, "_gen_btn_top"):
            self._gen_btn_top.setEnabled(True)
        self._refresh_border_preview()
        self._schedule_color_preview_refresh(delay_ms=50)

    def _load_image(self, path: str) -> None:
        if HAS_PIL:
            try:
                img = Image.open(path)
                self._image_size_orig = (img.width, img.height)
                self._image_size      = (img.width, img.height)
                self._image_aspect    = img.width / img.height
                self._source_card.set_image(path, self._image_size)
                self._stat_labels["res"].setText(f"RES: {img.width} × {img.height} px")
            except Exception:
                pass
        else:
            from PySide6.QtGui import QImageReader
            reader = QImageReader(path)
            sz = reader.size()
            if sz.isValid():
                self._image_size_orig = (sz.width(), sz.height())
                self._image_size      = (sz.width(), sz.height())
                self._image_aspect    = sz.width() / sz.height()
                self._source_card.set_image(path, self._image_size)
                self._stat_labels["res"].setText(f"RES: {sz.width()} × {sz.height()} px")

        self._refresh_canvas_with_adjustments(preserve_crop=False)
        self._stat_labels["size"].setText(f"SIZE: {self._width_mm} × {self._height_mm} mm")

    # ── Rotation & Adjustments ────────────────────────────────────────────────

    def _apply_adjustments(self, img):
        """Apply all image-tool adjustments to a PIL RGB Image. Returns PIL Image."""
        if not HAS_PIL:
            return img
        all_zero = (
            self._adj_color_temp == 0 and self._adj_tint == 0 and
            self._adj_exposure == 0 and self._adj_highlights == 0 and
            self._adj_shadows == 0 and self._adj_saturation == 0
        )
        if all_zero:
            return img

        temp = self._adj_color_temp
        if temp != 0:
            r, g, b = img.split()
            if temp > 0:
                r = r.point(lambda x: min(255, x + int(temp * 0.8)))
                b = b.point(lambda x: max(0, x - int(temp * 0.5)))
            else:
                b = b.point(lambda x: min(255, x + int(-temp * 0.8)))
                r = r.point(lambda x: max(0, x - int(-temp * 0.5)))
            img = Image.merge("RGB", (r, g, b))

        tint = self._adj_tint
        if tint != 0:
            r, g, b = img.split()
            if tint > 0:
                r = r.point(lambda x: min(255, x + int(tint * 0.3)))
                g = g.point(lambda x: max(0, x - int(tint * 0.5)))
                b = b.point(lambda x: min(255, x + int(tint * 0.3)))
            else:
                g = g.point(lambda x: min(255, x + int(-tint * 0.5)))
                r = r.point(lambda x: max(0, x - int(-tint * 0.3)))
                b = b.point(lambda x: max(0, x - int(-tint * 0.3)))
            img = Image.merge("RGB", (r, g, b))

        exp = self._adj_exposure
        if exp != 0:
            factor = 2 ** (exp / 100.0 * 2)   # 0.25× – 4×
            img = ImageEnhance.Brightness(img).enhance(factor)

        shadows = self._adj_shadows
        if shadows != 0:
            lut = [
                max(0, min(255, i + int((128 - i) * shadows / 100.0 * 0.5))) if i < 128 else i
                for i in range(256)
            ]
            img = img.point(lut * 3)

        highlights = self._adj_highlights
        if highlights != 0:
            lut = [
                max(0, min(255, i + int((i - 128) * highlights / 100.0 * 0.5))) if i > 128 else i
                for i in range(256)
            ]
            img = img.point(lut * 3)

        sat = self._adj_saturation
        if sat != 0:
            factor = 1.0 + sat / 100.0   # 0× – 2×
            img = ImageEnhance.Color(img).enhance(factor)

        return img

    def _build_adjusted_pixmap(self) -> QPixmap | None:
        """Build a QPixmap from the current image with rotation and adjustments applied."""
        if not self._image_path or not os.path.isfile(self._image_path):
            return None
        if HAS_PIL:
            try:
                with Image.open(self._image_path) as src:
                    img = src.convert("RGB")
                img = self._apply_adjustments(img)
                if self._rotation != 0:
                    img = img.rotate(-self._rotation, expand=True)
                data = img.tobytes("raw", "RGB")
                qimg = QImage(data, img.width, img.height, img.width * 3,
                              QImage.Format.Format_RGB888)
                return QPixmap.fromImage(qimg.copy())
            except Exception:
                pass
        pix = QPixmap(self._image_path)
        if pix.isNull():
            return None
        if self._rotation != 0:
            pix = pix.transformed(QTransform().rotate(self._rotation))
        return pix

    def _refresh_canvas_with_adjustments(
        self,
        preserve_crop: bool = True,
        crop_override=None,
    ) -> None:
        """Rebuild the canvas pixmap from source image + rotation + adjustments."""
        if not self._image_path:
            return
        old_crop = self._canvas.crop()
        old_size = self._image_size
        pix = self._build_adjusted_pixmap()
        if pix is None:
            return
        if self._image_size_orig:
            w, h = self._image_size_orig
            if self._rotation in (90, 270):
                self._image_size  = (h, w)
                self._image_aspect = h / w if w else 1.0
            else:
                self._image_size  = (w, h)
                self._image_aspect = w / h if h else 1.0
        keep_crop = bool(
            crop_override is None and preserve_crop and old_crop and old_size == self._image_size
        )
        self._canvas.set_pixmap(pix, keep_crop=keep_crop)
        if crop_override is not None:
            self._canvas.set_crop(crop_override)
        elif self._canvas.crop():
            self._update_crop_stat()
            self._refresh_source_preview()
        else:
            self._recenter_crop()
        self._schedule_color_preview_refresh(delay_ms=50)

    def _schedule_canvas_refresh(self, delay_ms: int = 120) -> None:
        """Debounced version of _refresh_canvas_with_adjustments for slider drags."""
        timer = getattr(self, "_canvas_refresh_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._refresh_canvas_with_adjustments)
            self._canvas_refresh_timer = timer
        timer.start(delay_ms)

    def _on_rotate(self, direction: int) -> None:
        """Rotate the image by `direction` degrees (positive = CW, negative = CCW).

        The crop frame stays put — only the underlying image rotates inside it.
        The crop is recentered with the user's chosen orientation/aspect afterward.
        """
        self._rotation = (self._rotation + direction) % 360
        self._refresh_canvas_with_adjustments(preserve_crop=False)

    def _set_crop_orientation(self, orientation: str) -> None:
        """Switch between landscape/portrait crop. Swaps W/H so the crop matches."""
        if orientation not in ("landscape", "portrait"):
            return
        self._crop_orientation = orientation
        try:
            w = float(self._width_mm)
            h_raw = self._height_mm.strip()
            h = float(h_raw) if h_raw else w
        except ValueError:
            self._sync_orientation_buttons()
            return

        needs_swap = (
            (orientation == "landscape" and w < h) or
            (orientation == "portrait"  and w > h)
        )
        if needs_swap and w > 0 and h > 0:
            def _fmt(v: float) -> str:
                return str(int(v)) if abs(v - round(v)) < 1e-9 else f"{v:g}"
            self._updating_dims = True
            self._width_mm  = _fmt(h)
            self._height_mm = _fmt(w)
            self._w_input.setText(self._width_mm)
            self._h_input.setText(self._height_mm)
            self._updating_dims = False
            self._update_size_stat()
            self._refresh_border_preview()
            self._schedule_color_preview_refresh()
            self._update_setting_warnings()

        self._sync_orientation_buttons()
        self._recenter_crop()
        if hasattr(self, "_canvas"):
            self._canvas.update()

    def _sync_orientation_buttons(self) -> None:
        """Update the orientation toggle visual state to match current W/H."""
        try:
            w = float(self._width_mm)
            h_raw = self._height_mm.strip()
            h = float(h_raw) if h_raw else w
        except ValueError:
            return
        if w > h:
            self._crop_orientation = "landscape"
        elif h > w:
            self._crop_orientation = "portrait"
        # If equal, leave the previously selected orientation untouched.
        if hasattr(self, "_land_btn") and hasattr(self, "_port_btn"):
            self._land_btn.setChecked(self._crop_orientation == "landscape")
            self._port_btn.setChecked(self._crop_orientation == "portrait")

    def _reset_adjustments(self) -> None:
        """Reset all image-tool sliders to zero."""
        attrs = ["_adj_color_temp", "_adj_tint", "_adj_exposure",
                 "_adj_highlights", "_adj_shadows", "_adj_saturation"]
        for attr in attrs:
            setattr(self, attr, 0)
            control = self._adj_sliders.get(attr)
            if control:
                control.setValue(0)
        self._refresh_canvas_with_adjustments()

    # ── Presets ───────────────────────────────────────────────────────────────
    def _apply_preset(self, key: str) -> None:
        for k, chip in self._preset_chips.items():
            chip.setActive(k == key)
        self._active_preset = key
        for pkey, _label, _dims, w, h in PRESETS:
            if pkey == key:
                # Honor the user's chosen crop orientation when stamping in the preset.
                if self._crop_orientation == "landscape" and w < h:
                    w, h = h, w
                elif self._crop_orientation == "portrait" and w > h:
                    w, h = h, w
                self._updating_dims = True
                self._width_mm  = str(w)
                self._height_mm = str(h)
                self._w_input.setText(str(w))
                self._h_input.setText(str(h))
                self._updating_dims = False
                self._sync_orientation_buttons()
                self._recenter_crop()
                self._canvas.update()
                self._update_size_stat()
                break

    def _apply_layer_height(self, key: str) -> None:
        for k, chip in self._layer_chips.items():
            chip.setActive(k == key)
        self._active_layer_h = key
        self._layer_thick = key
        self._layer_thick_input.setText(key)
        self._update_z_stat()
        self._update_setting_warnings()

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _sync_profile_chips(self) -> None:
        for k, chip in getattr(self, "_profile_chips", {}).items():
            chip.setActive(k == self._active_print_profile)

    def _current_litho_mode(self) -> str:
        return "single" if self._output_mode == "texture_only" else "color"

    def _sync_litho_mode_chips(self) -> None:
        mode = self._current_litho_mode()
        for k, chip in getattr(self, "_litho_mode_chips", {}).items():
            chip.setActive(k == mode)

    def _apply_single_litho_defaults(self) -> None:
        self._active_layer_h = SINGLE_COLOR_LAYER_HEIGHT
        for k, chip in getattr(self, "_layer_chips", {}).items():
            chip.setActive(k == SINGLE_COLOR_LAYER_HEIGHT)
        self._set_text_field(
            "_layer_thick",
            "_layer_thick_input",
            SINGLE_COLOR_LAYER_HEIGHT,
        )
        self._set_text_field(
            "_texture_max_layers",
            "_tex_max_input",
            SINGLE_COLOR_TEXTURE_MAX_LAYERS,
        )
        self._update_z_stat()

    def _set_litho_mode(self, mode: str) -> None:
        self._output_mode = "texture_only" if mode == "single" else "both"
        if hasattr(self, "_output_mode_combo"):
            self._set_combo_data(self._output_mode_combo, self._output_mode)
        if self._current_litho_mode() == "single":
            self._apply_single_litho_defaults()
            self._apply_single_filament_lock()
        else:
            self._restore_color_filament_state()
        self._sync_litho_mode_chips()
        self._sync_filament_controls()
        self._apply_hex_only_visibility()
        self._refresh_source_preview()
        self._schedule_color_preview_refresh(delay_ms=50)
        self._update_z_stat()
        self._update_setting_warnings()

    def _sync_quality_chips(self) -> None:
        for k, chip in getattr(self, "_quality_chips", {}).items():
            chip.setActive(k == self._active_quality)

    def _apply_quality_preset(self, key: str) -> None:
        for pkey, _label, _hint, color_px, tex_px, cap in QUALITY_PRESETS:
            if pkey != key:
                continue
            self._active_quality = key
            self._preview_cell_cap = cap
            self._sync_quality_chips()
            self._updating_quality_fields = True
            self._color_px_w = color_px
            self._tex_px_w = tex_px
            self._color_px_input.setText(color_px)
            self._tex_px_input.setText(tex_px)
            self._updating_quality_fields = False
            self._last_preview_capped = False
            self._last_preview_requested = None
            self._last_preview_actual = None
            self._schedule_color_preview_refresh(delay_ms=50)
            self._update_setting_warnings()
            return

    def _set_text_field(self, attr: str, widget_name: str, value: str) -> None:
        setattr(self, attr, value)
        widget = getattr(self, widget_name, None)
        if widget is not None:
            widget.setText(value)

    def _apply_print_profile(self, key: str) -> None:
        profile = next((p for p in PRINT_PROFILES if p[0] == key), None)
        if profile is None:
            return
        _pkey, _label, _hint, settings = profile
        self._active_print_profile = key
        self._sync_profile_chips()

        quality = settings.get("quality", "")
        if quality:
            self._apply_quality_preset(quality)
        else:
            self._active_quality = "custom"
            self._sync_quality_chips()
            self._set_text_field("_color_px_w", "_color_px_input", settings["color_px"])
            self._set_text_field("_tex_px_w", "_tex_px_input", settings["tex_px"])

        layer_h = settings["layer_height"]
        if hasattr(self, "_layer_chips"):
            for k, chip in self._layer_chips.items():
                chip.setActive(k == layer_h)
        self._active_layer_h = layer_h
        self._set_text_field("_layer_thick", "_layer_thick_input", layer_h)

        field_updates = [
            ("_layer_count", "_layer_count_input", settings["layers"]),
            ("_backing_layers", "_backing_input", settings["backing"]),
            ("_texture_min_layers", "_tex_min_input", settings["tex_min"]),
            ("_texture_max_layers", "_tex_max_input", settings["tex_max"]),
            ("_fine_layer_h", "_fine_layer_input", settings["fine_layer"]),
            ("_border_mm", "_border_input", settings["border"]),
            ("_color_number", "_color_number_input", settings["color_number"]),
            ("_curve", "_curve_input", settings["curve"]),
        ]
        for attr, widget_name, value in field_updates:
            self._set_text_field(attr, widget_name, value)

        self._pixel_mode = settings["pixel_mode"]
        if hasattr(self, "_pixel_mode_combo"):
            self._pixel_mode_combo.setCurrentText(self._pixel_mode)

        self._output_mode = settings["output_mode"]
        if hasattr(self, "_output_mode_combo"):
            self._set_combo_data(self._output_mode_combo, self._output_mode)
        self._sync_litho_mode_chips()

        self._distance_method = settings["distance"]
        if hasattr(self, "_distance_combo"):
            self._distance_combo.setCurrentText(self._distance_method)

        self._refresh_border_preview()
        self._update_z_stat()
        self._schedule_color_preview_refresh(delay_ms=50)
        self._update_setting_warnings()

    def _reset_print_defaults(self) -> None:
        self._low_memory = False
        if hasattr(self, "_low_memory_switch"):
            self._low_memory_switch.setChecked(False)
        for attr, widget_name in [
            ("_layer_threads", "_layer_threads_input"),
            ("_row_threads", "_row_threads_input"),
            ("_layer_timeout", "_layer_timeout_input"),
            ("_row_timeout", "_row_timeout_input"),
        ]:
            self._set_text_field(attr, widget_name, "")
        self._apply_print_profile("litho")

    def _on_pixel_mode_changed(self, mode: str) -> None:
        self._pixel_mode = mode
        self._schedule_color_preview_refresh()
        self._update_setting_warnings()

    def _on_output_mode_changed(self, mode: str) -> None:
        self._output_mode = mode or "both"
        if self._current_litho_mode() == "single":
            self._apply_single_litho_defaults()
            self._apply_single_filament_lock()
        else:
            self._restore_color_filament_state()
        self._sync_litho_mode_chips()
        self._sync_filament_controls()
        self._apply_hex_only_visibility()
        self._refresh_source_preview()
        self._schedule_color_preview_refresh()
        self._update_z_stat()
        self._update_setting_warnings()

    def _on_distance_changed(self, method: str) -> None:
        self._distance_method = method or "CIELab"
        self._schedule_color_preview_refresh()
        self._update_setting_warnings()

    def _on_color_number_changed(self, value: str) -> None:
        self._color_number = value
        self._update_setting_warnings()

    def _on_low_memory_changed(self, enabled: bool) -> None:
        self._low_memory = enabled
        self._update_setting_warnings()

    def _update_setting_warnings(self) -> None:
        label = getattr(self, "_settings_warning_label", None)
        if label is None:
            return
        warnings = []
        color_out, texture_out = self._output_flags()
        try:
            if color_out and int(self._layer_count or "0") > 5:
                warnings.append("Color layers above 5 exceed most measured palette data.")
        except ValueError:
            pass
        try:
            if color_out and float(self._color_px_w or "0") < 0.15:
                warnings.append("Very small color pixels increase STL size and print time.")
        except ValueError:
            pass
        try:
            if texture_out and not color_out and float(self._tex_px_w or "0") < 0.15:
                warnings.append("Very small texture pixels increase STL size and print time.")
        except ValueError:
            pass
        if self._output_mode == "color_only":
            warnings.append("Output mode disables the texture layer (-Z false).")
        elif self._output_mode == "texture_only":
            warnings.append(
                "Single color litho exports texture only at 32 x 0.10 mm = 3.20 mm."
            )
        if color_out and self._color_number.strip():
            warnings.append(f"Color count is limited to {self._color_number.strip()} per layer.")
        if self._low_memory:
            warnings.append("Low-memory mode writes temporary polygon files.")
        if color_out:
            if self._pixel_mode != "ADDITIVE":
                warnings.append("Live color preview is tuned for ADDITIVE mode.")
            elif self.palette_data:
                if not self.color_vars.get("#FFFFFF", False):
                    warnings.append("White must be active for ADDITIVE mode.")
                ignored = 0
                for hx, active in self.color_vars.items():
                    info = self.palette_data.get(hx, {}) or {}
                    if active and not isinstance(info.get("layers"), dict):
                        ignored += 1
                if ignored:
                    warnings.append(f"{ignored} active hex-only filaments ignored in ADDITIVE mode.")
        if self._last_preview_capped and self._last_preview_requested and self._last_preview_actual:
            rw, rh = self._last_preview_requested
            aw, ah = self._last_preview_actual
            warnings.append(f"Preview capped from {rw} x {rh} to {aw} x {ah} cells.")
        label.setText("  |  ".join(warnings))
        label.setVisible(bool(warnings))

    def _on_crop_changed(self, _crop) -> None:
        self._update_crop_stat()
        self._refresh_source_preview()
        self._schedule_color_preview_refresh(delay_ms=120)

    def _refresh_source_preview(self) -> None:
        panel = getattr(self, "_source_preview_panel", None)
        if panel is None:
            return
        if not self._image_path or not os.path.isfile(self._image_path):
            panel.clear()
            return
        pix, meta = self._build_cropped_source_preview()
        panel.set_preview(pix, meta)

    def _build_cropped_source_preview(self) -> tuple[QPixmap | None, str]:
        crop = self._canvas.crop() if hasattr(self, "_canvas") else None
        if not crop:
            return None, ""
        cx, cy, cw, ch = crop
        meta = f"{int(round(cw))} x {int(round(ch))} px"
        if self._rotation:
            meta += f"  |  rot {self._rotation} deg"

        if HAS_PIL:
            try:
                with Image.open(self._image_path) as src:
                    img = src.convert("RGB")
                if self._rotation != 0:
                    img = img.rotate(-self._rotation, expand=True)
                img = self._apply_adjustments(img)
                img = img.crop((
                    int(round(cx)), int(round(cy)),
                    int(round(cx + cw)), int(round(cy + ch)),
                ))
                try:
                    border_mm = float(self._border_mm.strip() or "0")
                    out_w_mm = float(self._width_mm.strip() or "0")
                except ValueError:
                    border_mm = 0.0
                    out_w_mm = 0.0
                if border_mm > 0 and out_w_mm > 0:
                    img = _apply_source_border(img, border_mm, out_w_mm, (255, 255, 255))
                    meta += f"  |  border {border_mm:g} mm"
                data = img.tobytes("raw", "RGB")
                qimg = QImage(data, img.width, img.height, img.width * 3,
                              QImage.Format.Format_RGB888)
                return QPixmap.fromImage(qimg.copy()), meta
            except Exception:
                pass

        pix = self._canvas.crop_pixmap()
        return pix, meta

    def _schedule_color_preview_refresh(self, delay_ms: int = 250) -> None:
        if not getattr(self, "_jar_panel", None):
            return
        if not HAS_PIL:
            return
        if self._current_litho_mode() != "single" and not HAS_NUMPY:
            return
        timer = getattr(self, "_preview_refresh_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._refresh_color_preview_now)
            self._preview_refresh_timer = timer
        timer.start(delay_ms)

    def _refresh_color_preview_now(self) -> None:
        panel = getattr(self, "_jar_panel", None)
        if panel is None:
            return
        if not self._image_path or not os.path.isfile(self._image_path):
            panel.clear()
            self._update_setting_warnings()
            return
        try:
            if self._current_litho_mode() == "single":
                result = self._build_single_color_preview()
            else:
                active = [hx for hx, on in self.color_vars.items() if on]
                if not active:
                    panel.set_preview(None, "")
                    panel.set_empty_text("Enable some filaments to see the print preview")
                    self._update_setting_warnings()
                    return
                result = self._build_color_preview(active)
        except Exception as exc:
            self._log(f"Preview refresh failed: {exc}\n", "err")
            return
        if result is None:
            self._update_setting_warnings()
            return
        pix, meta = result
        panel.set_preview(pix, meta)
        self._update_setting_warnings()

    def _build_color_preview(self, active_hexes: list):
        """Build the JAR-accurate preview pixmap.

        Returns `(QPixmap, meta_text)` on success, `None` on failure.
        """
        try:
            out_w_mm = float(self._width_mm.strip())
            out_h_mm = float(self._height_mm.strip() or "0")
            color_px = float(self._color_px_w.strip())
            border_mm = float(self._border_mm.strip() or "0")
        except ValueError:
            self._log("Invalid numeric value in dimensions / pixel / border.\n", "err")
            return None
        if out_w_mm <= 0 or color_px <= 0:
            return None

        with Image.open(self._image_path) as src:
            img = src.convert("RGB")
        if self._rotation != 0:
            img = img.rotate(-self._rotation, expand=True)
        img = self._apply_adjustments(img)
        crop = self._canvas.crop()
        if crop and self._image_size:
            cx, cy, cw, ch = crop
            img = img.crop((
                int(round(cx)), int(round(cy)),
                int(round(cx + cw)), int(round(cy + ch)),
            ))
        if border_mm > 0:
            img = _apply_source_border(img, border_mm, out_w_mm, (255, 255, 255))
        iw, ih = img.size
        # Match JAR's ImageUtil.resizeImage: integer truncation, and when
        # height is blank derive it from the source aspect via an intermediate
        # integer-mm step (the JAR truncates twice).
        grid_w = max(1, int(out_w_mm / color_px))
        if out_h_mm <= 0:
            derived_h_mm = int(ih * out_w_mm / iw) if iw else int(out_w_mm)
            grid_h = max(1, int(derived_h_mm / color_px))
            shown_h_mm = derived_h_mm
        else:
            grid_h = max(1, int(out_h_mm / color_px))
            shown_h_mm = out_h_mm
        requested_w, requested_h = grid_w, grid_h
        cap = max(1, int(getattr(self, "_preview_cell_cap", _PREVIEW_MAX_GRID_CELLS)))
        # Cap absurd grids so the preview stays snappy.
        if grid_w * grid_h > cap:
            scale = (cap / (grid_w * grid_h)) ** 0.5
            grid_w = max(1, int(grid_w * scale))
            grid_h = max(1, int(grid_h * scale))
            self._last_preview_capped = True
            self._last_preview_requested = (requested_w, requested_h)
            self._last_preview_actual = (grid_w, grid_h)
        else:
            self._last_preview_capped = False
            self._last_preview_requested = (requested_w, requested_h)
            self._last_preview_actual = (grid_w, grid_h)

        small = img.resize((grid_w, grid_h), Image.NEAREST)

        try:
            max_layers = int(self._layer_count.strip())
        except ValueError:
            max_layers = 5
        max_layers = max(1, max_layers)

        quant = _jar_stack_preview(
            small, self.palette_data, active_hexes, max_layers,
            max_pixels=cap,
        )
        if quant is None:
            return None

        # PIL → QPixmap
        data = quant.tobytes("raw", "RGB")
        qimg = QImage(data, quant.width, quant.height, quant.width * 3,
                      QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg.copy())  # copy so the bytes buffer can be freed

        # Count unique RGB cells in the output to surface how many distinct
        # printed colours the JAR will actually use.
        if HAS_NUMPY:
            arr = np.asarray(quant)
            uniq = len(np.unique(arr.reshape(-1, 3), axis=0))
        else:
            uniq = len(active_hexes)
        w_str = f"{out_w_mm:g}"
        h_str = f"{shown_h_mm:g}"
        meta = (
            f"{w_str} × {h_str} mm  ·  "
            f"{quant.width} × {quant.height} cells  ·  {uniq} colors"
        )
        meta += "  ·  capped" if self._last_preview_capped else "  ·  full preview"
        return pix, meta

    def _build_single_color_preview(self):
        """Build a grayscale texture preview for single-color lithophanes."""
        try:
            out_w_mm = float(self._width_mm.strip())
            out_h_mm = float(self._height_mm.strip() or "0")
            texture_px = float(self._tex_px_w.strip())
            border_mm = float(self._border_mm.strip() or "0")
        except ValueError:
            self._log("Invalid numeric value in dimensions / texture pixel / border.\n", "err")
            return None
        if out_w_mm <= 0 or texture_px <= 0:
            return None

        with Image.open(self._image_path) as src:
            img = src.convert("RGB")
        if self._rotation != 0:
            img = img.rotate(-self._rotation, expand=True)
        img = self._apply_adjustments(img)
        crop = self._canvas.crop()
        if crop and self._image_size:
            cx, cy, cw, ch = crop
            img = img.crop((
                int(round(cx)), int(round(cy)),
                int(round(cx + cw)), int(round(cy + ch)),
            ))
        if border_mm > 0:
            img = _apply_source_border(img, border_mm, out_w_mm, (255, 255, 255))

        iw, ih = img.size
        grid_w = max(1, int(out_w_mm / texture_px))
        if out_h_mm <= 0:
            derived_h_mm = int(ih * out_w_mm / iw) if iw else int(out_w_mm)
            grid_h = max(1, int(derived_h_mm / texture_px))
            shown_h_mm = derived_h_mm
        else:
            grid_h = max(1, int(out_h_mm / texture_px))
            shown_h_mm = out_h_mm

        requested_w, requested_h = grid_w, grid_h
        cap = max(1, int(getattr(self, "_preview_cell_cap", _PREVIEW_MAX_GRID_CELLS)))
        if grid_w * grid_h > cap:
            scale = (cap / (grid_w * grid_h)) ** 0.5
            grid_w = max(1, int(grid_w * scale))
            grid_h = max(1, int(grid_h * scale))
            self._last_preview_capped = True
            self._last_preview_requested = (requested_w, requested_h)
            self._last_preview_actual = (grid_w, grid_h)
        else:
            self._last_preview_capped = False
            self._last_preview_requested = (requested_w, requested_h)
            self._last_preview_actual = (grid_w, grid_h)

        gray = img.convert("L").resize((grid_w, grid_h), Image.NEAREST).convert("RGB")
        data = gray.tobytes("raw", "RGB")
        qimg = QImage(data, gray.width, gray.height, gray.width * 3,
                      QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg.copy())

        w_str = f"{out_w_mm:g}"
        h_str = f"{shown_h_mm:g}"
        filament = self._active_filament_label() or "selected filament"
        meta = (
            f"{w_str} x {h_str} mm  |  "
            f"{gray.width} x {gray.height} cells  |  single color: {filament}"
        )
        meta += "  |  capped" if self._last_preview_capped else "  |  full preview"
        return pix, meta

    def _refresh_border_preview(self) -> None:
        if getattr(self, "_canvas", None):
            self._canvas.set_border_preview(0, 0, 0)
        self._refresh_source_preview()

    # ── Dimensions ────────────────────────────────────────────────────────────
    def _on_w_changed(self, val: str) -> None:
        if self._updating_dims:
            return
        self._width_mm = val
        if self._lock_ratio and self._image_aspect:
            try:
                w = float(val)
                h = round(w / self._image_aspect, 1)
                self._updating_dims = True
                self._height_mm = str(h)
                self._h_input.setText(str(h))
                self._updating_dims = False
            except ValueError:
                pass
        self._update_crop_for_dims()
        self._canvas.update()
        self._update_size_stat()
        self._refresh_border_preview()
        self._schedule_color_preview_refresh()
        self._update_setting_warnings()
        self._sync_orientation_buttons()

    def _on_h_changed(self, val: str) -> None:
        if self._updating_dims:
            return
        self._height_mm = val
        self._update_crop_for_dims()
        self._canvas.update()
        self._update_size_stat()
        self._refresh_border_preview()
        self._schedule_color_preview_refresh()
        self._update_setting_warnings()
        self._sync_orientation_buttons()

    def _on_lock_toggled(self, v: bool) -> None:
        self._lock_ratio = v

    def _update_size_stat(self):
        self._stat_labels["size"].setText(f"SIZE: {self._width_mm} × {self._height_mm} mm")

    def _update_z_stat(self):
        try:
            thick    = float(self._layer_thick)
            colors   = int(self._layer_count)
            backing  = int(self._backing_layers)
            tex_max  = int(self._texture_max_layers)
        except (ValueError, TypeError):
            self._stat_labels["z"].setText("Z: —")
            return
        color_out, texture_out = self._output_flags()
        layer_total = 0
        if color_out:
            layer_total += backing + colors
        if texture_out:
            layer_total += tex_max
        z_mm = layer_total * thick
        self._stat_labels["z"].setText(f"Z: {z_mm:.2f} mm")

    def _effective_height_mm(self) -> float:
        w = float(self._width_mm.strip())
        h_raw = self._height_mm.strip()
        if h_raw:
            return float(h_raw)
        if self._image_aspect:
            return w / self._image_aspect
        return w

    def _generation_thicknesses(self) -> tuple[float, float, float, float]:
        thick = float(self._layer_thick.strip())
        plate_mm = int(self._backing_layers.strip() or "0") * thick
        tmin_mm = int(self._texture_min_layers.strip() or "0") * thick
        tmax_mm = int(self._texture_max_layers.strip() or "0") * thick
        return thick, plate_mm, tmin_mm, tmax_mm

    def _output_flags(self) -> tuple[bool, bool]:
        if self._output_mode == "color_only":
            return True, False
        if self._output_mode == "texture_only":
            return False, True
        return True, True

    def _add_optional_arg(self, cmd: list, flag: str, value: str) -> None:
        value = (value or "").strip()
        if value:
            cmd.extend([flag, value])

    def _write_single_color_engine_palette(self, tmp_paths: list) -> str:
        """Write a temp palette that satisfies the JAR's white requirement.

        PIXEstL still validates the active palette before honoring `-z false`.
        It requires active `#FFFFFF` plus at least one measured non-white color.
        The selected single-color filament is a print/material choice in the UI;
        the texture mesh itself is generated through White internally.
        """
        if "#FFFFFF" not in self.palette_data:
            raise RuntimeError("Single-color mode requires #FFFFFF in the palette.")
        engine_palette = copy.deepcopy(self.palette_data)
        selected = self._single_color_hex
        selected_info = engine_palette.get(selected, {}) or {}
        support_hex = ""
        if (
            selected.upper() != "#FFFFFF"
            and isinstance(selected_info.get("layers"), dict)
            and selected_info.get("layers")
        ):
            support_hex = selected
        if not support_hex:
            for hx, info in engine_palette.items():
                if hx.upper() == "#FFFFFF" or not isinstance(info, dict):
                    continue
                layers = info.get("layers")
                if isinstance(layers, dict) and layers:
                    support_hex = hx
                    break
        if not support_hex:
            raise RuntimeError(
                "Single-color mode requires at least one measured non-white palette entry."
            )
        for hx, info in engine_palette.items():
            if isinstance(info, dict):
                info["active"] = hx.upper() == "#FFFFFF" or hx == support_hex
        tmp = tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", encoding="utf-8", delete=False
        )
        with tmp:
            json.dump(engine_palette, tmp, indent=2, ensure_ascii=False)
        tmp_paths.append(tmp.name)
        return tmp.name

    def _build_jar_cmd(self, src_path: str, out_path: str,
                       color: bool, texture: bool,
                       palette_path: str | None = None) -> list:
        _thick, plate_mm, tmin_mm, tmax_mm = self._generation_thicknesses()
        cmd = [
            "java", "-jar", JAR_PATH,
            "-p", palette_path or self._palette_path,
            "-w", self._width_mm.strip(),
        ]
        h_mm = self._height_mm.strip()
        if h_mm:
            cmd += ["-H", h_mm]
        cmd += [
            "-b", self._layer_thick.strip(),
            "-l", self._layer_count.strip(),
            "-f", f"{plate_mm:.3f}",
            "-m", f"{tmin_mm:.3f}",
            "-M", f"{tmax_mm:.3f}",
            "-cW", self._color_px_w.strip(),
            "-tW", self._tex_px_w.strip(),
            "-d", self._distance_method,
            "-F", self._pixel_mode,
        ]
        self._add_optional_arg(cmd, "-c", self._color_number)
        self._add_optional_arg(cmd, "-C", self._curve)
        self._add_optional_arg(cmd, "-n", self._layer_threads)
        self._add_optional_arg(cmd, "-N", self._row_threads)
        self._add_optional_arg(cmd, "-t", self._layer_timeout)
        self._add_optional_arg(cmd, "-T", self._row_timeout)
        if self._low_memory:
            cmd.append("-Y")
        cmd += [
            "-i", src_path,
            "-o", out_path,
            "-z", "true" if color else "false",
            "-Z", "true" if texture else "false",
        ]
        return cmd

    def _show_text_dialog(self, title: str, text: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(760, 560)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setFont(_mf(10))
        viewer.setPlainText(text)
        lay.addWidget(viewer, 1)
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)
        dlg.exec()

    def _show_engine_help(self) -> None:
        cmd = ["java", "-jar", JAR_PATH, "--help"]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                cwd=SCRIPT_DIR,
                timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            text = (
                f"Command\n{subprocess.list2cmdline(cmd)}\n\n"
                f"Exit code: {proc.returncode}\n\n"
                f"{proc.stdout}"
            )
        except FileNotFoundError:
            text = "java not found. Install Java and make sure it is on PATH."
        except Exception as exc:
            text = f"Engine diagnostics failed: {exc}"
        self._show_text_dialog("PIXEstL engine help", text)

    # ── Crop ──────────────────────────────────────────────────────────────────
    def _target_ratio(self):
        try:
            w = float(self._width_mm)
            h = float(self._height_mm)
            if w > 0 and h > 0:
                return w / h
        except ValueError:
            pass
        return None

    def _recenter_crop(self) -> None:
        if not self._image_size:
            return
        ratio = self._target_ratio()
        iw, ih = self._image_size
        if ratio is None:
            self._canvas.set_crop((0, 0, iw, ih))
            return
        if iw / ih > ratio:
            ch = ih
            cw = ih * ratio
        else:
            cw = iw
            ch = iw / ratio
        cx = (iw - cw) / 2
        cy = (ih - ch) / 2
        self._canvas.set_crop((cx, cy, cw, ch))
        self._update_crop_stat()

    def _update_crop_for_dims(self) -> None:
        if not self._image_size or not self._canvas.crop():
            return
        ratio = self._target_ratio()
        iw, ih = self._image_size
        if ratio is None:
            self._canvas.set_crop((0, 0, iw, ih))
            return
        old = self._canvas.crop()
        old_cx, old_cy, old_cw, old_ch = old
        center_x = old_cx + old_cw / 2
        center_y = old_cy + old_ch / 2
        if iw / ih > ratio:
            ch = ih
            cw = ih * ratio
        else:
            cw = iw
            ch = iw / ratio
        nx = max(0.0, min(center_x - cw / 2, iw - cw))
        ny = max(0.0, min(center_y - ch / 2, ih - ch))
        self._canvas.set_crop((nx, ny, cw, ch))
        self._update_crop_stat()

    def _update_crop_stat(self):
        c = self._canvas.crop()
        if c:
            _, _, cw, ch = c
            self._stat_labels["crop"].setText(f"CROP: {int(round(cw))} × {int(round(ch))} px")
        else:
            self._stat_labels["crop"].setText("CROP: -")

    # ── Palette ───────────────────────────────────────────────────────────────
    def _load_palette(self) -> None:
        path = self._palette_path
        if not os.path.isfile(path):
            self._log(f"Palette not found: {path}\n", "err")
            return
        try:
            with open(path, encoding="utf-8") as f:
                self.palette_data = json.load(f)
        except Exception as exc:
            self._log(f"Could not parse palette JSON: {exc}\n", "err")
            return
        self._rebuild_filament_list()

    def _rebuild_filament_list(self) -> None:
        # Clear
        for i in reversed(range(self._filament_layout.count())):
            item = self._filament_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self._filament_rows.clear()
        self._filament_row_section.clear()
        self.color_vars.clear()

        # Classify each entry by whether it has per-layer HSL data.
        measured: list[tuple[str, dict]] = []
        flat: list[tuple[str, dict]] = []
        for hex_code, info in self.palette_data.items():
            if not isinstance(info, dict):
                continue
            layers = info.get("layers")
            if isinstance(layers, dict) and layers:
                measured.append((hex_code, info))
            else:
                flat.append((hex_code, info))

        self._filament_section_headers = {}

        def _make_row(hex_code: str, info: dict, section: str) -> FilamentRow:
            full_name = info.get("name", hex_code)
            active    = bool(info.get("active", True))
            m = re.match(r"^(.*?)\[([^\]]+)\]$", full_name)
            if m:
                name, material = m.group(1).strip(), m.group(2)
            else:
                name, material = full_name, ""
            layers = info.get("layers")
            n_layers = len(layers) if isinstance(layers, dict) else 0

            self.color_vars[hex_code] = active
            row = FilamentRow(
                hex_code, name, material, active,
                layer_count=n_layers,
                muted=(section == "flat"),
            )
            if section == "flat":
                row.setToolTip(
                    "Available for single-color lithos; ignored in ADDITIVE mode "
                    "because it has no measured layer data."
                )
            row.toggled.connect(self._on_filament_toggled)
            row.edit_requested.connect(self._open_color_editor)
            self._filament_rows[hex_code] = row
            self._filament_row_section[hex_code] = section
            self._filament_layout.insertWidget(self._filament_layout.count() - 1, row)
            return row

        insert_anchor = self._filament_layout.count() - 1

        # Measured group
        if measured:
            hdr = FilamentSectionHeader("MULTI-LAYER", len(measured))
            self._filament_section_headers["measured"] = hdr
            self._filament_layout.insertWidget(insert_anchor, hdr)
            for hex_code, info in measured:
                _make_row(hex_code, info, "measured")

        # Hex-only group
        if flat:
            hdr = FilamentSectionHeader("HEX-ONLY  (ignored in additive)", len(flat))
            self._filament_section_headers["flat"] = hdr
            self._filament_layout.insertWidget(self._filament_layout.count() - 1, hdr)
            for hex_code, info in flat:
                _make_row(hex_code, info, "flat")

        self._update_filament_count_label()
        if self._current_litho_mode() == "single":
            self._apply_single_filament_lock()
        self._sync_filament_controls()
        self._apply_hex_only_visibility()
        self._schedule_color_preview_refresh(delay_ms=50)
        self._update_setting_warnings()

    def _single_filament_choice(self, preferred_hex: str | None = None) -> str:
        if preferred_hex in self.color_vars:
            return preferred_hex
        active = [hx for hx, on in self.color_vars.items() if on]
        if len(active) == 1:
            return active[0]
        if self._single_color_hex in active:
            return self._single_color_hex
        if "#FFFFFF" in active:
            return "#FFFFFF"
        if active:
            return active[0]
        if self._single_color_hex in self.color_vars:
            return self._single_color_hex
        if "#FFFFFF" in self.color_vars:
            return "#FFFFFF"
        return next(iter(self.color_vars), "")

    def _apply_single_filament_lock(self, preferred_hex: str | None = None) -> str:
        chosen = self._single_filament_choice(preferred_hex)
        if not chosen:
            self._update_filament_count_label()
            return ""
        self._single_color_hex = chosen
        for hx, row in self._filament_rows.items():
            active = hx == chosen
            self.color_vars[hx] = active
            row.setChecked(active)
        self._update_filament_count_label()
        return chosen

    def _restore_color_filament_state(self) -> None:
        for hx, row in self._filament_rows.items():
            info = self.palette_data.get(hx, {}) or {}
            active = bool(info.get("active", True))
            self.color_vars[hx] = active
            row.setChecked(active)
        self._update_filament_count_label()

    def _active_filament_label(self) -> str:
        selected = next((hx for hx, on in self.color_vars.items() if on), "")
        if not selected:
            return ""
        info = self.palette_data.get(selected, {}) or {}
        name = info.get("name") or selected
        return re.sub(r"\[[^\]]+\]$", "", name).strip() or name

    def _update_filament_count_label(self) -> None:
        label = getattr(self, "_filament_count_lbl", None)
        if label is None:
            return
        count = len(self.color_vars)
        active_count = sum(1 for v in self.color_vars.values() if v)
        if self._current_litho_mode() == "single":
            label.setText(f"{active_count} / {count} selected")
        else:
            label.setText(f"{active_count} / {count} active")

    def _sync_filament_controls(self) -> None:
        single = self._current_litho_mode() == "single"
        tip = "Single-color mode locks the palette to one selected filament."
        for btn in (getattr(self, "_all_on_btn", None), getattr(self, "_all_off_btn", None)):
            if btn is not None:
                btn.setEnabled(not single)
                btn.setToolTip(tip if single else "")
        hex_btn = getattr(self, "_hex_only_btn", None)
        if hex_btn is not None:
            hex_btn.setEnabled(not single)
            if single:
                hex_btn.setText("All filaments shown")
                hex_btn.setToolTip("Single-color mode can use measured or hex-only filaments.")
            else:
                hex_btn.setText(
                    "Hide hex-only filaments" if hex_btn.isChecked()
                    else "Show hex-only filaments"
                )
                hex_btn.setToolTip(
                    "Hex-only palette entries are ignored by ADDITIVE mode unless they have measured layer data."
                )

    def _on_filament_toggled(self, hex_code: str, active: bool) -> None:
        if self._current_litho_mode() == "single":
            self._apply_single_filament_lock(hex_code)
            self._schedule_color_preview_refresh()
            self._update_setting_warnings()
            return
        self.color_vars[hex_code] = active
        if hex_code in self.palette_data:
            self.palette_data[hex_code]["active"] = active
        self._update_filament_count_label()
        self._schedule_color_preview_refresh()
        self._update_setting_warnings()

    def _set_all(self, state: bool) -> None:
        if self._current_litho_mode() == "single":
            self._apply_single_filament_lock()
            self._schedule_color_preview_refresh()
            self._update_setting_warnings()
            return
        for hx, row in self._filament_rows.items():
            row.setChecked(state)
            self.color_vars[hx] = state
            if hx in self.palette_data:
                self.palette_data[hx]["active"] = state
        self._update_filament_count_label()
        self._schedule_color_preview_refresh()
        self._update_setting_warnings()

    def _toggle_hex_only_filaments(self, checked: bool) -> None:
        self._show_hex_only = checked
        if hasattr(self, "_hex_only_btn"):
            self._hex_only_btn.setText(
                "Hide hex-only filaments" if checked else "Show hex-only filaments"
            )
        self._apply_hex_only_visibility()

    def _apply_hex_only_visibility(self) -> None:
        text = getattr(self, "_filter_input", None)
        filter_text = text.text().lower() if text is not None else ""
        single = self._current_litho_mode() == "single"
        section_visible_count = {"measured": 0, "flat": 0}
        for hx, row in self._filament_rows.items():
            section = self._filament_row_section.get(hx)
            info = self.palette_data.get(hx, {})
            name = info.get("name", hx).lower()
            matches_filter = (not filter_text) or filter_text in name or filter_text in hx.lower()
            visible = matches_filter and (single or section != "flat" or self._show_hex_only)
            row.setVisible(visible)
            if visible and section in section_visible_count:
                section_visible_count[section] += 1
        for section, hdr in self._filament_section_headers.items():
            if section == "flat" and not single and not self._show_hex_only:
                hdr.setVisible(False)
            else:
                hdr.setVisible(section_visible_count.get(section, 0) > 0)

    def _filter_filaments(self, text: str) -> None:
        self._apply_hex_only_visibility()

    def _save_palette(self) -> None:
        path = self._palette_path
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.palette_data, f, indent=2, ensure_ascii=False)
            self._log(f"Palette saved → {path}\n", "ok")
        except Exception as exc:
            self._log(f"Save failed: {exc}\n", "err")

    def _save_palette_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Palette As",
            os.path.dirname(self._palette_path),
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.palette_data, f, indent=2, ensure_ascii=False)
            self._palette_path = path
            self._log(f"Palette saved → {path}\n", "ok")
        except Exception as exc:
            self._log(f"Save failed: {exc}\n", "err")

    def _open_color_editor(self, hex_code: str) -> None:
        info = self.palette_data.get(hex_code, {})
        dlg  = ColorEditorDialog(hex_code, info, is_new=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_hex, new_info = dlg.get_result()
        if new_hex is None:
            self.palette_data.pop(hex_code, None)
        elif new_hex != hex_code:
            # Re-insert at the same position preserving order
            new_data = {}
            for k, v in self.palette_data.items():
                if k == hex_code:
                    new_data[new_hex] = new_info
                else:
                    new_data[k] = v
            self.palette_data = new_data
        else:
            self.palette_data[hex_code] = new_info
        self._rebuild_filament_list()
        if self._current_litho_mode() == "single":
            self._apply_single_filament_lock(new_hex)
            self._apply_hex_only_visibility()
            self._schedule_color_preview_refresh(delay_ms=50)

    def _add_new_color(self) -> None:
        default = {"name": "New Color[PLA Basic]", "active": True, "layers": {}}
        dlg = ColorEditorDialog("#FFFFFF", default, is_new=True, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_hex, new_info = dlg.get_result()
        if new_hex and new_info:
            if self._current_litho_mode() == "single":
                new_info = dict(new_info)
                new_info["active"] = False
            self.palette_data[new_hex] = new_info
            self._rebuild_filament_list()
            if self._current_litho_mode() == "single":
                self._apply_single_filament_lock(new_hex)
                self._apply_hex_only_visibility()
                self._schedule_color_preview_refresh(delay_ms=50)

    # ── Run ───────────────────────────────────────────────────────────────────
    def _generate_stl(self) -> None:
        img = self._image_path.strip()
        if not img:
            QMessageBox.warning(self, "No image", "Please select an image file first.")
            return
        if not os.path.isfile(img):
            QMessageBox.critical(self, "Not found", f"Image file not found:\n{img}")
            return
        if not os.path.isfile(JAR_PATH):
            QMessageBox.critical(self, "JAR missing", f"lithopainter.jar not found:\n{JAR_PATH}")
            return

        self._save_palette()

        img_name = os.path.splitext(os.path.basename(img))[0]
        out_zip  = os.path.join(self.output_dir, img_name + ".zip")

        self._log(f"Output will be saved to:\n  {out_zip}\n", "dim")
        self._run_btn.setText("  Cancel  ")
        if hasattr(self, "_gen_btn_top"):
            self._gen_btn_top.setEnabled(False)
        self._status_pill.set_state("Running", T["warn"])

        crop = self._canvas.crop()

        def _worker() -> None:
            tmp_paths: list = []
            try:
                JAVA_SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".wbmp"}
                ext = os.path.splitext(img)[1].lower()

                needs_crop = False
                if crop and self._image_size:
                    cx, cy, cw, ch = crop
                    iw, ih = self._image_size
                    needs_crop = (abs(cw - iw) > 1 or abs(ch - ih) > 1)
                needs_convert = ext not in JAVA_SUPPORTED
                needs_rotate  = self._rotation != 0
                needs_adjust  = HAS_PIL and any(
                    v != 0 for v in [
                        self._adj_color_temp, self._adj_tint, self._adj_exposure,
                        self._adj_highlights, self._adj_shadows, self._adj_saturation,
                    ]
                )

                try:
                    border_mm_val = float(self._border_mm.strip() or "0")
                except ValueError:
                    border_mm_val = 0.0
                needs_border = border_mm_val > 0

                def _bake_input(border_rgb: tuple | None) -> str:
                    """Return a path to an input image suitable for the JAR.
                    If border_rgb is None, no border pad is applied (used when
                    needs_border is False). Otherwise the inner content is
                    shrunk and padded with the given color."""
                    if not (needs_crop or needs_convert or needs_rotate or
                            needs_adjust or border_rgb is not None):
                        return img
                    if not HAS_PIL:
                        raise RuntimeError(
                            "Pillow required for crop / border / format conversion. "
                            "Install with: pip install pillow"
                        )
                    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    tmp.close()
                    tmp_paths.append(tmp.name)
                    with Image.open(img) as pil_img:
                        out_img = pil_img.convert("RGB")
                        if needs_rotate:
                            out_img = out_img.rotate(-self._rotation, expand=True)
                        out_img = self._apply_adjustments(out_img)
                        if needs_crop:
                            cx, cy, cw, ch = crop
                            out_img = out_img.crop((
                                int(round(cx)), int(round(cy)),
                                int(round(cx + cw)), int(round(cy + ch)),
                            ))
                        if border_rgb is not None:
                            try:
                                out_w_mm = float(self._width_mm.strip())
                            except ValueError:
                                out_w_mm = 0.0
                            out_img = _apply_source_border(
                                out_img, border_mm_val, out_w_mm, border_rgb
                            )
                        out_img.save(tmp.name, "PNG")
                    return tmp.name

                if needs_crop:
                    cx, cy, cw, ch = crop
                    self._log(
                        f"Cropped to {int(round(cw))}×{int(round(ch))} px "
                        f"at ({int(round(cx))}, {int(round(cy))})\n", "dim"
                    )
                if needs_border:
                    self._log(
                        f"Added {border_mm_val:g} mm border; texture frame "
                        "exports as a separate STL when texture output is enabled.\n",
                        "dim",
                    )

                color_out, texture_out = self._output_flags()
                palette_path = self._palette_path
                if not color_out and texture_out:
                    palette_path = self._write_single_color_engine_palette(tmp_paths)
                if color_out and texture_out:
                    self._log("Litho mode: color (-z true, -Z true).\n", "dim")
                elif texture_out:
                    filament = self._active_filament_label() or "selected filament"
                    self._log(
                        f"Litho mode: single color ({filament}; texture only, "
                        "32 x 0.10 mm = 3.20 mm).\n",
                        "dim",
                    )
                elif color_out:
                    self._log("Litho mode: color only (-z true, -Z false).\n", "dim")

                def _run(cmd: list) -> int:
                    self._log(f"\n$ {subprocess.list2cmdline(cmd)}\n", "dim")
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        encoding="utf-8",
                        errors="replace",
                        cwd=SCRIPT_DIR,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    self._proc = proc
                    for line in proc.stdout:
                        self._log(line)
                    proc.wait()
                    self._proc = None
                    return proc.returncode

                border_rgb = (255, 255, 255) if needs_border else None
                src = _bake_input(border_rgb)
                rc = _run(self._build_jar_cmd(
                    src, out_zip, color=color_out, texture=texture_out,
                    palette_path=palette_path
                ))

                if rc == 0:
                    if needs_border and texture_out:
                        _thick, _plate_mm, _tmin_mm, tmax_mm = self._generation_thicknesses()
                        frame_file = _append_frame_stl_to_zip(
                            out_zip, border_mm_val, tmax_mm
                        )
                        if frame_file:
                            self._log(f"Added separate frame STL: {frame_file}\n", "dim")
                        else:
                            self._log("Could not add separate frame STL.\n", "warn")
                    self._log(f"\nDone! Output: {out_zip}\n", "ok")
                    extract_dir = os.path.join(self.output_dir, img_name)
                    try:
                        os.makedirs(extract_dir, exist_ok=True)
                        with zipfile.ZipFile(out_zip) as zf:
                            zf.extractall(extract_dir)
                        self._log(f"Unzipped to: {extract_dir}\n", "dim")
                    except Exception as exc:
                        self._log(f"Unzip failed: {exc}\n", "err")
                        extract_dir = self.output_dir
                    self._append_print_settings_note(extract_dir)
                    # .3mf generation is disabled for now; keep the exporter
                    # code below so it can be re-enabled quickly.
                    # self._build_bambu_3mf(extract_dir, img_name)
                    self._log(".3mf generation disabled.\n", "dim")
                    try:
                        os.startfile(extract_dir)  # noqa: S606  (Windows only)
                    except Exception as exc:
                        self._log(f"Could not open folder: {exc}\n", "err")
                    QMetaObject.invokeMethod(self, "_on_run_done_ok", Qt.ConnectionType.QueuedConnection)
                else:
                    self._log(f"\nExited with code {rc}\n", "err")
                    QMetaObject.invokeMethod(self, "_on_run_done_err", Qt.ConnectionType.QueuedConnection)
            except FileNotFoundError:
                self._proc = None
                self._log("java not found — is Java installed and on your PATH?\n", "err")
                QMetaObject.invokeMethod(self, "_on_run_done_err", Qt.ConnectionType.QueuedConnection)
            except Exception as exc:
                self._proc = None
                self._log(f"Error: {exc}\n", "err")
                QMetaObject.invokeMethod(self, "_on_run_done_err", Qt.ConnectionType.QueuedConnection)
            finally:
                for p in tmp_paths:
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _append_print_settings_note(self, extract_dir: str) -> None:
        """Append a recommended-settings line to the JAR-generated
        instructions.txt so the user has print parameters alongside the
        swap mapping (no completion popup)."""
        path = os.path.join(extract_dir, "instructions.txt")
        color_out, texture_out = self._output_flags()
        if color_out and texture_out:
            mode_line = "  Litho mode -> Color (-z true, -Z true)\n"
        elif texture_out:
            filament = self._active_filament_label() or "selected filament"
            mode_line = (
                f"  Litho mode -> Single color: {filament} "
                "(texture only, 32 x 0.10 mm = 3.20 mm)\n"
            )
        elif color_out:
            mode_line = "  Litho mode -> Color only (-z true, -Z false)\n"
        else:
            mode_line = "  Litho mode -> Custom\n"
        frame_line = ""
        try:
            border_mm = float(self._border_mm.strip() or "0")
        except ValueError:
            border_mm = 0.0
        if texture_out and border_mm > 0:
            frame_line = "  Frame -> layer-frame.stl\n"
        note = (
            "\n\nRecommended print settings\n"
            f"{mode_line}"
            f"{frame_line}"
            "  0.4 mm nozzle  ->  0.1 mm layer height\n"
            "  0.2 mm nozzle  ->  0.1 mm layer height\n"
        )
        try:
            mode = "a" if os.path.exists(path) else "w"
            with open(path, mode, encoding="utf-8") as f:
                f.write(note)
        except OSError as exc:
            self._log(f"Could not update instructions.txt: {exc}\n", "warn")

    def _parse_ams_swap_overrides(
        self,
        extract_dir: str,
        active_filaments: list,
        template_colours: list,
    ) -> dict:
        path = os.path.join(extract_dir, "instructions.txt")
        if not os.path.exists(path):
            return {}
        base_slots = {}
        for i, (fname, fhex) in enumerate(active_filaments):
            slot = 0
            if template_colours and hasattr(bambu_3mf, "_closest_template_slot"):
                try:
                    slot = bambu_3mf._closest_template_slot(fhex, template_colours)
                except Exception:
                    slot = 0
            if slot <= 0:
                slot = i + 2
            base_slots[fname] = slot
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return {}
        overrides = {}
        for src, target in re.findall(r"([^,\n:]+?)-->([^,\n]+)", text):
            src_name = src.strip()
            target_name = target.strip()
            slot = base_slots.get(src_name)
            if slot:
                overrides[target_name] = slot
        return overrides

    def _build_bambu_3mf(self, extract_dir: str, img_name: str) -> None:
        """After the JAR succeeds, package the STLs as a Bambu .3mf with a
        height-range modifier on the texture region (fine layer height)."""
        template_dir = os.path.join(SCRIPT_DIR, "resources", "bambu_template")
        if not os.path.exists(os.path.join(template_dir, "project_settings.config")):
            self._log(
                "Skipping .3mf: resources/bambu_template/project_settings.config "
                "missing (drop a Bambu reference .3mf's project_settings.config "
                "in there to enable).\n", "warn"
            )
            return
        try:
            stl_paths = sorted(
                os.path.join(extract_dir, n)
                for n in os.listdir(extract_dir)
                if n.lower().endswith(".stl")
            )
            if not stl_paths:
                self._log("Skipping .3mf: no STLs in output dir.\n", "warn")
                return
            active_filaments = [
                (p.get("name", ""), hex_code)
                for hex_code, p in self.palette_data.items()
                if p.get("active", True)
            ]
            template_colours = bambu_3mf.read_template_filament_colours(template_dir)
            slot_overrides = self._parse_ams_swap_overrides(
                extract_dir, active_filaments, template_colours
            )
            if slot_overrides:
                self._log(
                    "Applied AMS swap mapping from instructions.txt: "
                    + ", ".join(f"{name}->slot {slot}" for name, slot in slot_overrides.items())
                    + "\n",
                    "dim",
                )
            parts = bambu_3mf.classify_jar_stls(
                stl_paths, active_filaments, template_colours, slot_overrides
            )
            out_3mf = os.path.join(extract_dir, f"{img_name}.3mf")
            try:
                thick    = float(self._layer_thick)
                backing  = int(self._backing_layers)
                colors   = int(self._layer_count)
                tex_min  = int(self._texture_min_layers)
                tex_max  = int(self._texture_max_layers)
                fine     = float(self._fine_layer_h)
                plate_w  = float(self._width_mm)
                plate_h  = float(self._height_mm) if self._height_mm.strip() else plate_w
            except (ValueError, TypeError):
                self._log("Skipping .3mf: invalid numeric settings.\n", "warn")
                return
            color_out, _texture_out = self._output_flags()
            if not color_out:
                backing = 0
                colors = 0
            bambu_3mf.build_3mf(
                out_path=out_3mf,
                parts=parts,
                plate_w_mm=plate_w,
                plate_h_mm=plate_h,
                layer_thick_mm=thick,
                backing_layers=backing,
                color_layers=colors,
                texture_min_layers=tex_min,
                texture_max_layers=tex_max,
                fine_layer_height_mm=fine,
                template_dir=template_dir,
                project_name=img_name,
            )
            self._log(f"Bambu .3mf written: {out_3mf}\n", "ok")
            tex_min_z = (backing + colors + tex_min) * thick
            tex_max_z = (backing + colors + tex_max) * thick
            tex_part_name = next(
                (p["name"] for p in parts if p["kind"] == "texture"),
                "",
            )
            if tex_part_name:
                self._log(
                    f"  Texture range Z={tex_min_z:.2f}-{tex_max_z:.2f} mm "
                    f"at {fine:.2f} mm layer height.\n", "dim"
                )
            else:
                self._log("  No texture STL found; skipping height-range notes.\n", "dim")
            self._append_print_settings_note(extract_dir)
        except Exception as exc:
            self._log(f".3mf export failed: {exc}\n", "err")
            self._log(traceback.format_exc(), "dim")

    from PySide6.QtCore import Slot as _Slot

    @_Slot()
    def _on_run_done_ok(self):
        self._run_btn.setText("  Generate STL  ")
        if hasattr(self, "_gen_btn_top"):
            self._gen_btn_top.setEnabled(True)
        self._status_pill.set_state("Done", T["ok"])

    @_Slot()
    def _on_run_done_err(self):
        self._run_btn.setText("  Generate STL  ")
        if hasattr(self, "_gen_btn_top"):
            self._gen_btn_top.setEnabled(True)
        self._status_pill.set_state("Error", T["err"])

    def _on_run_btn_clicked(self) -> None:
        if self._proc is not None:
            self._cancel_generation()
        else:
            self._generate_stl()

    def _cancel_generation(self) -> None:
        proc = self._proc
        if proc is not None:
            proc.terminate()
            self._proc = None
            self._run_btn.setText("  Generate STL  ")
            if hasattr(self, "_gen_btn_top"):
                self._gen_btn_top.setEnabled(True)
            self._status_pill.set_state("Cancelled", T["warn"])
            self._log("\nGeneration cancelled.\n", "err")

    def _open_output_folder(self) -> None:
        os.startfile(self.output_dir)

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("Litho")
    app.setOrganizationName("Litho")
    app.setStyleSheet(_global_qss())
    win = LithoWindow()
    win.show()
    sys.exit(app.exec())
