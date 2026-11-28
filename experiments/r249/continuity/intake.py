"""Read-only exact artifact intake for the bounded native quaternion audit."""
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

manifest, group, inputs, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
spec = json.loads(manifest.read_text())
rows = list(spec["groups"][group])
if group == "r248":
    rows += spec["negative_controls"]
inputs.mkdir(parents=True, exist_ok=False)
out.mkdir(parents=True, exist_ok=False)
(out / "inputs.json").write_bytes(manifest.read_bytes())
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
receipts = []
for entry in rows:
    key = str(entry["artifact_id"])
    archive = inputs / (key + ".zip")
    with archive.open("wb") as stream:
        subprocess.run(["gh", "api", "repos/SemperSupra/oneirifact/actions/artifacts/" + key + "/zip"], stdout=stream, check=True, timeout=120)
    assert archive.stat().st_size == entry["bytes"] and sha(archive.read_bytes()) == entry["sha256"], "Artifact custody mismatch"
    target = inputs / key
    target.mkdir()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for info in z.infolist():
            path = Path(info.filename)
            assert not path.is_absolute() and ".." not in path.parts
            assert not ((info.external_attr >> 16) & 0o170000) == 0o120000
        receipt_raw = z.read(entry["receipt"])
        producer = json.loads(receipt_raw)
        assert producer["source_head_commit"] == entry["producer_head"]
        verified = []
        for name, data in producer["files"].items():
            raw = z.read(name)
            assert len(raw) == data["bytes"] and sha(raw) == data["sha256"], "Producer receipt mismatch: " + name
            verified.append(name)
        selected = {}
        for name in (entry["receipt"], entry["blend"], entry["glb"]):
            raw = z.read(name)
            (target / name).write_bytes(raw)
            selected[name] = {"bytes": len(raw), "sha256": sha(raw)}
        row = {"input": entry, "source_receipt_sha256": sha(receipt_raw), "verified_inner_files": verified, "selected_files": selected, "input_path": key}
        receipts.append(row)
    # Raw archive is no longer needed; selected immutable native/GLB files remain
    # in the ephemeral input directory, never in the audit artifact or repository.
    archive.unlink()
    print("R249_INTAKE", json.dumps({"id": entry["id"], "artifact_id": entry["artifact_id"], "verified_inner_files": len(verified)}), flush=True)
result = {"schema": "oneirifact.quaternion-audit-custody/v1", "group": group, "source_head_commit": os.environ.get("SOURCE_HEAD_SHA"), "run_id": os.environ.get("GITHUB_RUN_ID"), "manifest_sha256": sha(manifest.read_bytes()), "cases": receipts}
(out / "input-custody.json").write_text(json.dumps(result, indent=2) + "\n")
