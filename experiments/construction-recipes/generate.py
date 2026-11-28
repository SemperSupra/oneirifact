"""Original canonical construction recipes; no alternative geometry evaluator.

Primitive source uses a 10x construction frame and a final 0.1 uniform scale.
Actual geometry must be produced by Oneirifact's native graph/scene APIs.
Inspired by the original public R205 component layout, with independently
authored parameterized families, useful builds, connector plans and BOMs.
No manufacturer dimensions, clutch fit or structural certification is claimed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path


class Recipe:
    def __init__(self, name):
        self.name, self.features = name, []

    def add(self, op, params=None, inputs=None):
        identity = f"f{len(self.features)}"
        node = {"id": identity, "op": op}
        if params is not None:
            node["params"] = params
        if inputs:
            node["inputs"] = inputs
        self.features.append(node)
        return identity

    def box(self, x, y, z):
        return self.add("box", dict(width=x * 10, depth=y * 10, height=z * 10))

    def cylinder(self, radius, height):
        return self.add("cylinder", dict(radius=radius * 10, height=height * 10))

    def sphere(self, radius):
        return self.add("sphere", dict(radius=radius * 10))

    def translate(self, node, xyz):
        return self.add("translate", dict(zip("xyz", (v * 10 for v in xyz))), [node])

    def rotate(self, node, xyz):
        return self.add("rotate", dict(zip(("rx", "ry", "rz"), xyz)), [node])

    def boolean(self, left, right, operation):
        return self.add(operation, inputs=[left, right])

    def finish(self, root):
        root = self.add("scale", {"factor": 0.1}, [root])
        return {"schema": "oneirifact.graph/v0.1", "name": self.name,
                "unit": "m", "detail": 32, "root": root, "features": self.features}


def brick(nx, ny, height=0.0096):
    name = f"brick_{nx}x{ny}"
    recipe = Recipe(name)
    pitch, wall = 0.008, 0.0015
    width, depth = nx * pitch - 0.0002, ny * pitch - 0.0002
    root = recipe.box(width, depth, height)
    cutter = recipe.box(width - 2 * wall, depth - 2 * wall, height - wall + 0.0004)
    cutter = recipe.translate(cutter, [0, 0, -wall / 2 - 0.0002])
    root = recipe.boolean(root, cutter, "difference")
    stud = recipe.cylinder(0.0024, 0.002)
    for ix in range(nx):
        for iy in range(ny):
            center = [(ix - (nx - 1) / 2) * pitch, (iy - (ny - 1) / 2) * pitch,
                      height / 2 + 0.0008]
            root = recipe.boolean(root, recipe.translate(stud, center), "union")
    # Central underside tubes are source geometry, not a tested clutch mechanism.
    for ix in range(nx - 1):
        for iy in range(ny - 1):
            outer = recipe.cylinder(0.0032, height - wall + 0.0002)
            inner = recipe.cylinder(0.0024, height - wall + 0.0006)
            tube = recipe.boolean(outer, inner, "difference")
            tube = recipe.translate(tube, [(ix - (nx - 2) / 2) * pitch,
                                           (iy - (ny - 2) / 2) * pitch, -wall / 2 + 0.0001])
            root = recipe.boolean(root, tube, "union")
    return recipe.finish(root), {"family": "studded hollow block", "pitch_m": pitch,
        "stud_grid": [nx, ny], "body_size_m": [width, depth, height],
        "wall_m": wall, "stud_radius_m": 0.0024, "tube_wall_m": 0.0008,
        "physical_fit": "NOT_QUALIFIED"}


def notched_log():
    recipe = Recipe("notched_log")
    root = recipe.box(0.064, 0.008, 0.008)
    cut = recipe.box(0.0084, 0.010, 0.0042)
    for x in [-0.024, 0.024]:
        root = recipe.boolean(root, recipe.translate(cut, [x, 0, -0.0021]), "difference")
    return recipe.finish(root), {"family": "rectangular notched beam", "length_m": 0.064,
        "cross_section_m": [0.008, 0.008], "notch_centers_m": [-0.024, 0.024],
        "notch_width_m": 0.0084, "course_step_m": 0.004,
        "nominal_lateral_clearance_m": 0.0004, "physical_fit": "NOT_QUALIFIED"}


def flat_panel():
    recipe = Recipe("roof_panel")
    return recipe.finish(recipe.box(0.038, 0.072, 0.003)), {
        "family": "flat panel", "size_m": [0.038, 0.072, 0.003]}


def axis_rotation(vector):
    length = math.sqrt(sum(v * v for v in vector))
    return [0, math.degrees(math.acos(max(-1, min(1, vector[2] / length)))),
            math.degrees(math.atan2(vector[1], vector[0]))]


def instance(identity, definition, xyz, rotation=(0, 0, 0)):
    return {"id": identity, "definition_id": definition, "composition_mode": "scene_assembly",
            "transform": {"translation": list(xyz), "rotation": list(rotation), "scale": 1}}


def definition(identity, graph):
    return {"schema": "oneirifact.component/v0.1", "id": identity,
            "name": identity.replace("_", " "), "unit": "m", "graph": graph}


def save_case(root, name, definitions, parts, plan):
    folder = root / name
    (folder / "components").mkdir(parents=True, exist_ok=True)
    for identity, (graph, metadata) in definitions.items():
        (folder / "components" / f"{identity}.json").write_text(json.dumps(definition(identity, graph), indent=2) + "\n")
        (folder / f"{identity}.graph.json").write_text(json.dumps(graph, indent=2) + "\n")
    scene = {"schema": "oneirifact.scene/v0.1", "id": name, "name": name.replace("_", " "),
             "composition_mode": "scene_assembly", "instances": parts}
    (folder / "scene.candidate.json").write_text(json.dumps(scene, indent=2) + "\n")
    plan.update({"schema": "oneirifact.construction-review/v1", "id": name,
        "length_unit": "m", "rotation_unit": "degrees", "euler_order": "XYZ",
        "geometry_authority": "canonical feature graphs evaluated by native Oneirifact",
        "definition_pin_status": "COMPUTE_WITH_NATIVE_COMPONENT_HASH_BEFORE_ADMISSION",
        "bom": dict(sorted(Counter(p["definition_id"] for p in parts).items())),
        "instance_count": len(parts), "families": {k: v[1] for k, v in definitions.items()},
        "physical_fit": "NOT_QUALIFIED", "structural_loads": "NOT_QUALIFIED"})
    (folder / "assembly-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return {"case": name, "instances": len(parts), "definitions": len(definitions)}


def generate(out):
    out.mkdir(parents=True, exist_ok=False)
    results = []
    parts = []
    # Two repeatable piers and a single spanning beam; a useful subassembly.
    for side, x in [("left", -0.024), ("right", 0.024)]:
        for course in range(3):
            parts.append(instance(f"pier_{side}_{course}", "brick_2x2", [x, 0, 0.0048 + course * 0.0096]))
    parts.append(instance("bridge_deck", "brick_8x2", [0, 0, 0.0048 + 3 * 0.0096]))
    for x in [-0.024, 0, 0.024]:
        parts.append(instance(f"parapet_{len(parts)}", "brick_2x2", [x, 0, 0.0048 + 4 * 0.0096]))
    results.append(save_case(out, "brick_bridge", {"brick_2x2": brick(2, 2), "brick_8x2": brick(8, 2)}, parts,
        {"description": "Ten-piece hollow studded-block bridge with two reusable piers and a spanning beam.",
         "assembly_sequence": ["Place two piers on a six-stud center spacing.",
            "Stack three two-by-two blocks per pier.", "Seat the eight-by-two beam on the two piers.",
            "Place three two-by-two parapet blocks on the beam."],
         "construction_invariants": {"stud_pitch_m": 0.008, "course_height_m": 0.0096,
             "pier_center_separation_m": 0.048, "beam_support_overlap_m": 0.0158},
         "connection_scope": "Source lattice alignment; meshed clearance and mechanical retention remain separate."}))

    parts = []
    for course in range(8):
        z = 0.004 + course * 0.004
        if course % 2 == 0:
            parts.append(instance(f"back_{course}", "notched_log", [0, 0.024, z]))
            if course == 0:
                parts.append(instance("front_sill", "notched_log", [0, -0.024, z]))
        else:
            for side, x in [("left", -0.024), ("right", 0.024)]:
                parts.append(instance(f"side_{side}_{course}", "notched_log", [x, 0, z], [0, 0, 90]))
    angle = math.radians(30)
    wall_top, half_panel, half_thickness = 0.036, 0.019, 0.0015
    ridge = wall_top + 0.024 * math.tan(angle) + half_thickness / math.cos(angle)
    for side, sign in [("left", -1), ("right", 1)]:
        parts.append(instance(f"roof_{side}", "roof_panel",
            [sign * half_panel * math.cos(angle), 0, ridge - half_panel * math.sin(angle)], [0, sign * 30, 0]))
    results.append(save_case(out, "log_cabin", {"notched_log": notched_log(), "roof_panel": flat_panel()}, parts,
        {"description": "Open-front cabin of thirteen crossed notched beams and two pitched roof panels.",
         "assembly_sequence": ["Place the front sill and rear beam.",
             "Alternate perpendicular paired side beams and rear beams at half-height courses.",
             "Place the two thirty-degree roof panels on the side walls."],
         "construction_invariants": {"notch_axis_spacing_m": 0.048, "wall_axis_spacing_m": 0.048,
             "course_step_m": 0.004, "roof_ridge_m": ridge, "wall_top_m": wall_top},
         "connection_scope": "Nominal half-lap notch alignment; roof seam and structural loading unqualified."}))

    side = 0.060
    points = [[-side / 2, -side / (2 * math.sqrt(3)), 0.006],
              [side / 2, -side / (2 * math.sqrt(3)), 0.006],
              [0, side / math.sqrt(3), 0.006],
              [0, 0, 0.006 + side * math.sqrt(2 / 3)]]
    recipe = Recipe("frame_rod")
    defs = {"frame_rod": (recipe.finish(recipe.cylinder(0.0016, side - 0.003)),
                         {"family": "cylindrical strut", "radius_m": 0.0016,
                          "length_m": side - 0.003})}
    parts, edges, sockets = [], [], []
    for i, p in enumerate(points):
        recipe = Recipe(f"socket_hub_{i}")
        shape = recipe.sphere(0.006)
        for j, q in enumerate(points):
            if i == j:
                continue
            axis = [(q[k] - p[k]) / side for k in range(3)]
            cut = recipe.cylinder(0.0018, 0.0075)
            cut = recipe.rotate(cut, axis_rotation(axis))
            cut = recipe.translate(cut, [v * 0.004 for v in axis])
            shape = recipe.boolean(shape, cut, "difference")
            sockets.append({"hub": i, "toward": j, "axis": axis, "radius_m": 0.0018,
                            "start_distance_m": 0.00025, "end_distance_m": 0.00775})
        defs[f"socket_hub_{i}"] = (recipe.finish(shape), {"family": "three-socket spherical hub",
            "radius_m": 0.006, "socket_radius_m": 0.0018, "radial_clearance_m": 0.0002})
        parts.append(instance(f"hub_{i}", f"socket_hub_{i}", p))
        for j in range(i + 1, len(points)):
            q = points[j]
            vector = [q[k] - p[k] for k in range(3)]
            center = [(q[k] + p[k]) / 2 for k in range(3)]
            parts.append(instance(f"rod_{i}_{j}", "frame_rod", center, axis_rotation(vector)))
            edges.append({"rod": f"rod_{i}_{j}", "hubs": [i, j], "center_distance_m": side,
                          "endpoint_inset_m": 0.0015})
    results.append(save_case(out, "rod_hub_frame", defs, parts,
        {"description": "Ten-piece tetrahedral frame: six equal struts and four three-socket hubs.",
         "assembly_sequence": ["Assemble the triangular base from three hubs and three struts.",
             "Insert three rising struts.", "Seat the apex hub on all three upper rod ends."],
         "hub_centers_m": points, "socket_axes": sockets, "edges": edges,
         "connection_scope": "Exact endpoint-to-socket axis alignment and nominal clearance; friction, rigidity and loads unqualified."}))
    manifest = {"schema": "oneirifact.construction-recipes/v1", "cases": results,
        "source_authority": "Native Oneirifact; this script constructs JSON only.",
        "files": {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(out.rglob("*")) if p.is_file()}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
