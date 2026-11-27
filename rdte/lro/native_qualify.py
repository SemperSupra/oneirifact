#!/usr/bin/env python3
"""Fixed-input native CPU Cycles LRO through the same bounded HTTP fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import tempfile
import time
import zlib

from qualify import call, origin, require, run_fixture

PROFILES = ("pavilion-day", "pavilion-night", "pavilion-plan")
DONOR = Path(__file__).resolve().parent / "cycles"
GENERATOR = "dfb651839319343da291556bf160e474360bb2cd7e92256486d7d7cc6c0f9308"
SPECS = "667aa706befe36b34c8689aaf7cbec1a32858cc5610c3ab154b7cf7218ec73c9"
REQUEST = json.dumps({"scene": "pavilion", "profiles": PROFILES, "generator_sha256": GENERATOR,
                      "specs_sha256": SPECS}, separators=(",", ":")).encode()
SOURCE = hashlib.sha256(REQUEST).hexdigest()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def image_check(data):
    require(1000 < len(data) <= 4 << 20 and data[:8] == b"\x89PNG\r\n\x1a\n", "native PNG")
    offset, payload, header = 8, bytearray(), None
    while offset < len(data):
        require(offset + 12 <= len(data), "truncated PNG")
        count, kind = struct.unpack(">I4s", data[offset:offset+8])
        require(offset + 12 + count <= len(data), "truncated PNG chunk")
        value = data[offset+8:offset+8+count]
        require(zlib.crc32(kind+value) == struct.unpack(">I", data[offset+8+count:offset+12+count])[0], "PNG CRC")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", value)
        if kind == b"IDAT":
            payload.extend(value)
        offset += 12+count
        if kind == b"IEND":
            require(offset == len(data), "trailing PNG bytes")
            break
    require(header is not None and header[:3] == (720, 480, 8) and header[3] in (2, 6) and header[4:] == (0, 0, 0), "native PNG format")
    stride = 720 * (3 if header[3] == 2 else 4) + 1
    decoder = zlib.decompressobj()
    raw = decoder.decompress(payload, stride * 480 + 1)
    require(len(raw) == stride * 480 and decoder.eof and len(set(raw)) > 32, "native raster data")
    require(all(raw[i] <= 4 for i in range(0, len(raw), stride)), "PNG filter")

def stop(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)

def renderer(blender, work, job):
    path = work / job["id"]
    # The pinned donor requires private output custody; default mkdir under
    # umask 022 produces 0755 and is deliberately rejected by the donor.
    path.mkdir(mode=0o700)
    require((path.stat().st_mode & 0o077) == 0, "private native output directory")
    proc = None
    try:
        for profile in PROFILES:
            if job["cancel"].is_set():
                break
            with (path / (profile + ".log")).open("wb") as log:
                start = time.monotonic()
                proc = subprocess.Popen([str(blender), "--background", "--factory-startup", "--disable-autoexec",
                                         "-t", "2", "--python-exit-code", "1", "--python", str(DONOR/"pavilion.py"), "--",
                                         str(DONOR/"specs.json"), profile, str(path)],
                                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                        env={"HOME": str(work), "PATH": os.defpath, "LANG": "C.UTF-8"})
                with job["lock"]:
                    job["started"] = True
                while proc.poll() is None:
                    if job["cancel"].wait(0.1):
                        stop(proc)
                        break
                    if time.monotonic() - start > 100:
                        stop(proc)
                        raise RuntimeError("native render exceeded time budget")
                if job["cancel"].is_set():
                    break
                if proc.returncode != 0:
                    # Public fixed-input process only, with a scrubbed environment.
                    # Retain a bounded diagnostic tail, never HTTP request data.
                    with (path / (profile + ".log")).open("rb") as diagnostic:
                        diagnostic.seek(max(0, (path / (profile + ".log")).stat().st_size - 4096))
                        print(diagnostic.read(4096).decode("utf-8", errors="replace"), flush=True)
                    raise RuntimeError("native Blender failed")
                image = (path/(profile+".png")).read_bytes()
                receipt = json.loads((path/(profile+".json")).read_text())
                image_check(image)
                require(receipt["engine"] == "CYCLES" and receipt["device"] == "CPU"
                        and receipt["blender_version"].startswith("5.2.4")
                        and receipt["generator_sha256"] == "sha256:"+GENERATOR
                        and receipt["spec_sha256"] == "sha256:"+SPECS
                        and receipt["image_sha256"] == "sha256:"+sha(image)
                        and receipt["resolution"] == [720, 480], "native source/engine/receipt mismatch")
                with job["lock"]:
                    job["rows"] += 1
        with job["lock"]:
            if job["cancel"].is_set():
                job["state"] = "canceled"
            else:
                require(job["rows"] == len(PROFILES), "incomplete native render")
                job["image"] = image
                job["sha256"] = sha(image)
                job["state"] = "succeeded"
    except Exception as error:
        # Error type only: native logs are not returned through HTTP.
        print("Native fixture worker failure:", type(error).__name__, str(error), flush=True)
        with job["lock"]:
            job["state"] = "failed"
    finally:
        if proc is not None:
            stop(proc)

def poll(base, token, key, predicate, seconds=220):
    until = time.monotonic()+seconds
    last = -1
    while time.monotonic() < until:
        code, raw = call(base, token, "/v1/operations/"+key)
        require(code == 200, "native status unavailable")
        s = json.loads(raw)
        require(s["id"] == key and s["source_sha256"] == SOURCE
                and last <= s["rows"] <= len(PROFILES), "native status identity/progress")
        last = s["rows"]
        if predicate(s):
            return s
        require(s["state"] == "running", "unexpected native terminal state")
        time.sleep(0.5)
    raise RuntimeError("native operation timeout")

def exercise(base, token, out, mode, work):
    path = "/v1/operations"
    require(call(base, "invalid", path, "POST", "image", REQUEST)[0] == 401, "native auth")
    require(call(base, token, path, "POST", "image", b"{}")[0] == 400, "native request")
    start = time.monotonic()
    first = call(base, token, path, "POST", "image", REQUEST)
    require(first[0] == 202 and call(base, token, path, "POST", "image", REQUEST) == first, "native admission/replay")
    running = poll(base, token, "image", lambda s: s["worker_started"] and s["state"] == "running", 20)
    require(running["rows"] < len(PROFILES), "must witness live computation")
    # The client has no open HTTP connection during this interval.
    time.sleep(3)
    done = poll(base, token, "image", lambda s: s["state"] == "succeeded")
    elapsed = time.monotonic()-start
    require(elapsed >= 5 and done["rows"] == len(PROFILES), "sustained multi-render workload")
    code, downloaded = call(base, token, path+"/image/artifact")
    require(code == 200 and sha(downloaded) == done["artifact_sha256"], "native artifact delivery")
    image_check(downloaded)
    out.mkdir(parents=True, exist_ok=True)
    images = {}
    for profile in PROFILES:
        for suffix in (".png", ".json"):
            shutil.copyfile(work/"image"/(profile+suffix), out/(profile+suffix))
        data = (out/(profile+".png")).read_bytes()
        image_check(data)
        images[profile] = sha(data)
    require(images[PROFILES[-1]] == sha(downloaded), "native downloaded PNG differs")
    require(call(base, token, path, "POST", "cancel", REQUEST)[0] == 202, "native cancel admission")
    poll(base, token, "cancel", lambda s: s["worker_started"] and s["state"] == "running", 20)
    require(call(base, token, path+"/cancel/cancel", "POST", body=REQUEST)[0] == 202, "native cancel")
    canceled = poll(base, token, "cancel", lambda s: s["state"] == "canceled", 20)
    require(call(base, token, path+"/cancel/artifact")[0] == 409, "native canceled artifact")
    report = {"schema": "public-native-lro/v1", "transport": mode, "source_sha256": SOURCE,
              "images_sha256": images, "elapsed_seconds": round(elapsed, 3),
              "completed_units": done["rows"], "canceled_units": canceled["rows"],
              "checks": ["actual CPU Cycles", "202/replay/auth", "live progress", "disconnected client",
                         "artifact HTTPS digest", "actual process cancellation", "canceled artifact rejection"]}
    (out/"receipt.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cloudflared", type=Path, required=True)
    parser.add_argument("--blender", type=Path, required=True)
    args = parser.parse_args()
    blender = args.blender.resolve(strict=True)
    require(sha((DONOR/"pavilion.py").read_bytes()) == GENERATOR and sha((DONOR/"specs.json").read_bytes()) == SPECS, "donor bytes")
    with tempfile.TemporaryDirectory(prefix="native-lro-") as tmp:
        work = Path(tmp)
        run_fixture(args.out, args.cloudflared,
                    lambda: origin(lambda job: renderer(blender, work, job), REQUEST, SOURCE, len(PROFILES)),
                    lambda base, token, out, mode: exercise(base, token, out, mode, work))

if __name__ == "__main__":
    main()
