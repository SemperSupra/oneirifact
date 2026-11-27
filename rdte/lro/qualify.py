#!/usr/bin/env python3
"""Standalone bounded public-safe asynchronous ray-render qualification.

Run with Python 3.11+; optional pinned cloudflared binary. No arbitrary scenes,
shell commands, remote uploads, private engine source or durable-store claims.
"""
import argparse
import hashlib
import hmac
import http.client
import json
import math
import os
from pathlib import Path
import re
import secrets
import struct
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
import zlib

WIDTH, HEIGHT = 480, 320
REQUEST = b'{"scene":"spheres"}'
SOURCE = hashlib.sha256(REQUEST).hexdigest()
TERMINAL = {"succeeded", "canceled", "failed"}

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

def pixel(x, y):
    # Perspective ray through the pixel, two spheres on a checkerboard floor.
    dx, dy, dz = (x - WIDTH / 2) / HEIGHT, (HEIGHT / 2 - y) / HEIGHT, -1.0
    norm = math.sqrt(dx*dx + dy*dy + dz*dz)
    dx, dy, dz = dx/norm, dy/norm, dz/norm
    near, hit, color = 1e9, None, (0, 0, 0)
    for cx, cy, cz, radius, rgb in ((-0.85, -0.12, -4.0, 0.87, (225, 92, 47)), (0.85, 0.08, -4.7, 1.07, (44, 151, 207))):
        b = dx*cx + dy*cy + dz*cz
        disc = b*b - (cx*cx + cy*cy + cz*cz - radius*radius)
        if disc >= 0:
            t = b - math.sqrt(disc)
            if 0 < t < near:
                near, hit, color = t, ((t*dx-cx)/radius, (t*dy-cy)/radius, (t*dz-cz)/radius), rgb
    if hit:
        nx, ny, nz = hit
        shade = 0.21 + 0.79*max(0, -0.45*nx + 0.75*ny + 0.48*nz)
        spec = 0.25*max(0, -0.22*nx + 0.39*ny + 0.89*nz)**30
        return bytes(min(255, int(c*shade + 255*spec)) for c in color)
    if dy < -0.0001:
        t = -1.0/dy
        if t < 40:
            square = (math.floor(t*dx) + math.floor(t*dz)) & 1
            value = (167 if square else 100)
            fog = min(0.9, t/40)
            return bytes(int(value*(1-fog)+c*fog) for c in (163, 188, 209))
    return bytes((153+int(40*max(0, dy)), 183+int(32*max(0, dy)), 211+int(25*max(0, dy))))

def render(job):
    rows = []
    try:
        for y in range(HEIGHT):
            if job["cancel"].is_set():
                break
            # Deliberate test gate only for the cancellation probe. It is not
            # measured render latency and cannot be supplied by a client.
            if job["controlled"] and y == 1:
                if job["cancel"].wait(30):
                    break
                raise RuntimeError("cancel probe did not cancel")
            rows.append(b"\0" + b"".join(pixel(x, y) for x in range(WIDTH)))
            with job["lock"]:
                job["rows"] = y+1
        with job["lock"]:
            if job["cancel"].is_set():
                job["state"] = "canceled"
            else:
                data = (b"\x89PNG\r\n\x1a\n" +
                        chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)) +
                        chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
                job["image"] = data
                job["sha256"] = hashlib.sha256(data).hexdigest()
                job["state"] = "succeeded"
    except Exception:
        with job["lock"]:
            job["state"] = "failed"

def origin(renderer=render, request_body=REQUEST, source_sha=SOURCE, total_units=HEIGHT):
    token = secrets.token_urlsafe(32)
    jobs = {}
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def log_message(self, *args):
            pass  # no bearer, paths or ephemeral hostname in logs

        def send(self, code, body=b"", content_type="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def auth(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send(401)
                return False
            return True

        def do_POST(self):
            if not self.auth():
                return
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length") != str(len(request_body)):
                self.send(400)
                return
            if self.rfile.read(len(request_body)) != request_body:
                self.send(400)
                return
            if self.path == "/v1/operations":
                key = self.headers.get("Idempotency-Key", "")
                if key not in ("image", "cancel"):
                    self.send(400)
                    return
                if key not in jobs:
                    for active in jobs.values():
                        with active["lock"]:
                            if active["state"] not in TERMINAL:
                                self.send(409)
                                return
                    job = {"id": key, "state": "running", "rows": 0, "lock": threading.Lock(),
                           "cancel": threading.Event(), "controlled": key == "cancel"}
                    jobs[key] = job
                    job["thread"] = threading.Thread(target=renderer, args=(job,), daemon=True)
                    job["thread"].start()
                self.send(202, json.dumps({"id": key, "source_sha256": source_sha}).encode())
                return
            match = re.fullmatch(r"/v1/operations/(image|cancel)/cancel", self.path)
            if match and match[1] in jobs:
                job = jobs[match[1]]
                with job["lock"]:
                    if job["state"] in TERMINAL:
                        self.send(409)
                        return
                    job["cancel"].set()
                self.send(202)
                return
            self.send(404)

        def do_GET(self):
            if not self.auth():
                return
            match = re.fullmatch(r"/v1/operations/(image|cancel)(/artifact)?", self.path)
            if not match or match[1] not in jobs:
                self.send(404)
                return
            job = jobs[match[1]]
            with job["lock"]:
                if match[2]:
                    if job["state"] != "succeeded":
                        self.send(409)
                        return
                    self.send(200, job["image"], "image/png")
                else:
                    status = {k: job[k] for k in ("id", "state", "rows")}
                    status.update(source_sha256=source_sha, total_rows=total_units, artifact_sha256=job.get("sha256"), worker_started=job.get("started", False))
                    self.send(200, json.dumps(status).encode())
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, token, jobs, thread

def call(base, token, path, method="GET", key=None, body=None):
    # http.client never follows redirects. Every call uses a new connection.
    target = urlsplit(base)
    con = (http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection)(
        target.hostname, target.port, timeout=8)
    try:
        headers = {"Authorization": "Bearer " + token}
        if key:
            headers["Idempotency-Key"] = key
        if body is not None:
            headers["Content-Type"] = "application/json"
        con.request(method, path, body=body, headers=headers)
        response = con.getresponse()
        data = response.read((4 << 20) + 1)
        require(len(data) <= 4 << 20, "response byte budget")
        return response.status, data
    finally:
        con.close()

def state(base, token, key):
    code, data = call(base, token, "/v1/operations/" + key)
    require(code == 200, "status unavailable")
    result = json.loads(data)
    require(result["source_sha256"] == SOURCE and result["id"] == key, "source or ID mismatch")
    return result

def wait_for(base, token, key, predicate):
    limit = time.monotonic() + 50
    last = -1
    while time.monotonic() < limit:
        result = state(base, token, key)
        require(last <= result["rows"] <= HEIGHT, "invalid progress")
        last = result["rows"]
        if predicate(result):
            return result
        require(result["state"] not in TERMINAL, "unexpected terminal state")
        time.sleep(0.1)
    raise RuntimeError("operation timeout")

def check_png(data):
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "PNG signature")
    offset, payload, size = 8, b"", None
    while offset < len(data):
        count, kind = struct.unpack(">I4s", data[offset:offset+8])
        value = data[offset+8:offset+8+count]
        crc, = struct.unpack(">I", data[offset+8+count:offset+12+count])
        require(zlib.crc32(kind+value) == crc, "PNG CRC")
        if kind == b"IHDR":
            size = struct.unpack(">II", value[:8])
        if kind == b"IDAT":
            payload += value
        offset += 12+count
    require(size == (WIDTH, HEIGHT), "PNG dimensions")
    raw = zlib.decompress(payload)
    require(len(raw) == HEIGHT*(WIDTH*3+1) and len(set(raw)) > 32, "nontrivial rendered pixels")

def qualify(base, token, out, mode):
    path = "/v1/operations"
    require(call(base, "invalid", path, "POST", "image", REQUEST)[0] == 401, "auth negative")
    require(call(base, token, path, "POST", "image", b"{}")[0] == 400, "request negative")
    start = time.monotonic()
    first = call(base, token, path, "POST", "image", REQUEST)
    require(first[0] == 202, "submit failed")
    require(call(base, token, path, "POST", "image", REQUEST) == first, "idempotent replay")
    result = wait_for(base, token, "image", lambda s: s["state"] == "succeeded")
    elapsed = time.monotonic() - start
    code, image = call(base, token, path + "/image/artifact")
    require(code == 200 and hashlib.sha256(image).hexdigest() == result["artifact_sha256"], "artifact digest")
    check_png(image)
    require(call(base, token, path, "POST", "cancel", REQUEST)[0] == 202, "cancel submit")
    wait_for(base, token, "cancel", lambda s: s["rows"] == 1)
    require(call(base, token, path + "/cancel/cancel", "POST", body=REQUEST)[0] == 202, "cancel request")
    canceled = wait_for(base, token, "cancel", lambda s: s["state"] == "canceled")
    require(call(base, token, path + "/cancel/artifact")[0] == 409, "canceled artifact admission")
    out.mkdir(parents=True, exist_ok=True)
    (out / "render.png").write_bytes(image)
    receipt = {"schema": "public-ray-fixture/v1", "transport": mode, "source_sha256": SOURCE,
               "artifact_sha256": result["artifact_sha256"], "width": WIDTH, "height": HEIGHT,
               "client_elapsed_seconds": round(elapsed, 3), "canceled_rows": canceled["rows"],
               "checks": ["auth rejection", "request rejection", "202", "idempotent replay",
                          "fresh HTTP connections", "progress", "PNG CRC/pixels/digest", "cancel", "no canceled artifact"]}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)

def run_fixture(out, cloudflared, origin_factory=origin, tester=qualify):
    server, token, jobs, thread = origin_factory()
    proc = None
    try:
        base = "http://127.0.0.1:" + str(server.server_port)
        if cloudflared:
            with tempfile.TemporaryDirectory(prefix="lro-tunnel-") as tmp:
                log = Path(tmp) / "tunnel.log"
                with log.open("wb") as writer:
                    proc = subprocess.Popen([str(cloudflared.resolve(strict=True)), "tunnel", "--no-autoupdate",
                                             "--protocol", "http2", "--url", base],
                                            stdout=writer, stderr=subprocess.STDOUT,
                                            env={"HOME": tmp, "PATH": os.defpath, "LANG": "C.UTF-8"})
                    try:
                        limit = time.monotonic()+90
                        remote = None
                        while time.monotonic() < limit and proc.poll() is None:
                            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com\b", log.read_text(errors="replace"))
                            if match:
                                try:
                                    if call(match[0], token, "/v1/operations/image")[0] == 404:
                                        remote = match[0]
                                        break
                                except (OSError, http.client.HTTPException):
                                    pass
                            time.sleep(1)
                        require(remote is not None, "Quick Tunnel not ready")
                        tester(remote, token, out, "cloudflare-quick-tunnel")
                    finally:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
        else:
            tester(base, token, out, "loopback")
    finally:
        for job in jobs.values():
            job["cancel"].set()
            job["thread"].join(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cloudflared", type=Path, help="Explicit verified Quick Tunnel binary; omit for loopback")
    args = parser.parse_args()
    run_fixture(args.out, args.cloudflared)

if __name__ == "__main__":
    main()
