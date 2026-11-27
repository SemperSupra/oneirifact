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
import shutil
import subprocess
import tempfile

MAX_FILE = 16 << 20
MAX_TOTAL = 128 << 20
MAX_FILES = 4096
LEAK = 42


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def stage_tracked(destination):
    """Scan only exact tracked regular files, with no repository config/history."""
    paths = subprocess.check_output(["git", "ls-files", "-z"], timeout=15).split(b"\0")
    paths = [os.fsdecode(p) for p in paths if p]
    require(0 < len(paths) <= MAX_FILES, "tracked file-count limit")
    total = 0
    for name in paths:
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts
                and ".git" not in relative.parts, "unsafe tracked path")
        source = Path.cwd() / relative
        require(source.is_file() and not source.is_symlink()
                and not any(p.is_symlink() for p in source.parents),
                "nonregular or linked source")
        size = source.stat().st_size
        total += size
        require(size <= MAX_FILE and total <= MAX_TOTAL, "tracked source size limit")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        require(target.stat().st_size == size, "source changed during staging")
    return len(paths)


def run_scan(binary, work, name, source, expect_rule=None):
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
        count = stage_tracked(source)
        run_scan(binary, work, "public-tracked-source", source)
        print(f"Independent scanner controls and {count} public tracked files PASS")


if __name__ == "__main__":
    main()
