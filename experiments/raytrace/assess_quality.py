#!/usr/bin/env python3
"""Bounded visual-quality witness for the original public Cycles pavilion.

This is a reference-image heuristic, not human aesthetic acceptance or
camera/color-science metrology. Uses independently decoded real PNG pixels.
"""
import json
from pathlib import Path
import sys

from PIL import Image, ImageStat


def evaluate(folder: Path) -> dict:
    metrics = {}
    for name in ("pavilion-day", "pavilion-night"):
        with Image.open(folder / (name + ".png")) as item:
            item.load()
            if item.format != "PNG" or item.size != (720, 480):
                raise ValueError("unexpected real Cycles frame")
            im = item.convert("RGB")
            area = im.crop((270, 155, 450, 305))
            samples = list(area.getdata())
            fully_bright = sum(min(ch) >= 248 for ch in samples)
            fraction = fully_bright / len(samples)
            means = ImageStat.Stat(im).mean
            metrics[name] = {
                "central_highlight_clip_fraction": round(fraction, 6),
                "frame_mean_rgb": [round(x, 4) for x in means],
                "central_area_pixels": len(samples),
            }

    # Frozen R191 public reference observations under the same rectangle:
    # day .1494 and night .1534. Require the next iteration to improve.
    for key in ("pavilion-day", "pavilion-night"):
        if metrics[key]["central_highlight_clip_fraction"] >= 0.14:
            raise ValueError("highlight clipping not improved from earlier study")
    day = sum(metrics["pavilion-day"]["frame_mean_rgb"]) / 3
    night = sum(metrics["pavilion-night"]["frame_mean_rgb"]) / 3
    if night >= day * 0.82:
        raise ValueError("night scene not meaningfully darker than daylight")
    return {
        "schema": "oneirifact.public-visual-comparison/v0.1",
        "status": "REFERENCE_CONTRAST_AND_HIGHLIGHT_HEURISTICS_PASS",
        "previous_render": "R191 actual public native Cycles #46026177019",
        "limits": "single ROI and one public runner; not independent human quality judgment",
        "metrics": metrics,
        "night_to_day_mean_brightness_ratio": round(night / day, 5),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: assess_quality.py EXISTING_RENDER_OUTPUT_DIR")
    folder = Path(sys.argv[1])
    result = evaluate(folder)
    (folder / "visual-quality.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("PUBLIC_R192_VISUAL_QUALITY_PASS", json.dumps(result, sort_keys=True))
