"""Actual render contact sheet + qualified encoder; no image synthesis."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

out = Path(sys.argv[1])
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name, value):
    (out / name).write_text(json.dumps(value, indent=2) + "\n")
producer = json.loads((out / "capture-receipt.json").read_text())
critic = json.loads((out / "capture-critic.json").read_text())
manifest = json.loads((out / "render-manifest.json").read_text())
paths = [out / row["file"] for row in manifest["frames"]]
assert paths and all(sha(path) == row["sha256"] for path, row in zip(paths, manifest["frames"]))
assert imageio_ffmpeg.__version__ == "0.6.0"
encoder = Path(imageio_ffmpeg.get_ffmpeg_exe())
encoder_sha = sha(encoder)
assert encoder_sha == "e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99"
version = subprocess.check_output([str(encoder), "-version"], text=True).splitlines()[0]
video = out / "captured-source-vs-retargeted.mp4"
subprocess.run([str(encoder), "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(manifest["fps"]), "-i", str(out / "render-frames" / "%04d.png"), "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)], check=True)
size = Image.open(paths[0]).size
width, height = size
decoded = subprocess.run([str(encoder), "-hide_banner", "-loglevel", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, check=True).stdout
stride = width * height * 3
assert len(decoded) == len(paths) * stride
errors = []
for index in sorted({0, len(paths) // 2, len(paths) - 1}):
    image = Image.frombytes("RGB", size, decoded[index * stride:(index + 1) * stride])
    source = Image.open(paths[index]).convert("RGB")
    error = max(ImageStat.Stat(ImageChops.difference(image, source)).mean)
    assert error < 8
    errors.append({"frame": index, "max_mean_channel_error_255": error})
frames, seconds = imageio_ffmpeg.count_frames_and_secs(str(video))
assert frames == len(paths) and abs(seconds - len(paths) / manifest["fps"]) < .15
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
def font(size):
    return ImageFont.truetype(font_path, size) if Path(font_path).exists() else ImageFont.load_default()
chosen = [round(i * (len(paths) - 1) / 5) for i in range(6)]
sheet = Image.new("RGB", (1280, 1680), "#111925")
draw = ImageDraw.Draw(sheet)
capture_label = "Walking" if producer["capture"] == "07_01" else "Sit / stand sequence"
draw.text((28, 20), "CMU " + producer["capture"] + " · " + capture_label, font=font(34), fill="#f4f6fa")
draw.text((28, 65), "Actual captured source (orange) and " + producer["case"]["id"] + " retargeted exterior (teal)", font=font(23), fill="#cbd5e1")
draw.text((28, 101), "Pinned Diffeomorphic 5.2.0 · original cadence · no contact correction", font=font(21), fill="#cbd5e1")
for k, index in enumerate(chosen):
    x, y = (k % 2) * 640, 152 + (k // 2) * 480
    image = Image.open(paths[index]).convert("RGB")
    sheet.paste(image, (x, y))
    draw.rectangle((x + 10, y + 8, x + 260, y + 40), fill="#111925")
    draw.text((x + 18, y + 13), "Capture t = %.3f s" % manifest["frames"][index]["time_s"], font=font(20), fill="#f5f6fa")
draw.rectangle((0, 1593, 1280, 1680), fill="#172333")
draw.text((28, 1606), "Transport passed; retarget quality held. Ground, seat, balance and self-collision are unqualified.", font=font(21), fill="#f6cd72")
draw.text((28, 1641), "Source-inferred foot episodes exceeding 5 mm drift: " + str(critic["target_5mm_screen_exceedances"]) + " (provisional screen, not measured contact).", font=font(20), fill="#cad5e3")
sheet.save(out / "captured-motion-review.png")
save("media-receipt.json", {"schema": "oneirifact.captured-motion-media/v1", "status": "PASS_FULL_VIDEO_DECODE", "encoder": {"package": "imageio-ffmpeg==0.6.0", "wheel_sha256": "c7e46fcec401dd990405049d2e2f475e2b397779df2519b544b8aab515195282", "binary_sha256": encoder_sha, "version": version}, "frame_count": frames, "fps": manifest["fps"], "duration_s": seconds, "source_frame_samples": errors, "video_sha256": sha(video), "render_source": "Actual native Blender output; no image generation", "review_image_sha256": sha(out / "captured-motion-review.png")})
producer["critic_status"] = critic["status"]
producer["media_status"] = "PASS_FULL_VIDEO_DECODE"
producer["files"] = {str(path.relative_to(out)): {"bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(out.rglob("*")) if path.is_file() and path.name != "capture-receipt.json"}
save("capture-receipt.json", producer)
print("R247_PACKAGE", json.dumps({"case": producer["case"]["id"], "capture": producer["capture"], "frames": frames, "video_bytes": video.stat().st_size, "critic": critic["status"]}), flush=True)
