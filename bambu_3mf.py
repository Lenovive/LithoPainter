"""Build a Bambu Studio-compatible .3mf from Lithopainter's STL output.

Embeds a `layer_config_ranges.xml` so the texture region of the lithophane
prints at a user-specified fine layer height (e.g. 0.04 mm) via Bambu's
height-range modifier feature, even though the surrounding color stack
uses the project's nominal layer height (e.g. 0.10 mm).
"""

import os
import re
import uuid
import zipfile

# JAR-output STLs are ASCII "solid v3d.csg" format. Plate STL spans
# Z in [-backing*thick, 0]; the color and texture STLs sit on top.
# We lift everything by `backing * thick` via per-component transforms
# so build-space Z = mesh-space Z + backing*thick.


def _stream_ascii_stl_triangles(stl_path: str):
    """Yield (v1, v2, v3) tuples of (x,y,z) floats from an ASCII STL."""
    vbuf = []
    with open(stl_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.lstrip()
            if s.startswith("vertex"):
                parts = s.split()
                vbuf.append((float(parts[1]), float(parts[2]), float(parts[3])))
                if len(vbuf) == 3:
                    yield vbuf[0], vbuf[1], vbuf[2]
                    vbuf = []


def _new_uuid() -> str:
    return str(uuid.uuid4())


def build_3mf(
    out_path: str,
    parts: list,                 # list of dicts: {name, stl_path, extruder}
    plate_w_mm: float,
    plate_h_mm: float,
    layer_thick_mm: float,
    backing_layers: int,
    color_layers: int,
    texture_min_layers: int,
    texture_max_layers: int,
    fine_layer_height_mm: float,
    template_dir: str,
    project_name: str = "lithophane",
) -> None:
    """Write a Bambu-compatible .3mf at `out_path`.

    `parts` is the ordered list of mesh parts. Each item has:
        - name:       display name (e.g. "obj_cyan", "layer-texture", "plate")
        - stl_path:   absolute path to the JAR-output ASCII STL
        - extruder:   1-based filament index in the Bambu project
        - kind:       one of "texture", "color", "plate"
    """
    proj_settings = os.path.join(template_dir, "project_settings.config")
    filament_seq  = os.path.join(template_dir, "filament_sequence.json")
    if not os.path.exists(proj_settings):
        raise FileNotFoundError(
            f"Bambu template missing: {proj_settings}. "
            "Re-add resources/bambu_template/project_settings.config."
        )

    z_lift = backing_layers * layer_thick_mm
    color_top   = (backing_layers + color_layers) * layer_thick_mm
    texture_min_z = color_top + texture_min_layers * layer_thick_mm
    texture_max_z = color_top + texture_max_layers * layer_thick_mm

    # Place the print roughly centered on a 256-mm bed (Bambu X1/P1 default).
    bed_cx, bed_cy = 128.0, 128.0
    place_x = bed_cx - plate_w_mm / 2.0
    place_y = bed_cy - plate_h_mm / 2.0

    # Each sub-mesh becomes its own 3mf object inside object_1.model,
    # referenced as a component from the top-level 3dmodel.model.
    sub_objects = []  # (id, uuid, transform_str, part_dict)
    for idx, p in enumerate(parts, start=1):
        sub_uuid = f"00010{idx-1:03d}-b206-40ff-9872-83e8017abed1"
        # Identity orientation, lift into build space by z_lift.
        xform = (
            f"1 0 0 0 1 0 0 0 1 {place_x:.4f} {place_y:.4f} {z_lift:.4f}"
        )
        sub_objects.append((idx, sub_uuid, xform, p))

    top_uuid = _new_uuid()
    item_uuid = _new_uuid()
    build_uuid = _new_uuid()

    # Build the top-level model XML referencing the components.
    components_xml = "\n".join(
        f'    <component p:path="/3D/Objects/object_1.model" objectid="{i}" '
        f'p:UUID="{u}" transform="{x}"/>'
        for i, u, x, _p in sub_objects
    )
    top_object_id = len(sub_objects) + 1  # Avoid collision with sub-object ids.
    top_model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
 <metadata name="Application">Lithopainter</metadata>
 <metadata name="BambuStudio:3mfVersion">1</metadata>
 <metadata name="CreationDate">2026-05-17</metadata>
 <metadata name="ModificationDate">2026-05-17</metadata>
 <resources>
  <object id="{top_object_id}" p:UUID="{top_uuid}" type="model">
   <components>
{components_xml}
   </components>
  </object>
 </resources>
 <build p:UUID="{build_uuid}">
  <item objectid="{top_object_id}" p:UUID="{item_uuid}" transform="1 0 0 0 1 0 0 0 1 0 0 0" printable="1"/>
 </build>
</model>
'''

    # model_settings.config: maps part subtypes to source STLs / extruders.
    # The texture part is also tagged so the user can see which one carries
    # the height-range modifier.
    parts_xml = []
    for i, u, x, p in sub_objects:
        parts_xml.append(
            f'''    <part id="{i}" subtype="normal_part">
      <metadata key="name" value="{p['name']}"/>
      <metadata key="matrix" value="{x}"/>
      <metadata key="source_file" value="{os.path.basename(p['stl_path'])}"/>
      <metadata key="extruder" value="{p['extruder']}"/>
    </part>'''
        )
    parts_block = "\n".join(parts_xml)

    model_settings = f'''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="{top_object_id}">
    <metadata key="name" value="{project_name}"/>
    <metadata key="layer_height" value="{layer_thick_mm}"/>
    <metadata key="sparse_infill_density" value="100%"/>
    <metadata key="sparse_infill_pattern" value="zig-zag"/>
{parts_block}
  </object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value="{project_name}"/>
    <metadata key="locked" value="false"/>
    <metadata key="filament_map_mode" value="Auto For Flush"/>
    <metadata key="gcode_file" value=""/>
    <model_instance>
      <metadata key="object_id" value="{top_object_id}"/>
      <metadata key="instance_id" value="0"/>
      <metadata key="identify_id" value="1"/>
    </model_instance>
  </plate>
  <assemble>
  </assemble>
</config>
'''

    # The texture part id is whichever sub-object has kind="texture".
    texture_part_id = next(
        (i for (i, _u, _x, p) in sub_objects if p.get("kind") == "texture"),
        None,
    )
    layer_ranges = ""
    if texture_part_id is not None:
        layer_ranges = f'''<?xml version="1.0" encoding="utf-8"?>
<objects>
 <object id="{texture_part_id}">
  <range min_z="{texture_min_z:.4f}" max_z="{texture_max_z:.4f}">
   <option opt_key="extruder">1</option>
   <option opt_key="layer_height">{fine_layer_height_mm}</option>
  </range>
 </object>
</objects>
'''

    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
</Types>
'''

    rels_root = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
'''

    rels_3d = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/Objects/object_1.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
'''

    slice_info = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="02.06.00.51"/>
  </header>
</config>
'''

    # object_1.model holds every part's mesh in one file, each as its own
    # <object id="N"> element. We write the file as a single deflated entry
    # so the XML repetition compresses well.
    parts_meshes = []
    for i, u, _x, p in sub_objects:
        # Re-emit mesh per part. Keep memory low by streaming each STL once.
        parts_meshes.append((i, u, p))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels_root)
        zf.writestr("3D/_rels/3dmodel.model.rels", rels_3d)
        zf.writestr("3D/3dmodel.model", top_model)
        zf.writestr("Metadata/model_settings.config", model_settings)
        if layer_ranges:
            zf.writestr("Metadata/layer_config_ranges.xml", layer_ranges)
        zf.writestr("Metadata/slice_info.config", slice_info)
        # Embed template files verbatim.
        with open(proj_settings, "rb") as f:
            zf.writestr("Metadata/project_settings.config", f.read())
        if os.path.exists(filament_seq):
            with open(filament_seq, "rb") as f:
                zf.writestr("Metadata/filament_sequence.json", f.read())

        # Write the consolidated object_1.model that holds all sub-object meshes.
        # We open a single zip entry and stream every part's <object> block in.
        with zf.open("3D/Objects/object_1.model", "w", force_zip64=True) as fp:
            fp.write((
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<model unit="millimeter" xml:lang="en-US" '
                'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
                'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
                'requiredextensions="p">\n'
                ' <resources>\n'
            ).encode())
            for i, u, p in parts_meshes:
                fp.write(
                    f'  <object id="{i}" p:UUID="{u}" type="model">\n'
                    f'   <mesh>\n    <vertices>\n'.encode()
                )
                n_tri = 0
                for v1, v2, v3 in _stream_ascii_stl_triangles(p["stl_path"]):
                    for x, y, z in (v1, v2, v3):
                        fp.write(f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>\n'.encode())
                    n_tri += 1
                fp.write('    </vertices>\n    <triangles>\n'.encode())
                for t in range(n_tri):
                    base = t * 3
                    fp.write(f'     <triangle v1="{base}" v2="{base+1}" v3="{base+2}"/>\n'.encode())
                fp.write('    </triangles>\n   </mesh>\n  </object>\n'.encode())
            fp.write(' </resources>\n</model>\n'.encode())


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _closest_template_slot(hex_code: str, template_colours: list) -> int:
    """Return the 1-based slot in template_colours whose color is closest to
    hex_code (Euclidean distance in RGB). Returns 0 if list is empty.
    """
    if not template_colours:
        return 0
    target = _hex_to_rgb(hex_code)
    best_i, best_d = 0, float("inf")
    for i, c in enumerate(template_colours, start=1):
        try:
            r, g, b = _hex_to_rgb(c)
        except Exception:
            continue
        d = (r - target[0]) ** 2 + (g - target[1]) ** 2 + (b - target[2]) ** 2
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def classify_jar_stls(
    stl_paths: list,
    active_filaments: list = None,
    template_colours: list = None,
    name_to_extruder_override: dict = None,
) -> list:
    """Tag JAR-output STL paths with kind and a 1-based extruder index.

    `active_filaments`: ordered list of (name, hex) for active palette filaments.
    `template_colours`: ordered list of hex strings from the embedded
        project_settings.config's `filament_colour` array. When provided, each
        color STL is matched to the closest template slot by RGB distance,
        so e.g. White (#FFFFFF) maps to whichever template slot holds white
        — typically extruder 1 alongside the texture.
    `name_to_extruder_override`: optional explicit filament-name -> extruder
        mapping. Lithopainter uses this for PIXEstL's 1-AMS swap instructions,
        e.g. target colors after `Cyan-->Matte Ice Blue` inherit Cyan's slot.

    Texture/plate/margin always pin to extruder 1 (the texture/base material).
    Without `template_colours`, color extruders fall back to palette order
    starting at 2.
    """
    # Resolve name -> extruder via the template, or via palette order if no template.
    name_to_extruder = {}
    name_to_extruder_override = name_to_extruder_override or {}
    if active_filaments:
        for i, (fname, fhex) in enumerate(active_filaments):
            if template_colours:
                slot = _closest_template_slot(fhex, template_colours)
                if slot > 0:
                    name_to_extruder[fname] = slot
                    continue
            name_to_extruder[fname] = i + 2

    parts = []
    fallback_extr = 2
    for path in stl_paths:
        name = os.path.basename(path)
        stem = re.sub(r"\.stl$", "", name, flags=re.IGNORECASE)
        low = name.lower()

        if "plate" in low:
            kind, extr = "plate", 1
        elif "texture" in low:
            kind, extr = "texture", 1
        elif "margin" in low or "border" in low:
            kind, extr = "margin", 1
        else:
            kind = "color"
            filament_name = re.sub(r"^layer-", "", stem, flags=re.IGNORECASE)
            if filament_name in name_to_extruder_override:
                extr = name_to_extruder_override[filament_name]
            elif filament_name in name_to_extruder:
                extr = name_to_extruder[filament_name]
            else:
                extr = fallback_extr
                fallback_extr += 1

        parts.append({
            "name": stem,
            "stl_path": path,
            "extruder": extr,
            "kind": kind,
        })
    return parts


def read_template_filament_colours(template_dir: str) -> list:
    """Return the `filament_colour` array from the embedded project_settings.config,
    or [] if it can't be read.
    """
    import json
    path = os.path.join(template_dir, "project_settings.config")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return list(cfg.get("filament_colour") or [])
    except Exception:
        return []
