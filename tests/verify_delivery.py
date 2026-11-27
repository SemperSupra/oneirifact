"""Stage and verify every file of a bounded static deployment, without private inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import urllib.request

MANIFEST = "release-manifest.json"
BASE = "https://sempersupra.github.io/oneirifact/"
MAX_FILES = 256
MAX_FILE = 64 << 20
MAX_TOTAL = 128 << 20
MAX_MANIFEST = 1 << 20
SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    return (isinstance(name, str) and len(name) <= 512 and name != MANIFEST
            and all(SEGMENT.fullmatch(part) for part in name.split("/")))


def validate(document):
    require(type(document) is dict and set(document) == {"version", "files"}
            and type(document["version"]) is int and document["version"] == 1,
            "invalid manifest schema")
    files = document["files"]
    require(type(files) is list and 0 < len(files) <= MAX_FILES, "invalid file count")
    seen = set()
    total = 0
    for entry in files:
        require(type(entry) is dict and set(entry) == {"path", "bytes", "sha256"}, "invalid entry")
        name, size, digest = entry["path"], entry["bytes"], entry["sha256"]
        require(safe_path(name), "unsafe asset path")
        require(name.casefold() not in seen, "duplicate asset path")
        require(type(size) is int and 0 <= size <= MAX_FILE, "invalid asset length")
        require(isinstance(digest, str) and DIGEST.fullmatch(digest), "invalid digest")
        seen.add(name.casefold())
        total += size
    require(total <= MAX_TOTAL, "total asset limit exceeded")
    require(any(e["path"] == "index.html" for e in files), "index.html required")
    require([e["path"] for e in files] == sorted(e["path"] for e in files), "unsorted manifest")
    return files


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), "invalid site root")
    files = []
    total = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            require(safe_path(relative) and not path.is_symlink(), "unsafe site entry: " + relative)
            if name in dirs:
                continue
            require(path.is_file(), "nonregular site entry")
            size = path.stat().st_size
            total += size
            require(len(files) < MAX_FILES and size <= MAX_FILE and total <= MAX_TOTAL, "site exceeds limits")
            data = path.read_bytes()
            require(len(data) == size, "asset changed during inventory")
            files.append({"path": relative, "bytes": size, "sha256": sha(data)})
    document = {"version": 1, "files": sorted(files, key=lambda e: e["path"])}
    validate(document)
    return document


def stage(source, destination):
    require(not destination.exists() and not destination.is_symlink(), "stage must not exist")
    require(not destination.resolve().is_relative_to(source.resolve()), "stage inside source")
    document = inventory(source)
    destination.mkdir(parents=True)
    for entry in document["files"]:
        target = destination / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / entry["path"], target)
    require(inventory(destination) == document, "staged assets differ")
    raw = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    require(len(raw) <= MAX_MANIFEST, "manifest exceeds limit")
    (destination / MANIFEST).write_bytes(raw)
    return sha(raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("unexpected asset redirect")


# Browsers enforce MIME types for ES modules and streaming WebAssembly.
# Bind those response properties to the same origin and bytes checked below.
BROWSER_MEDIA_TYPES = {
    ".html": {"text/html"},
    ".js": {"text/javascript", "application/javascript"},
    ".mjs": {"text/javascript", "application/javascript"},
    ".wasm": {"application/wasm"},
    ".css": {"text/css"},
    ".json": {"application/json"},
}


def verify_response_headers(url, headers):
    relative = url[len(BASE):] or "index.html"
    expected = BROWSER_MEDIA_TYPES.get(Path(relative).suffix.lower())
    if expected:
        values = headers.get_all("Content-Type", [])
        require(len(values) == 1 and values[0].split(";", 1)[0].strip().lower() in expected,
                "unexpected browser asset media type: " + relative)
    encodings = headers.get_all("Content-Encoding", [])
    require(not encodings or (len(encodings) == 1 and encodings[0].strip().lower() == "identity"),
            "unexpected content encoding: " + relative)


def fetch(url, limit):
    require(url.startswith(BASE), "unexpected asset origin")
    opener = urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Accept-Encoding": "identity"})
    with opener.open(req, timeout=10) as response:
        require(response.status == 200 and response.geturl() == url, "unexpected asset response")
        verify_response_headers(url, response.headers)
        data = response.read(limit + 1)
        require(len(data) <= limit, "oversized response")
        return data


def verify(expected, read=fetch):
    require(isinstance(expected, str) and DIGEST.fullmatch(expected), "invalid expected digest")
    raw = read(BASE + MANIFEST, MAX_MANIFEST)
    require(len(raw) <= MAX_MANIFEST and sha(raw) == expected, "live manifest digest mismatch")
    files = validate(json.loads(raw))
    for entry in files:
        names = [entry["path"]] if entry["path"] != "index.html" else ["index.html", ""]
        for name in names:
            data = read(BASE + name, entry["bytes"])
            require(len(data) == entry["bytes"] and sha(data) == entry["sha256"],
                    "live asset mismatch: " + entry["path"])
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("stage")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("destination", type=Path)
    live = sub.add_parser("verify")
    live.add_argument("expected")
    args = parser.parse_args()
    if args.command == "stage":
        print(stage(args.source, args.destination))
    else:
        print(f"Live manifest and {verify(args.expected)} asset(s) verified")


if __name__ == "__main__":
    main()
