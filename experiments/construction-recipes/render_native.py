"""Render actual engine-exported meshes; never regenerate shapes from a second SDF.

Run in Blender: --scene SCENE.json (--native MODEL.obj | --parts-directory DIR)
--output DIR. Per-definition STL/OBJ input uses exact scene transforms.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def obj_meshes(path):
    vertices, groups, name = [], {}, None
    for line in path.read_text().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "v":
            vertices.append(tuple(float(v) for v in fields[1:4]))
        elif fields[0] in ("o", "g"):
            name = fields[1]
        elif fields[0] == "f":
            assert name is not None, "OBJ face lacks object identity"
            indices = []
            for field in fields[1:]:
                raw = int(field.split("/")[0])
                index = raw - 1 if raw > 0 else len(vertices) + raw
                assert 0 <= index < len(vertices), "OBJ index outside vertex list"
                indices.append(index)
            groups.setdefault(name, []).append(indices)
    result = []
    for name, faces in groups.items():
        used = sorted({v for face in faces for v in face})
        indices = {old: new for new, old in enumerate(used)}
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([vertices[i] for i in used], [],
                         [[indices[i] for i in face] for face in faces])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        result.append(obj)
    assert result and all(len(o.data.polygons) for o in result), "Empty OBJ import"
    return result


def material(name, rgb, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*rgb, 1)
    shader.inputs["Roughness"].default_value = 0.38
    shader.inputs["Metallic"].default_value = metallic
    return mat


def look_at(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def explode_and_render(scene_spec, objects, floor, cam, output):
    instances = {x["id"]: x for x in scene_spec["instances"]}
    points = [obj.matrix_world @ Vector(v) for obj in objects for v in obj.bound_box]
    lo = Vector([min(p[k] for p in points) for k in range(3)])
    hi = Vector([max(p[k] for p in points) for k in range(3)])
    center, span = (lo + hi) / 2, max(hi - lo)
    for i, obj in enumerate(objects):
        # Explode by source instance center, never modify vertex geometry.
        source_center = Vector(instances[obj.name]["transform"]["translation"])
        obj.location += (source_center - center) * 0.65
        obj.location.z += span * 0.18 * (i / max(1, len(objects) - 1))
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(v) for obj in objects for v in obj.bound_box]
    lo = Vector([min(p[k] for p in points) for k in range(3)])
    hi = Vector([max(p[k] for p in points) for k in range(3)])
    center, span = (lo + hi) / 2, max(hi - lo)
    # Reframe presentation context so lower exploded pieces cannot enter the floor.
    floor.location.z = lo.z - span * 0.006
    cam.location = center + Vector((1.45, -2.0, 1.35)) * span
    look_at(cam, center)
    cam.data.ortho_scale = span * 1.9
    bpy.context.scene.render.filepath = str(output / "exploded.png")
    bpy.ops.render.render(write_still=True)


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    scene_spec = json.loads(args.scene.read_text())
    instances = {x["id"]: x for x in scene_spec["instances"]}
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    input_hashes = {str(args.scene): digest(args.scene)}
    if args.native:
        objects = obj_meshes(args.native)
        input_hashes[str(args.native)] = digest(args.native)
        assert {o.name for o in objects} == set(instances), "Native OBJ object identities differ from source scene"
        method = "Oneirifact native BuildSceneAssembly OBJ (no shape regeneration)"
    else:
        objects = []
        definitions = {}
        for identity, inst in instances.items():
            definition = inst["definition_id"]
            if definition not in definitions:
                path = args.parts_directory / (definition + ".stl")
                if path.exists():
                    bpy.ops.wm.stl_import(filepath=str(path), forward_axis="Y", up_axis="Z")
                    obj = bpy.context.object
                else:
                    path = args.parts_directory / (definition + ".obj")
                    imported = obj_meshes(path)
                    assert len(imported) == 1, "Component OBJ must contain exactly one named mesh"
                    obj = imported[0]
                definitions[definition] = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                input_hashes[str(path)] = digest(path)
            obj = bpy.data.objects.new(identity, definitions[definition])
            bpy.context.collection.objects.link(obj)
            tx = inst["transform"]
            obj.location = tx["translation"]
            obj.rotation_mode = "XYZ"
            obj.rotation_euler = [math.radians(v) for v in tx["rotation"]]
            obj.scale = [tx["scale"]] * 3
            objects.append(obj)
        method = "Existing Oneirifact source-first compiled donor component meshes + exact source instance transforms"
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    palette = [material("clay red", (0.55, 0.11, 0.07)), material("ochre", (0.78, 0.42, 0.075)),
               material("muted blue", (0.08, 0.29, 0.47)), material("cedar", (0.38, 0.18, 0.075)),
               material("roof slate", (0.09, 0.14, 0.18)), material("hub orange", (0.65, 0.24, 0.055)),
               material("strut aluminum", (0.31, 0.40, 0.47), 0.72)]
    for i, obj in enumerate(objects):
        inst = instances[obj.name]
        obj["oneirifact_instance_id"] = obj.name
        obj["oneirifact_definition_id"] = inst["definition_id"]
        obj["oneirifact_definition_hash"] = inst.get("definition_hash", "UNPINNED_SOURCE_CANDIDATE")
        obj["oneirifact_source_scene_sha256"] = digest(args.scene)
        if "log" in inst["definition_id"]:
            color = palette[3]
        elif "roof" in inst["definition_id"]:
            color = palette[4]
        elif "hub" in inst["definition_id"]:
            color = palette[5]
        elif "rod" in inst["definition_id"]:
            color = palette[6]
        else:
            color = palette[i % 3]
        # Each occurrence may have a different display color, while source IDs remain unchanged.
        obj.data = obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(color)
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(v) for obj in objects for v in obj.bound_box]
    lo = Vector([min(p[k] for p in points) for k in range(3)])
    hi = Vector([max(p[k] for p in points) for k in range(3)])
    center, span = (lo + hi) / 2, max(hi - lo)
    assert 0 < span < 10, "Unexpected physical extent"
    source_bounds = {obj.name: {"vertices": len(obj.data.vertices), "polygons": len(obj.data.polygons),
        "bounds_m": [[min((obj.matrix_world @ Vector(v))[k] for v in obj.bound_box) for k in range(3)],
                     [max((obj.matrix_world @ Vector(v))[k] for v in obj.bound_box) for k in range(3)]]}
                     for obj in objects}
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(args.output / "assembly.glb"), export_format="GLB",
        use_selection=True, export_extras=True, export_yup=True)
    # Presentation floor/lights/camera are not included in the model-only GLB.
    bpy.ops.mesh.primitive_plane_add(size=span * 7, location=(center.x, center.y, lo.z - span * 0.006))
    floor = bpy.context.object
    floor.name = "presentation_floor"
    floor.data.materials.append(material("warm studio", (0.20, 0.22, 0.24)))
    if scene.world is None:
        scene.world = bpy.data.worlds.new("construction_studio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.28, 0.33, 0.4, 1)
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.4
    for name, offset, power, size in [("key", (1.6, -2.0, 2.8), 220, 2.0),
                                    ("fill", (-2.0, -0.4, 1.8), 110, 2.5),
                                    ("rim", (0.7, 2.2, 2.0), 175, 1.6)]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = power * span ** 2, "DISK", size * span
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        obj.location = center + Vector(offset) * span
        look_at(obj, center)
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    bpy.context.collection.objects.link(cam)
    cam.location = center + Vector((1.45, -2.0, 1.35)) * span
    look_at(cam, center)
    cam.data.type, cam.data.ortho_scale = "ORTHO", span * 1.58
    cam.data.clip_start, cam.data.clip_end = 0.00001, 100
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = False
    scene.cycles.seed = 251
    scene.render.threads_mode, scene.render.threads = "FIXED", 2
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1000, 800, 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = str(args.output / "assembled.png")
    scene["source_geometry_method"] = method
    scene["source_scene_sha256"] = digest(args.scene)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output / "assembly.blend"))
    bpy.ops.render.render(write_still=True)
    original = {o.name: o.location.copy() for o in objects}
    explode_and_render(scene_spec, objects, floor, cam, args.output)
    for obj in objects:
        obj.location = original[obj.name]
    receipt = {"schema": "oneirifact.construction-render/v1", "case": scene_spec["id"],
        "method": method, "blender": bpy.app.version_string, "length_unit": "m",
        "source_hashes": input_hashes, "instances": len(objects), "objects": source_bounds,
        "overall_bounds_m": [list(lo), list(hi)], "resolution": [1000, 800],
        "samples": args.samples, "geometry_changes": "NONE; display materials and exploded transforms only",
        "physical_fit": "NOT_QUALIFIED", "structural_loads": "NOT_QUALIFIED",
        "files": {p.name: digest(p) for p in args.output.iterdir() if p.is_file()}}
    (args.output / "render-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("CONSTRUCTION_RENDER " + json.dumps({k: receipt[k] for k in ("case", "method", "blender", "instances", "overall_bounds_m")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, required=True)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--native", type=Path)
    input_group.add_argument("--parts-directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=32)
    main(parser.parse_args(sys.argv[sys.argv.index("--") + 1:]))
