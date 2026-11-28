"""Report bounded product completeness after preserving every critic/render result."""
import hashlib,json,os,sys
from pathlib import Path

out=Path(sys.argv[1]);errors=[];critics={};receipt_path=out/"consumer-receipt.json"
receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
if receipt.get("status")!="PASS_NATIVE_CONSUMER_TRANSPORT":errors.append("native consumer transport absent or failed")
if not receipt.get("export",{}).get("full_source_attributes_bit_identical"):errors.append("exact source geometry/weights export absent")
interpolation=receipt.get("interpolation",{})
if set(interpolation)!={"swimming_front_crawl","bathing_seated_wash"}:errors.append("native quaternion continuity evidence absent")
for activity,info in interpolation.items():
    times=info.get("fractional_replay_times_s",[])
    if len(times)<2:errors.append("missing general fractional seeks for "+activity)
    for cross in info.get("raw_sign_transitions",[]):
        if not any(abs(t-cross["midpoint_time_s"])<1e-8 for t in times):errors.append("unprobed quaternion sign-transition midpoint")
    for phase in ("saved_blend_reopened","baked_glb_reimported"):
        for t in times:
            if not any(c.get("phase")==phase and c.get("activity_id")==activity and abs(c.get("time_s",-1)-t)<1e-8 for c in receipt.get("checks",[])):
                errors.append("missing adaptive fractional transport "+activity+" / "+phase+" / "+str(t))
for name in ("aquatic-prototypes.blend","aquatic-prototypes.glb","aquatic-native-contact-sheet.png"):
    if not (out/name).is_file():errors.append("missing product "+name)
for phase in ("native-ik","reopened-blend","consumer"):
    path=out/("native-critic-"+phase+".json")
    if not path.exists():errors.append("missing independent critic "+phase);continue
    critic=json.loads(path.read_text());critics[phase]={k:critic.get(k) for k in ("failed_or_invalid_clip_count","incomplete_clip_count","realism")}
    if critic.get("failed_or_invalid_clip_count")!=0 or critic.get("incomplete_clip_count")!=0:
        errors.append("bounded observed gates failed or incomplete: "+phase)
videos=receipt.get("videos",[])
oracle_path=out/"native-critic-analytic-oracles.json"
oracles=json.loads(oracle_path.read_text()) if oracle_path.exists() else {}
if oracles.get("status")!="PASS_CONTROLLED_CORRUPTION_PROBES" or oracles.get("baseline_failed_or_invalid_clips")!=0 or oracles.get("baseline_incomplete_clips")!=0:
    errors.append("independent controlled-corruption probes absent, failed or incomplete")
if len(videos)!=2 or any(v.get("decode_status")!="PASS" or not v.get("decoded_frames") for v in videos):
    errors.append("two completely decoded video products required")
production=os.environ.get("GITHUB_ACTIONS")=="true"
if production:
    if receipt.get("source_head_commit")!=os.environ.get("SOURCE_HEAD_SHA"):errors.append("producer source head mismatch")
    if not str(receipt.get("blender_version","")).startswith("5.2.4"):errors.append("unqualified production Blender version")
report={"schema":"oneirifact.aquatic-native-qualification/v1","status":"FAIL_BOUNDED_AQUATIC_CONSUMER" if errors else "PASS_BOUNDED_AQUATIC_CONSUMER",
        "evidence_substrate":"PUBLIC_STANDARD_GITHUB_RUNNER" if production else "LOCAL_PREFLIGHT_ONLY",
        "source_head_commit":receipt.get("source_head_commit"),"run_id":receipt.get("run_id"),"errors":errors,"critics":critics,
        "controlled_corruptions":{"status":oracles.get("status"),"probes":len(oracles.get("probes",[])),"failed_controls":oracles.get("failed_controls"),"not_run_controls":oracles.get("not_run_controls")},
        "scope":"Transport, immutable source attributes, complete authored-frame observation screens and actual decoded render products only.",
        "realism":"NOT_QUALIFIED","physical_contact":"NOT_QUALIFIED","fluid_forces_and_buoyancy":"NOT_QUALIFIED"}
out.mkdir(parents=True,exist_ok=True)
(out/"qualification.json").write_text(json.dumps(report,indent=2)+"\n")
if receipt:
    receipt["bounded_product_qualification"]=report
    receipt["files"]={p.name:{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file() and p!=receipt_path}
    receipt_path.write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(report))
if errors:raise SystemExit(1)
