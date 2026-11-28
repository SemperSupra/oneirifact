"""Independent selected-BVH parser/FK oracle; never rewrites source capture bytes."""
import hashlib
import math
import re
from pathlib import Path

import numpy as np


def parse(path):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig")
    hierarchy, motion = text.split("MOTION", 1)
    tokens = re.findall(r"[{}]|[^\s{}]+", hierarchy)
    cursor = 0
    nodes = []
    channel_count = 0

    def take():
        nonlocal cursor
        result = tokens[cursor]
        cursor += 1
        return result

    assert take() == "HIERARCHY"

    def node(parent=None, end=False):
        nonlocal channel_count
        name = take()
        if end:
            assert name == "Site"
            assert take() == "{" and take() == "OFFSET"
            offset = [float(take()) for _ in range(3)]
            assert take() == "}"
            nodes[parent]["end_offset"] = offset
            return
        index = len(nodes)
        item = {"name": name, "parent": parent, "offset": None, "channels": [], "channel_start": channel_count}
        nodes.append(item)
        assert take() == "{"
        while True:
            key = take()
            if key == "}":
                break
            if key == "OFFSET":
                item["offset"] = [float(take()) for _ in range(3)]
            elif key == "CHANNELS":
                item["channels"] = [take() for _ in range(int(take()))]
                item["channel_start"] = channel_count
                channel_count += len(item["channels"])
            elif key == "JOINT":
                node(index)
            elif key == "End":
                node(index, True)
            else:
                raise ValueError(key)
        assert item["offset"] is not None

    assert take() == "ROOT"
    node()
    assert cursor == len(tokens)
    lines = [line.strip() for line in motion.splitlines() if line.strip()]
    count = int(lines[0].split(":")[1])
    dt = float(lines[1].split(":")[1])
    values = np.fromstring(" ".join(lines[2:]), sep=" ").reshape(count, channel_count)
    assert np.isfinite(values).all()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "nodes": nodes, "values": values, "frame_time_s": dt, "frame_count": count, "channel_count": channel_count}


def rotation(axis, angle):
    c, s = math.cos(angle), math.sin(angle)
    if axis == "X":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "Y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def fk(data, frame, scale=1.0):
    result = []
    row = data["values"][frame]
    for node in data["nodes"]:
        local = np.eye(4)
        local[:3, 3] = np.array(node["offset"]) * scale
        for channel, value in zip(node["channels"], row[node["channel_start"]:]):
            if channel.endswith("position"):
                local["XYZ".index(channel[0]), 3] += value * scale
            else:
                local[:3, :3] = local[:3, :3] @ rotation(channel[0], math.radians(value))
        result.append(local if node["parent"] is None else result[node["parent"]] @ local)
    return np.array(result)


def controls():
    data = {"nodes": [
        {"name": "root", "parent": None, "offset": [0, 0, 0], "channels": ["Xposition", "Yposition", "Zposition", "Zrotation", "Yrotation", "Xrotation"], "channel_start": 0},
        {"name": "tip", "parent": 0, "offset": [2, 0, 0], "channels": [], "channel_start": 6},
    ], "values": np.array([[1, 2, 3, 90, 0, 0]])}
    expected = np.array([1, 4, 3])
    observed = fk(data, 0)[1, :3, 3]
    assert np.linalg.norm(observed - expected) < 1e-12
    assert np.linalg.norm(fk(data, 0, 2)[1, :3, 3] - 2 * expected) < 1e-12
    return {"translated_parent_plus_90_degree_child": "PASS", "declared_uniform_unit_scale": "PASS"}


if __name__ == "__main__":
    import json, sys
    data = parse(sys.argv[1])
    print(json.dumps({k: v for k, v in data.items() if k not in ("nodes", "values")}))
    print(controls())
