"""Recover only the qualified two-capture intake; preserve provenance/notices."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

archive, selected, product, addon = map(Path, sys.argv[1:5])
expected = "bd347c991cbc5887e2d074a60385b19aaaeac337ad2fa294070fa1733b215e28"
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
assert sha(archive.read_bytes()) == expected
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for info in z.infolist():
        path = Path(info.filename)
        assert not path.is_absolute() and ".." not in path.parts
        assert not ((info.external_attr >> 16) & 0o170000) == 0o120000
    intake = json.loads(z.read("source-intake.json"))
    assert intake["status"] == "PASS_SELECTED_SOURCE_INTAKE"
    assert intake["source_head"] == "7cd5ebcf9f99756bde9911ff4eb388fc838c9b35"
    assert str(intake["run_id"]) == "46152658438"
    assert set(intake["files"]) == {"07_01.bvh", "13_01.bvh", "CMU_07_01-READMEFIRST.txt", "CMU_13_01-READMEFIRST.txt"}
    selected.mkdir(parents=True, exist_ok=False)
    for name, meta in intake["files"].items():
        raw = z.read(name)
        assert len(raw) == meta["bytes"] and sha(raw) == meta["sha256"]
        (selected / name).write_bytes(raw)
        if name.endswith(".txt"):
            (product / name).write_bytes(raw)
    (product / "qualified-source-intake.json").write_bytes(z.read("source-intake.json"))
commit = subprocess.check_output(["git", "-C", str(addon), "rev-parse", "HEAD"], text=True).strip()
assert commit == "8501d53f66fffa8d2574a01532c30e195c8d2998"
license_path = addon / "LICENSE"
(product / "RETARGETER-LICENSE.txt").write_bytes(license_path.read_bytes())
paths = subprocess.check_output(["git", "-C", str(addon), "ls-files"], text=True).splitlines()
donor_files = {name: sha((addon / name).read_bytes()) for name in paths if (addon / name).is_file()}
here = Path(__file__).resolve().parent
implementation = {path.name: sha(path.read_bytes()) for path in sorted(here.glob("*.py"))}
consumer = here.parents[1] / "r245" / "consumer"
prep_hashes = {name: sha((consumer / name).read_bytes()) for name in ("prepare.py", "gltf.py")}
assert prep_hashes == {"prepare.py": "9c1ff2571f4ed5515b3c05d377fabd217e7f49eacf2ee4347a86bb34ffa2d66d", "gltf.py": "efce3c66622cc303fef03cc552c29f7e369d13206bf2fb53a2598d24d69aec1e"}
receipt = {"schema": "oneirifact.captured-motion-input-lock/v1", "source_intake_artifact_id": 15266376154, "source_intake_archive_sha256": expected, "source_intake_head": intake["source_head"], "source_intake_run": intake["run_id"], "retargeter_commit": commit, "retargeter_files_sha256": donor_files, "implementation_sha256": implementation, "frozen_consumer_parent": "7fc8141fef8e2133ecceb2474005e82da4da69ad", "preparation_file_sha256": prep_hashes, "source_rights": intake["rights"], "raw_bvh_in_product_or_git": False, "native_action_is_derived_capture_product": True}
(product / "input-lock.json").write_text(json.dumps(receipt, indent=2) + "\n")
print("R247_CUSTODY", json.dumps({"capture_files": 2, "archive_sha256": expected, "donor_commit": commit, "source_notices_preserved": True}))
