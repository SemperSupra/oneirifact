"""Independent captured-motion critic. Contact inference stays provisional."""
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np

DRIFT_M = .005


def episodes(times, mask, expected_dt, minimum_s=.12):
    times = np.asarray(times)
    if len(times) < 3 or not np.all(np.diff(times) > 0):
        raise ValueError("Missing or non-increasing observation times")
    if not np.allclose(np.diff(times), expected_dt, atol=1e-9, rtol=1e-5):
        return None
    result, current = [], []
    for i, active in enumerate(mask):
        if active:
            current.append(i)
        else:
            if current and times[current[-1]] - times[current[0]] >= minimum_s:
                result.append(current)
            current = []
    if current and times[current[-1]] - times[current[0]] >= minimum_s:
        result.append(current)
    return result


def horizontal_drift(points):
    points = np.asarray(points)[:, [0, 2]]
    return float(np.linalg.norm(points - points[0], axis=1).max())


def controls():
    times = np.arange(61) / 120
    fixed = np.zeros((61, 3))
    sliding = fixed.copy()
    sliding[:, 2] = np.linspace(0, .02, 61)
    assert horizontal_drift(fixed) == 0
    assert abs(horizontal_drift(sliding) - .02) < 1e-12
    assert horizontal_drift(sliding) > DRIFT_M
    phases = [True] * 21 + [False] * 19 + [True] * 21
    separated = episodes(times, phases, 1 / 120)
    assert len(separated) == 2 and separated[0][-1] == 20 and separated[1][0] == 40
    assert episodes(np.delete(times, 30), [True] * 60, 1 / 120) is None
    bad = times.copy()
    bad[2] = bad[1]
    try:
        episodes(bad, [True] * 61, 1 / 120)
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate timestamp was silently accepted")
    return {"fixed_foot_analytic_zero": "PASS", "20mm_slide_detected_over_5mm_screen": "PASS", "stance_episodes_separated_by_swing": "PASS", "missing_observation_abstains": "PASS", "duplicate_timestamp_rejected": "PASS"}


def review(data, receipt):
    rows = data["rows"]
    times = np.array([row["time_s"] for row in rows])
    dt = data["frame_time_s"]
    assert rows[0]["bvh_row"] == 1, "Empirical reference pose mislabeled as captured motion"
    assert [row["bvh_row"] for row in rows] == list(range(1, len(rows) + 1))
    assert abs(times[0]) < 1e-12 and np.allclose(times, np.arange(len(rows)) * dt, atol=1e-10)
    assert receipt["export"]["captured_frames"] == len(rows)
    assert receipt["export"]["source_attributes_and_indices_bit_identical"]
    assert receipt["export"]["skin_and_inverse_bind_accessors_unchanged"]
    assert not receipt["export"]["reference_frame_exported_as_capture"]
    foot_reports = []
    for side, word in (("L", "Left"), ("R", "Right")):
        source = np.array([row["source_joint_heads_m"][word + "ToeBase"] for row in rows])
        target = np.array([row["target"][side]["forefoot"] for row in rows])
        floor_proxy = float(np.quantile(source[:, 1], .05))
        speed = np.linalg.norm(np.gradient(source[:, [0, 2]], times, axis=0), axis=1)
        mask = (source[:, 1] < floor_proxy + .02) & (speed < .15)
        candidates = episodes(times, mask, dt)
        report = {"side": side, "source_joint": word + "ToeBase", "target_marker": "fixed source-skin forefoot marker transported by actual foot bone", "floor_proxy_m": floor_proxy, "floor_proxy_method": "5th percentile of source toe-base height; not measured ground", "source_height_band_m": .02, "source_speed_limit_m_per_s": .15, "minimum_episode_s": .12, "ground_truth_contact": "UNAVAILABLE", "episodes": []}
        if candidates is None:
            report["status"] = "NOT_RUN_SPARSE_OBSERVATIONS"
        else:
            for ids in candidates:
                td, sd = horizontal_drift(target[ids]), horizontal_drift(source[ids])
                report["episodes"].append({"start_s": float(times[ids[0]]), "end_s": float(times[ids[-1]]), "samples": len(ids), "source_proxy_drift_m": sd, "target_forefoot_drift_m": td, "target_minus_source_drift_m": td - sd, "target_5mm_screen": "EXCEEDS" if td > DRIFT_M else "WITHIN", "interpretation": "Provisional source-inferred stance only; neither source nor target contact accepted"})
            report["status"] = "PROVISIONAL_EPISODES_MEASURED" if candidates else "NO_QUALIFYING_PROXY_EPISODES"
        report["target_absolute_world_y_range_m"] = [float(target[:, 1].min()), float(target[:, 1].max())]
        report["target_net_forefoot_displacement_m"] = (target[-1] - target[0]).tolist()
        foot_reports.append(report)
    source_root = np.array([row["source_joint_heads_m"]["Hips"] for row in rows])
    target_root = np.array([row["target_root_m"] for row in rows])
    root_path_error = float(np.max(np.linalg.norm((target_root - target_root[0]) - (source_root - source_root[0]), axis=1)))
    assert root_path_error < 5e-5, "Source root motion was centered, lost or retimed"
    return {"schema": "oneirifact.captured-motion-independent-critic/v1", "status": "HOLD_RETARGET_QUALITY", "capture": data["capture"], "case_id": data["case_id"], "transport_status": receipt["status"], "source_cadence_and_capture_row_identity": "PASS", "reference_excluded": True, "captured_frames": len(rows), "duration_s": float(times[-1]), "source_to_target_root_displacement_max_error_m": root_path_error, "source_net_root_displacement_m": (source_root[-1] - source_root[0]).tolist(), "target_net_root_displacement_m": (target_root[-1] - target_root[0]).tolist(), "root_motion_preserved_without_centering": True, "loop_seam": "NOT_APPLICABLE_UNMODIFIED_NONLOOP_CAPTURE", "provisional_foot_screens": foot_reports, "target_5mm_screen_exceedances": sum(ep["target_5mm_screen"] == "EXCEEDS" for foot in foot_reports for ep in foot["episodes"]), "acceptance": {"realistic_motion": "NOT_QUALIFIED", "planted_foot_ground_truth": "UNAVAILABLE", "ground_penetration": "NOT_RUN_GROUND_UNCALIBRATED", "seat_contact": "NOT_RUN_SEAT_GEOMETRY_UNAVAILABLE", "self_intersection": "NOT_RUN", "joint_limits": "NOT_RUN", "balance_forces": "NOT_RUN", "finger_grip": "NOT_RUN", "soft_tissue_organs_breathing": "NOT_RUN", "generic_morphology_or_footwear": "NOT_QUALIFIED"}, "analytic_controls": controls(), "interpretation": "Actual captured source and native target evidence with provisional contact screens. Successful runtime and transport do not qualify realistic retargeting."}


if __name__ == "__main__":
    out = Path(sys.argv[1])
    report = review(json.loads((out / "capture-observations.json").read_text()), json.loads((out / "capture-receipt.json").read_text()))
    (out / "capture-critic.json").write_text(json.dumps(report, indent=2) + "\n")
    print("R247_CRITIC", json.dumps({key: report[key] for key in ("status", "capture", "case_id", "captured_frames", "target_5mm_screen_exceedances", "source_to_target_root_displacement_max_error_m")}))
