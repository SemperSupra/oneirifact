#!/usr/bin/env python3
"""Oneirifact public original procedural pavilion study, rendered by REAL Cycles.

This is independent new parametric geometry for visual RDT&E. It does not
contain or attest private Oneirifact foundry.Graph, CSG, scene assembly, CPE,
third-party content, personal media, or product-source publication rights.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys

SCHEMA = "oneirifact.public-procedural-raytrace-study/v0.1"
PROFILE_IDS = ("pavilion-day", "pavilion-night", "pavilion-tall", "pavilion-plan")
OUTPUT_SCHEMA = "oneirifact.public-cycles-render-receipt/v0.1"
WIDTH, HEIGHT = 720, 480


def checksum(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _no_constant(token):
    raise ValueError("nonfinite JSON token: " + token)


def load_specs(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("spec path must be a regular file")
    raw = path.read_bytes()
    if len(raw) > 16000:
        raise ValueError("spec size exceeds public study bound")
    document = json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    if not isinstance(document, dict) or set(document) != {"schema", "notice", "profiles"}:
        raise ValueError("unsupported or ambiguous study document")
    if document["schema"] != SCHEMA or not isinstance(document["notice"], str):
        raise ValueError("unsupported public study schema")
    if not isinstance(document["profiles"], list) or len(document["profiles"]) != 4:
        raise ValueError("required four independent study profiles")
    observed = []
    for profile in document["profiles"]:
        if not isinstance(profile, dict) or set(profile) != {
            "id", "label", "height_m", "roof_radius_m", "mode", "camera", "samples"
        }:
            raise ValueError("invalid public study profile fields")
        if not isinstance(profile["id"], str) or profile["id"] not in PROFILE_IDS:
            raise ValueError("unknown study profile")
        if not isinstance(profile["label"], str) or len(profile["label"]) > 64:
            raise ValueError("invalid display label")
        if profile["mode"] not in ("day", "night") or profile["camera"] not in ("hero", "overview"):
            raise ValueError("unsupported light/camera")
        if not isinstance(profile["samples"], int) or isinstance(profile["samples"], bool) or not 8 <= profile["samples"] <= 48:
            raise ValueError("samples out of bounds")
        for name, minimum, maximum in (("height_m", 3, 5), ("roof_radius_m", 3, 3.8)):
            value = profile[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("nonfinite or nonnumeric profile")
            if not minimum <= value <= maximum:
                raise ValueError("profile dimension out of range")
        if WIDTH * HEIGHT * profile["samples"] > 18_000_000:
            raise ValueError("sample pixel budget exceeded")
        observed.append(profile["id"])
    if tuple(observed) != PROFILE_IDS:
        raise ValueError("study profiles missing, repeated or unordered")
    if (
        document["profiles"][0]["height_m"] != document["profiles"][1]["height_m"]
        or document["profiles"][0]["roof_radius_m"] != document["profiles"][1]["roof_radius_m"]
        or document["profiles"][0]["camera"] != document["profiles"][1]["camera"]
        or document["profiles"][0]["height_m"] == document["profiles"][2]["height_m"]
    ):
        raise ValueError("variants do not isolate intended structural and light changes")
    return document, raw


def _output_path(raw: str, profile_id: str) -> Path:
    target = Path(os.path.abspath(raw))
    if not target.is_dir() or target.is_symlink():
        raise ValueError("render output directory must preexist and not be a symlink")
    if os.name != "nt" and target.stat().st_mode & 0o077:
        raise ValueError("render output directory must be private 0700")
    for name in (profile_id + ".png", profile_id + ".json"):
        if (target / name).exists() or (target / name).is_symlink():
            raise ValueError("will not overwrite render output")
    return target


def render(profile: dict, source_bytes: bytes, output: Path) -> dict:
    import bpy
    from mathutils import Vector

    if tuple(bpy.app.version[:3]) != (5, 2, 4):
        raise RuntimeError("this public study requires verified Blender 5.2.4 LTS")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = profile["samples"]
    scene.cycles.seed = 191
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.filepath = str(output / (profile["id"] + ".png"))
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    object_names = []
    def named(obj, name, material=None):
        obj.name = name
        object_names.append(name)
        if material is not None:
            obj.data.materials.append(material)
        return obj

    def material(name, color, metallic=0.0, roughness=0.35, transmission=0.0, emission=0.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            raise RuntimeError("Principled BSDF shader missing")
        bsdf.inputs["Base Color"].default_value = (*color, 1)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
        if emission:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (*color, 1)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission
        m.diffuse_color = (*color, 1)
        return m

    evening = profile["mode"] == "night"
    stone = material("warm limestone", (0.68, 0.63, 0.56), roughness=0.78)
    dark = material("obsidian graphite", (0.065, 0.092, 0.13), metallic=0.55, roughness=0.32)
    copper = material("oxidized brushed copper", (0.52, 0.30, 0.16), metallic=0.78, roughness=0.22)
    gold = material("champagne brass", (0.78, 0.52, 0.22), metallic=0.68, roughness=0.22)
    glass = material("blue mineral glass", (0.085, 0.37, 0.46), metallic=0.15, roughness=0.18, transmission=0.32)
    water = material("mirror reflecting pool", (0.04, 0.22, 0.26), metallic=0.7, roughness=0.10)
    glowing = material("faceted deep mineral crystal", (0.06, 0.30, 0.62) if evening else (0.065, 0.23, 0.52),
                       metallic=0.24, roughness=0.16, emission=0.82 if evening else 0.12)
    illuminated = material("warm embedded path lighting", (1.0, 0.48, 0.12), emission=8.0 if evening else 0.35)
    background = material("sand field", (0.24, 0.25, 0.23), roughness=0.95)

    def cylinder(name, radius, depth, pos, mat, vertices=96):
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=pos)
        return named(bpy.context.object, name, mat)

    def sphere(name, radius, pos, mat, ico=False):
        if ico:
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=pos)
        else:
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=radius, location=pos)
        return named(bpy.context.object, name, mat)

    def torus(name, major, minor, z, mat):
        bpy.ops.mesh.primitive_torus_add(major_segments=96, minor_segments=12,
                                         major_radius=major, minor_radius=minor, location=(0, 0, z))
        return named(bpy.context.object, name, mat)

    def beam(name, a, b, radius, mat):
        start, end = Vector(a), Vector(b)
        direction = end - start
        if direction.length < 1e-6:
            raise ValueError("zero-length structural beam")
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=direction.length,
                                            location=(start + end) / 2)
        obj = bpy.context.object
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
        return named(obj, name, mat)

    def panel(name, verts, mat):
        mesh = bpy.data.meshes.new(name + "_mesh")
        mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        return named(obj, name, mat)

    height = profile["height_m"]
    roof_radius = profile["roof_radius_m"]

    # Designed from first principles: a radial pavilion built from derived
    # geometric elements, not an imported model or private feature graph.
    cylinder("limestone foundation", 4.25, 0.25, (0, 0, -0.18), stone)
    cylinder("copper plinth", 3.83, 0.12, (0, 0, -0.02), copper)
    cylinder("inner terrace", 3.48, 0.10, (0, 0, 0.08), stone)
    cylinder("central reflecting pool", 1.53, 0.035, (0, 0, 0.15), water)
    cylinder("pool inner island", 0.78, 0.06, (0, 0, 0.18), dark)
    torus("foundation perimeter ring", 3.70, 0.037, 0.11, gold)
    torus("reflecting pool rim", 1.54, 0.039, 0.20, copper)

    # Radial portal arches preserve stable, independently named occurrences.
    n = 8
    for i in range(n):
        theta = 2 * math.pi * i / n
        ct, st = math.cos(theta), math.sin(theta)
        base_radius = 3.02
        cylinder(f"portal footing {i:02}", 0.19, 0.16, (base_radius * ct, base_radius * st, 0.22), dark, 20)
        points = []
        for j in range(13):
            t = j / 12
            distance = base_radius - (base_radius - 1.18) * (1 - math.cos(t * math.pi / 2))
            z = 0.37 + (height - 0.37) * math.sin(t * math.pi / 2)
            points.append((distance * ct, distance * st, z))
        for j in range(len(points) - 1):
            beam(f"arched rib {i:02} segment {j:02}", points[j], points[j + 1], 0.065, copper)
        # Individual seats and path lights remain separately addressable geometry.
        angle = theta + math.pi / n
        rr = 2.85
        cylinder(f"path marker {i:02}", 0.070, 0.033, (rr * math.cos(angle), rr * math.sin(angle), 0.158), illuminated, 20)

    torus("compression ring outer", roof_radius, 0.072, height - 0.51, gold)
    torus("oculus compression ring", 1.18, 0.075, height, gold)
    torus("secondary lantern ring", 1.0, 0.045, height - 0.14, glass)

    # Eight translucent roof leaves make the solid-vs-glass ray paths visible.
    for i in range(n):
        a = (i + 0.10) * 2 * math.pi / n
        b = (i + 0.90) * 2 * math.pi / n
        outer = roof_radius
        inner = 1.16
        corners = [
            (outer * math.cos(a), outer * math.sin(a), height - 0.49),
            (outer * math.cos(b), outer * math.sin(b), height - 0.49),
            (inner * math.cos(b), inner * math.sin(b), height + 0.03),
            (inner * math.cos(a), inner * math.sin(a), height + 0.03),
        ]
        panel(f"translucent roof leaf {i:02}", corners, glass)

    # Floating source-independent faceted sculpture in central oculus.
    sphere("suspended prismatic mineral", 0.66, (0, 0, 1.83), glowing, ico=True)
    for i in range(3):
        z = 1.25 + i * 0.34
        torus(f"sculpture orbital ring {i:02}", 0.83 + 0.10 * i, 0.018, z, gold)
    cylinder("prismatic anchor", 0.06, 0.58, (0, 0, height - 0.36), gold, 16)

    bpy.ops.mesh.primitive_plane_add(size=250, location=(0, 0, -0.39))
    named(bpy.context.object, "neutral evaluation ground", background)

    # Two independently positioned area lights and an actual Cycles sun emitter.
    def area(name, position, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = position
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        obj.rotation_euler = (Vector((0, 0, 1.0)) - obj.location).to_track_quat("-Z", "Y").to_euler()

    area("large softbox daylight", (-5, -6, 9), 1150 if not evening else 320, 8, (0.88, 0.94, 1.0))
    area("reflecting fill", (5, 2, 5), 480 if not evening else 220, 5, (0.85, 0.82, 0.78))
    if scene.world is None:
        scene.world = bpy.data.worlds.new("original study environment")
    scene.world.color = (0.085, 0.1, 0.125) if not evening else (0.018, 0.025, 0.05)
    if scene.world:
        scene.world.use_nodes = True
        background_node = scene.world.node_tree.nodes.get("Background")
        if background_node:
            background_node.inputs["Color"].default_value = (0.10, 0.17, 0.30, 1) if evening else (0.52, 0.59, 0.67, 1)
            background_node.inputs["Strength"].default_value = 0.15 if evening else 0.65

    # Fixed cinematic controls are fully disclosed in the public profile.
    if profile["camera"] == "overview":
        camera_pos = (7.8, -9.0, 11.4)
        target = (0, 0, 1.1)
    else:
        camera_pos = (8.0, -10.6, 5.5)
        target = (0, 0, 1.7)
    camera_data = bpy.data.cameras.new("evaluation camera")
    camera_obj = bpy.data.objects.new("evaluation camera", camera_data)
    scene.collection.objects.link(camera_obj)
    camera_obj.location = camera_pos
    camera_obj.rotation_euler = (Vector(target) - camera_obj.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 10.6 if profile["camera"] == "hero" else 12.2
    scene.camera = camera_obj

    # Actual engine execution: no pre-rendered images or raster substitutes.
    bpy.ops.render.render(write_still=True)
    image_path = output / (profile["id"] + ".png")
    pixels = image_path.read_bytes()
    if not pixels.startswith(b"\x89PNG\r\n\x1a\n") or len(pixels) < 1000:
        raise RuntimeError("real Cycles renderer did not produce a PNG")

    if len(object_names) != len(set(object_names)) or len(object_names) < 100:
        raise RuntimeError("procedural structure or occurrence IDs not retained")
    receipt = {
        "schema": OUTPUT_SCHEMA,
        "status": "ACTUAL_BLENDER_CYCLES_CPU_RENDER",
        "source_kind": "ORIGINAL_PUBLIC_PARAMETRIC_SCENE_NOT_PRIVATE_ONEIRIFACT_ENGINE",
        "profile": profile,
        "camera_position": list(camera_pos),
        "resolution": [WIDTH, HEIGHT],
        "samples": profile["samples"],
        "seed": 191,
        "blender_version": bpy.app.version_string,
        "engine": "CYCLES",
        "device": "CPU",
        "spec_sha256": checksum(source_bytes),
        "generator_sha256": checksum(Path(__file__).read_bytes()),
        "image_sha256": checksum(pixels),
        "image_bytes": len(pixels),
        "object_count": len(object_names),
        "object_names_sha256": checksum(("\n".join(object_names) + "\n").encode()),
        "object_ids": object_names,
        "limits": [
            "Original stand-alone public procedural design, not private Foundry graph/CSG",
            "No durable source CAS or independent source-to-Blender geometry fidelity",
            "CPU Cycles representative visual RDT&E only, not device/browser performance",
            "No CPE, external model, third-party geometry, protected asset, or personal media",
        ]
    }
    receipt_path = output / (profile["id"] + ".json")
    fd = os.open(str(receipt_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return receipt


def main(argv: list[str]) -> None:
    if "--" not in argv or len(argv[argv.index("--") + 1:]) != 3:
        raise SystemExit("Usage: blender --background --python pavilion.py -- SPECS.json PROFILE_ID EXISTING_OUTPUT_DIR")
    spec_name, profile_id, out_name = argv[argv.index("--") + 1:]
    document, raw = load_specs(Path(spec_name))
    if profile_id not in PROFILE_IDS:
        raise ValueError("unknown requested profile")
    profile = next(x for x in document["profiles"] if x["id"] == profile_id)
    receipt = render(profile, raw, _output_path(out_name, profile_id))
    print("PUBLIC_REAL_CYCLES_RENDER_PASS", json.dumps({
        "id": profile_id,
        "pixels": receipt["resolution"],
        "object_count": receipt["object_count"],
        "image_sha256": receipt["image_sha256"]
    }, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv)
