"""Falsify a source-only fixed-axis talar-dome ankle proxy.

The numerical gate was chosen after a local exploratory source preflight. This
public replay is reproducible negative evidence, not preregistered validation.
No skin points inform the fit and no replacement registration is generated.
"""
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "r240" / "registration"))
from ct_skin import sha, need, xform

CT_SHA = "f9e0e39a5591705aa73509e4239a4a9652d57fe3bdbb010b120b5366443ede8a"
DIAGNOSTIC_SHA = "441e272b88b0f8c8557d936ca0f0ba9f61fb2ddd967abb495f3bd4f0ea339cf1"
CRITERIA = {"radius_min_mm": 10., "radius_max_mm": 50.,
            "heldout_rms_max_mm": 3., "heldout_max_max_mm": 8.,
            "minimum_training_vertices": 300, "minimum_heldout_vertices": 100}


def unit(v):
    length = np.linalg.norm(v)
    need(length > 1e-9, "degenerate source direction")
    return v / length


def circle(points):
    center = points.mean(0)
    q = points - center
    x = np.linalg.lstsq(np.column_stack((2 * q, np.ones(len(q)))), (q * q).sum(1), rcond=None)[0]
    initial = np.r_[x[:2] + center, np.sqrt(max(0, x[2] + np.dot(x[:2], x[:2])))]
    fit = least_squares(lambda p: np.linalg.norm(points - p[:2], axis=1) - p[2],
                        initial, loss="soft_l1", f_scale=.001, max_nfev=100)
    need(fit.success and np.isfinite(fit.x).all(), "numerical circle solver failed")
    return fit.x


def error(points, fit):
    residual = abs(np.linalg.norm(points - fit[:2], axis=1) - fit[2]) * 1000
    return {"rms_mm": float(np.sqrt(np.mean(residual ** 2))),
            "p95_mm": float(np.quantile(residual, .95)), "max_mm": float(residual.max())}


def main(ct, diagnostic, out):
    need(sha(ct.read_bytes()) == CT_SHA and sha(diagnostic.read_bytes()) == DIAGNOSTIC_SHA,
         "exact source and prior diagnostic archive SHA")
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(ct) as z, zipfile.ZipFile(diagnostic) as dz:
        raw = z.read("female-ct-leg-animation.glb")
        previous = json.loads(z.read("receipt.json"))
        evidence = json.loads(dz.read("receipt.json"))
        need(sha(raw) == previous["models"]["animated"], "source GLB SHA")
        need(evidence["geometry_changed"] is False, "prior diagnostic changed source")
        source = trimesh.load(io.BytesIO(raw), file_type="glb", force="scene", process=False)
        (out / "ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt") +
            b"\nR243: unchanged same-donor tibia, fibula and talus source witness; failed geometric ankle proxy, no replacement anatomical registration.\n")
    selected = {}
    names = sorted(source.graph.nodes_geometry)
    def original(suffix):
        keys = [n for n in names if n.endswith("_" + suffix)]
        need(len(keys) == 1, "unambiguous actual source label " + suffix)
        name = keys[0]
        m, geometry = source.graph[name]
        mesh = source.geometry[geometry].copy()
        mesh.apply_transform(m)
        selected[name] = mesh
        return name, mesh
    results, views, arrays = [], [], {}
    for side, short in (("LEFT", "L"), ("RIGHT", "R")):
        tib_name, tib_mesh = original("TIBIA_" + side)
        fib_name, fib_mesh = original("FIBULA_" + side)
        tal_name, tal_mesh = original("TALUS_" + side)
        tib, fib, tal = tib_mesh.vertices, fib_mesh.vertices, tal_mesh.vertices
        knee = source.graph["shin_" + short][0][:3, 3]
        old = tib[tib[:, 1] < tib[:, 1].min() + .015].mean(0)
        up = unit(knee - old)
        level = float(tal[:, 1].max() + .015)
        bands = [v[abs(v[:, 1] - level) < .015] for v in (tib, fib)]
        need(min(map(len, bands)) > 100, "distal shaft source band too small")
        transverse = bands[1].mean(0) - bands[0].mean(0)
        axis = unit(transverse - up * np.dot(transverse, up))
        ap = unit(np.cross(axis, up))
        normal = unit(np.cross(ap, axis))
        basis = np.stack((axis, normal, ap), axis=1)
        need(abs(np.linalg.det(basis) - 1) < 1e-10, "source proxy frame orientation")
        origin = tal.mean(0)
        coord = (tal - origin) @ basis
        upper = coord[:, 1] >= np.median(coord[:, 1])
        upper_ids = np.flatnonzero(upper)
        distances = cKDTree(tib).query(tal[upper_ids])[0]
        threshold = float(np.quantile(distances, .35))
        patch_ids = upper_ids[distances <= threshold]
        q = coord[patch_ids]
        split = float(np.quantile(q[:, 2], .30))
        train_mask = q[:, 2] >= split
        train, held = q[train_mask], q[~train_mask]
        need(len(train) >= CRITERIA["minimum_training_vertices"] and
             len(held) >= CRITERIA["minimum_heldout_vertices"], "source holdout size")
        fitted = circle(train[:, 1:])
        fit_error, held_error = error(train[:, 1:], fitted), error(held[:, 1:], fitted)
        center_local = np.r_[np.median(q[:, 0]), fitted[:2]]
        candidate = origin + basis @ center_local
        radius = float(fitted[2] * 1000)
        criteria = {"radius_range": CRITERIA["radius_min_mm"] <= radius <= CRITERIA["radius_max_mm"],
                    "heldout_rms": held_error["rms_mm"] <= CRITERIA["heldout_rms_max_mm"],
                    "heldout_max": held_error["max_mm"] <= CRITERIA["heldout_max_max_mm"]}
        row = {"side": side, "source_ids": {"tibia": tib_name, "fibula": fib_name, "talus": tal_name},
               "source_vertices": {"tibia": len(tib), "fibula": len(fib), "talus": len(tal)},
               "axis_band_center_y_m": level, "axis_band_half_width_m": .015,
               "axis_band_vertices": list(map(len, bands)),
               "axis_source_unit_direction": axis.tolist(), "axis_units": "dimensionless",
               "source_frame_origin_m": origin.tolist(), "source_frame_basis": basis.tolist(),
               "superior_talus_vertices": int(upper.sum()), "opposing_tibia_vertex_distance_threshold_mm": threshold * 1000,
               "patch_vertices": len(q), "training_vertices": len(train), "heldout_vertices": len(held),
               "split_source_ap_m": split, "train_fit_radius_mm": radius,
               "train_error": fit_error, "heldout_error": held_error,
               "prior_tibial_centroid_proxy_m": old.tolist(),
               "failed_cylinder_center_proxy_m": candidate.tolist(),
               "center_shift_mm": ((candidate - old) * 1000).tolist(),
               "geometric_checks": criteria, "geometric_screen_pass": all(criteria.values()),
               "status": "GEOMETRIC_HYPOTHESIS_ONLY" if all(criteria.values()) else "REJECT_FIXED_AXIS_PROXY"}
        results.append(row)
        arrays[side + "_source_patch_vertex_ids"] = patch_ids
        arrays[side + "_training_mask"] = train_mask
        arrays[side + "_patch_points_m"] = tal[patch_ids]
        arrays[side + "_source_frame_coordinates_m"] = q
        views.append((side, row, tib, fib, tal, tal[patch_ids], train_mask, q, fitted, old, candidate))
    # Product contains only actual unchanged meshes from the source. Failed
    # centers live in the receipt; no synthetic bone or changed joint is emitted.
    witness = trimesh.Scene(base_frame="world")
    for name, mesh in selected.items():
        witness.add_geometry(mesh.copy(), node_name=name, geom_name=name)
    packed = witness.export(file_type="glb")
    (out / "female-ankle-source-witness.glb").write_bytes(packed)
    decoded = trimesh.load(io.BytesIO(packed), file_type="glb", force="scene", process=False)
    need(set(decoded.graph.nodes_geometry) == set(selected), "source witness identity")
    replay = []
    for name, mesh in selected.items():
        matrix, geometry = decoded.graph[name]
        got = decoded.geometry[geometry]
        need(np.array_equal(mesh.faces, got.faces), "source witness triangle preservation")
        vertices = xform(got.vertices, matrix)
        err = float(np.max(np.linalg.norm(vertices - mesh.vertices, axis=1)))
        need(err < 2e-6, "source witness GLB transport")
        replay.append({"source_id": name, "vertices": len(vertices), "triangles": len(mesh.faces), "max_error_m": err})
    np.savez_compressed(out / "source-patches-and-split.npz", **arrays)
    image = Image.new("RGB", (1500, 1050), "#14212b")
    draw = ImageDraw.Draw(image)
    fontpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    title = ImageFont.truetype(fontpath, 23)
    font = ImageFont.truetype(fontpath, 18)
    draw.text((22, 16), "Actual female ankle source — fixed-axis cylinder hypothesis rejected", font=title, fill="white")
    draw.text((22, 50), "Blue: tibia/fibula. Grey: talus. Gold: training patch. Red: contiguous held-out patch. No skin-based fitting.", font=font, fill="#c3d2da")
    for col, (side, row, tib, fib, tal, patch, train_mask, q, fitted, old, candidate) in enumerate(views):
        left = col * 750
        draw.text((left + 24, 95), side + f" | held-out RMS {row['heldout_error']['rms_mm']:.2f} mm / max {row['heldout_error']['max_mm']:.2f} mm", font=font, fill="#ffb2a4")
        low, high = tal[:, 1].min() - .015, tal[:, 1].max() + .075
        geometry = [v[(v[:, 1] > low) & (v[:, 1] < high)] for v in (tib, fib, tal)]
        center = tal.mean(0)
        def projected(v):
            return np.column_stack((v[:, 0] + .45 * v[:, 2], v[:, 1]))
        shift = projected(center[None, :])[0]
        scale = 3000
        def project(v):
            xy = projected(v) - shift
            return np.column_stack((left + 375 + xy[:, 0] * scale, 415 - xy[:, 1] * scale))
        for v, color in zip(geometry, ("#6e94ad", "#6e94ad", "#465969")):
            xy = project(v[::max(1, len(v) // 16000)])
            xy = xy[(xy[:, 0] > left + 20) & (xy[:, 0] < left + 730) & (xy[:, 1] > 135) & (xy[:, 1] < 530)]
            draw.point([tuple(p) for p in xy], fill=color)
        for take, color in ((train_mask, "#ffdc91"), (~train_mask, "#ff725e")):
            xy = project(patch[take])
            draw.point([tuple(p) for p in xy], fill=color)
        draw.text((left + 24, 545), "Source patch in the fixed-axis perpendicular plane", font=font, fill="white")
        fit_points = q[:, [2, 1]]
        center2 = fitted[[1, 0]]
        span = np.ptp(fit_points, axis=0).max() * 1.3
        scale2 = 290 / span
        middle = fit_points.mean(0)
        def project2(p):
            return np.array([left + 375, 765]) + (p - middle) * np.array([scale2, -scale2])
        for take, color in ((train_mask, "#ffdc91"), (~train_mask, "#ff725e")):
            for p in project2(fit_points[take]):
                draw.ellipse((p[0] - 1, p[1] - 1, p[0] + 1, p[1] + 1), fill=color)
        t = np.linspace(0, 2 * np.pi, 256)
        curve = center2 + fitted[2] * np.column_stack((np.cos(t), np.sin(t)))
        draw.line([tuple(p) for p in project2(curve)], fill="#e9f3f9", width=2)
        draw.text((left + 24, 940), f"Fit radius {row['train_fit_radius_mm']:.2f} mm | train/held {row['training_vertices']}/{row['heldout_vertices']}", font=font, fill="#c3d2da")
    draw.text((22, 1002), "Exploratory source-only screen replay. No ankle pivot acceptance and no replacement registered model emitted.", font=font, fill="#dbe6ed")
    image.save(out / "female-ankle-proxy-falsifier.png")
    receipt = {"status": "REJECT_FIXED_AXIS_ANKLE_PROXY" if not all(x["geometric_screen_pass"] for x in results) else "SOURCE_HYPOTHESIS_REQUIRES_FOLLOWUP",
               "registration_candidate_emitted": False, "source_geometry_changed": False,
               "input_sha256": {"ct": CT_SHA, "r242_diagnostic": DIAGNOSTIC_SHA},
               "source_ct_glb_sha256": sha(raw), "source_witness_glb_sha256": sha(packed),
               "source_labels_observed": names, "source_transport": replay, "fits": results,
               "geometric_screen_criteria": CRITERIA,
               "criteria_provenance": "Exploratory numerical screen chosen after local source preflight. This GHA run reproduces the negative result; it is not preregistered or donor-independent validation.",
               "scope": "Actual same-donor tibia/fibula/talus. Fixed-axis circular cylinder approximates a superior talar patch selected by proximity to tibia vertices. Neither the axis proxy nor patch is an independently established clinical articular surface. No skin optimization, axis rescue, shrink or replacement registration.",
               "next_constraint": "Qualify actual articular frame/ankle correspondence before replacing tibial-centroid anchor; retain R242 knee pair-relation critic and shared tibia/fibula transforms.",
               "execution": {k: os.environ.get(k) for k in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "SOURCE_HEAD_SHA", "RUNNER_OS", "RUNNER_ARCH")}}
    receipt["files"] = {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                        for p in out.iterdir() if p.is_file()}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("R243_ANKLE_PROXY", json.dumps({"status": receipt["status"], "fits": results,
          "source_transport": replay, "source_witness_glb_sha256": sha(packed)}), flush=True)


if __name__ == "__main__":
    main(*(Path(p) for p in sys.argv[1:]))
