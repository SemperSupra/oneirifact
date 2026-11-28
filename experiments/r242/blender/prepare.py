"""Verify exact public archives and prepare one independent Blender consumer."""
import hashlib, json, sys, zipfile
from pathlib import Path
PINS = {
 "male": ("15c35738f128cdab948f7f727091f32875288ec3bc6a2b55dfd69d20d5ed9e31", "male-athletic-anatomical-candidate.glb", "glb_sha256"),
 "female": ("45b6e0650ceee40acf62ee67d227aaf6b9542a3b5af6b1dceb344f02b25e5886", "female-athletic-ct-roll-candidate.glb", "candidate_glb_sha256"),
}
REFERENCE = "f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f"
def sha(data): return hashlib.sha256(data).hexdigest()
def main(sex, candidate, reference, out):
    expected, filename, key = PINS[sex]
    assert sha(candidate.read_bytes()) == expected, "candidate archive digest"
    assert sha(reference.read_bytes()) == REFERENCE, "reference archive digest"
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(candidate) as z, zipfile.ZipFile(reference) as ref:
        assert z.testzip() is None and ref.testzip() is None, "archive CRC"
        receipt = json.loads(z.read("receipt.json")); raw = z.read(filename)
        assert sha(raw) == receipt[key], "source GLB inner digest"
        (out / filename).write_bytes(raw)
        (out / "input-registration-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        for name in z.namelist():
            if name.startswith("LICENSE") or name == "ATTRIBUTION.txt":
                assert "/" not in name and "\\" not in name
                (out / name).write_bytes(z.read(name))
        refname = sex + "-athletic-cpu-reference.npz"
        (out / refname).write_bytes(ref.read(refname))
    meta = {"sex": sex, "model": filename, "candidate_archive_sha256": expected,
            "reference_archive_sha256": REFERENCE, "glb_sha256": sha(raw),
            "reference_file_sha256": sha((out/refname).read_bytes())}
    (out / "input.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("R242_INPUT", json.dumps(meta), flush=True)
if __name__ == "__main__":
    main(sys.argv[1], *(Path(x) for x in sys.argv[2:]))
