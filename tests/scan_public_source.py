#!/usr/bin/env python3
"""Pinned independent secret-scan gate for the public tracked source tree.

This is a defense-in-depth scan, not a release-rights or confidentiality attestation.
No findings, matching source lines, or credentials are printed or uploaded.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

MAX_FILE = 16 << 20
MAX_TOTAL = 128 << 20
MAX_FILES = 4096
LEAK = 42


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(repo, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(repo), *args],
                                   timeout=20, stderr=subprocess.DEVNULL)


def stage_tracked(destination, repo=None, commit=None):
    """Materialize exact commit blobs, never mutable index or worktree files."""
    repo = Path.cwd() if repo is None else Path(repo)
    commit = commit or git(repo, "rev-parse", "HEAD").decode().strip()
    require(len(commit) == 40 and all(c in "0123456789abcdef" for c in commit),
            "expected exact SHA-1 commit")
    require(git(repo, "cat-file", "-t", commit) == b"commit\\n", "invalid commit")
    require(destination.is_dir() and not destination.is_symlink() and not any(destination.iterdir()),
            "staging directory must exist and be empty")
    rows = [r for r in git(repo, "ls-tree", "-r", "-l", "-z", commit).split(b"\\0") if r]
    require(0 < len(rows) <= MAX_FILES, "tracked file-count limit")
    total, manifest, names = 0, {}, {}
    for row in rows:
        meta, raw_path = row.split(b"\\t", 1)
        mode, kind, oid, size = meta.decode("ascii").split()
        require(mode in ("100644", "100755") and kind == "blob", "nonregular Git entry")
        name = raw_path.decode("utf-8", errors="strict")
        relative = Path(name)
        require(not relative.is_absolute() and "\\\\" not in name
                and all(part not in ("", ".", "..", ".git") for part in name.split("/")),
                "unsafe tracked path")
        for index in range(1, len(relative.parts) + 1):
            prefix = "/".join(relative.parts[:index])
            # Record every directory prefix to catch case-colliding paths.
            folded = prefix.casefold()
            require(names.setdefault(folded, prefix) == prefix, "case-conflicting tracked path")
        count = int(size)
        total += count
        require(0 <= count <= MAX_FILE and total <= MAX_TOTAL, "tracked source size limit")
        data = git(repo, "cat-file", "blob", oid)
        require(len(data) == count, "Git blob size mismatch")
        require(hashlib.sha1(b"blob " + str(count).encode() + b"\\0" + data).hexdigest() == oid,
                "Git blob identity mismatch")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        manifest[name] = hashlib.sha256(data).hexdigest()
    require(scan_inventory(destination) == manifest, "staged tree mismatch")
    return manifest


def scan_inventory(source):
    require(source.is_dir() and not source.is_symlink(), "scan target unavailable")
    result, total = {}, 0
    for path in source.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        require(stat.S_ISREG(mode), "nonregular scan input")
        size = path.stat().st_size
        total += size
        require(size <= MAX_FILE and total <= MAX_TOTAL and len(result) < MAX_FILES,
                "scan input budget exceeded")
        data = path.read_bytes()
        require(len(data) == size, "scan input changed")
        result[path.relative_to(source).as_posix()] = hashlib.sha256(data).hexdigest()
    require(bool(result), "scan target empty")
    return result


def run_scan(binary, work, name, source, expect_rule=None, expected_manifest=None):
    before = scan_inventory(source)
    if expected_manifest is not None:
        require(before == expected_manifest, "scan input differs from committed bytes")
    report = work / (name + ".json")
    config = work / "config.toml"
    ignore = work / ".gitleaksignore"
    args = [str(binary), "dir", "--config", str(config), "--gitleaks-ignore-path",
            str(ignore), "--ignore-gitleaks-allow", "--redact=100", "--exit-code",
            str(LEAK), "--max-target-megabytes", "17", "--max-decode-depth", "2",
            "--max-archive-depth", "0", "--timeout", "40", "--log-level", "error",
            "--report-format", "json", "--report-path", str(report), str(source)]
    result = subprocess.run(args, cwd=work, timeout=50, capture_output=True,
                            env={"PATH": os.defpath, "HOME": str(work), "LANG": "C.UTF-8"})
    require(scan_inventory(source) == before, "scan input changed during scan")
    # The scanner's raw logs and reports must not be printed, even on failure.
    if expect_rule is None:
        require(result.returncode == 0, name + " failed or found a secret")
        if report.exists():
            require(json.loads(report.read_text()) in ([], None), name + " unexpected findings")
    else:
        require(result.returncode == LEAK and report.is_file(), name + " expected finding missing")
        require(any(f.get("RuleID") == expect_rule for f in json.loads(report.read_text())),
                name + " expected rule missing")
    print(name + " PASS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scanner", type=Path)
    parser.add_argument("--commit", required=True, help="Exact public commit SHA to scan")
    args = parser.parse_args()
    binary = args.scanner.resolve(strict=True)
    require(binary.is_file() and os.access(binary, os.X_OK), "scanner unavailable")
    with tempfile.TemporaryDirectory(prefix="public-source-scan-") as tmp:
        work = Path(tmp)
        (work / "config.toml").write_text("[extend]\nuseDefault = true\n")
        (work / ".gitleaksignore").write_text("")
        # Deliberately fake, reproducible signatures; never a credential or key.
        token = "gh" + "p_" + hashlib.sha256(b"public scanner fixture only").hexdigest()[:36]
        pem = ("-----BEGIN " + "PRIVATE KEY-----\n" + "A" * 96
               + "\n-----END " + "PRIVATE KEY-----\n")
        cases = [
            ("clean-control", "Ordinary project description.\n", None),
            ("fake-token", token + "\n", "github-pat"),
            ("ignore-inline-suppression", token + " # gitleaks:allow\n", "github-pat"),
            ("encoded-fake-token", base64.b64encode(token.encode()).decode() + "\n", "github-pat"),
            ("fake-key-shape", pem, "private-key"),
        ]
        for name, value, rule in cases:
            folder = work / name
            folder.mkdir()
            (folder / "fixture.txt").write_text(value)
            run_scan(binary, work, name, folder, rule)
        source = work / "tracked"
        source.mkdir()
        manifest = stage_tracked(source, commit=args.commit)
        run_scan(binary, work, "public-tracked-source", source, expected_manifest=manifest)
        print(f"Independent scanner controls and {len(manifest)} public committed files PASS")


if __name__ == "__main__":
    main()
