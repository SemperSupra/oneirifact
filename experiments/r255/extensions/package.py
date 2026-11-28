"""Actual rendered media, full decode verification and immutable gallery catalog."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import imageio_ffmpeg

ROOT=Path(sys.argv[1]);INPUT=Path(sys.argv[2]);GROUP=sys.argv[3]
PACK="r255-"+GROUP+"-v1"
ENCODER="e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99"
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+"\n")
def asset(p):return {"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":sha(p.read_bytes())}
font_path=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
font=ImageFont.truetype(str(font_path),17) if font_path.exists() else ImageFont.load_default()
small=ImageFont.truetype(str(font_path),13) if font_path.exists() else ImageFont.load_default()
encoder=Path(imageio_ffmpeg.get_ffmpeg_exe());assert sha(encoder.read_bytes())==ENCODER
version=subprocess.check_output([str(encoder),"-version"],text=True).splitlines()[0]
packages=[];media=[]
for folder in sorted(ROOT.iterdir()):
    if not folder.is_dir() or not (folder/"receipt.json").exists():continue
    receipt=json.loads((folder/"receipt.json").read_text());activity=receipt["id"];spec=receipt["video"]
    assert receipt["transport"]=="PASS" and spec
    frames=sorted((folder/"frames").glob("*.png"));assert len(frames)==spec["frames"]
    movie=folder/"preview.mp4"
    subprocess.run([str(encoder),"-hide_banner","-loglevel","error","-framerate",str(spec["fps"]),"-i",str(folder/"frames"/"%04d.png"),"-c:v","libx264","-preset","fast","-crf","19","-pix_fmt","yuv420p","-movflags","+faststart","-y",str(movie)],check=True)
    W,H=Image.open(frames[0]).size
    decoded=subprocess.check_output([str(encoder),"-v","error","-i",str(movie),"-f","rawvideo","-pix_fmt","rgb24","-"])
    framebytes=W*H*3;assert len(decoded)==len(frames)*framebytes
    samples=[]
    for idx in (0,len(frames)//2,len(frames)-1):
        actual=decoded[idx*framebytes:(idx+1)*framebytes];original=Image.open(frames[idx]).convert("RGB").tobytes()
        err=sum(abs(a-b) for a,b in zip(actual,original))/len(original);samples.append({"frame":idx,"mean_channel_error_255":err});assert err<8
    poster=folder/"poster.png";shutil.copyfile(frames[len(frames)//2],poster)
    ids=[round(i*(len(frames)-1)/4) for i in range(5)];sheet=Image.new("RGB",(W*5, H+94),(14,22,34));draw=ImageDraw.Draw(sheet)
    draw.text((16,12),activity.replace("_"," ").title()+" — original authored kinematics",font=font,fill="white")
    draw.text((16,37),"Transport "+receipt["transport"]+" | Contact "+receipt["contact"]+" | Physics NOT SIMULATED | Realism HELD",font=small,fill=(255,193,112))
    for col,idx in enumerate(ids):
        sheet.paste(Image.open(frames[idx]).convert("RGB"),(col*W,72));draw.text((col*W+10,H+75),f"t = {idx/spec['fps']:.3f} s",font=small,fill="white")
    sheet.save(folder/"contact-sheet.png")
    rights=folder/"rights.txt";licenses=[]
    for case in sorted({a["case_id"] for a in receipt["actors"]}):
        for name in ("LICENSE.md","LICENSE.ASSETS.md"):
            path=INPUT/case/name
            if path.exists():licenses.append("\n=== "+case+" / "+name+" ===\n"+path.read_text())
    rights.write_text("Oneirifact R255 original authored motion and native-source derivatives.\nNo captured-motion input is used. No captured dataset rights are inferred.\nThe original source notices below apply to source geometry and inherited code.\n\n"+"\n".join(licenses))
    verification={"encoder_version":version,"encoder_binary_sha256":ENCODER,"full_decode_frames":len(frames),"source_frames":len(frames),"sampled_pixel_errors":samples,"preview_fps":spec["fps"],"native_fps":24,"frames_are_actual_native_cpu_renders":True}
    save(folder/"media-verification.json",verification);media.append({"activity":activity,**verification})
    preview={**asset(movie),"fps":spec["fps"],"frames":len(frames),"duration_s":len(frames)/spec["fps"]}
    actors=[{"id":a["id"],"sex_variant":a["sex_variant"],"stature_m":a["stature_m"],"morphology_label":a["case_id"],"footwear":a["footwear"],"source_bind_sha256":a["source_bind_sha256"]} for a in receipt["actors"]]
    packages.append({"id":"r255-"+activity.replace("_","-"),"title":activity.replace("_"," ").title(),"group":GROUP,"source_kind":"authored","actors":actors,
       "clips":[{"id":activity,"title":activity.replace("_"," ").title(),"animation_name":activity,"duration_s":receipt["duration_s"],"evaluation":"Authored kinematic study; "+receipt["contact"]+"; realism and technique held","preview":preview}],
       "assets":{"model":asset(folder/"motion.glb"),"native_scene":asset(folder/"motion.blend"),"poster":asset(poster),"contact_sheet":asset(folder/"contact-sheet.png"),"receipt":asset(folder/"receipt.json"),"rights":asset(rights)},
       "provenance":{"repository":"SemperSupra/oneirifact","producer_head":receipt["source_head_commit"],"producer_run_id":receipt["run_id"],"provider_artifact":"RESOLVED_BY_POST_UPLOAD_RELEASE_LOCK","source_revision":receipt["source_parent"],"source_artifact_id":15266855834,"source_archive_sha256":"e694ab4d06bae33bf829e624d03a2bd81bb28d8b8059c42ae83e36819f33dd68","source_notices":asset(rights)},
       "qualification":{"transport":receipt["transport"],"realism":receipt["realism"],"contact":receipt["contact"],"physics":receipt["physics"],"retarget":receipt["retarget"]},
       "included_layers":receipt["included_layers"],"omitted_layers":receipt["omitted_layers"],"notes":[receipt["scope"],"Any failed contact or silhouette remains visible and explicitly unaccepted. Native and GLB transport do not imply valid technique.","Video cadence differs from 24 fps native animation."],"model_inventory":receipt["model_inventory"]})
    # Render frames are reproducible intermediates; package exact native/media instead.
    shutil.rmtree(folder/"frames")
catalog={"schema":"oneirifact.motion-browser/v1","pack_id":PACK,"title":"R255 "+GROUP.replace("-"," "),"packages":packages,"scope":"Original authored extension prototypes with full source weights and paired actors where declared. No capture, physics, contact or realism acceptance inferred from successful transport."}
save(ROOT/"catalog.json",catalog);save(ROOT/"media-verification.json",media)
files=[asset(p) for p in sorted(ROOT.rglob("*")) if p.is_file() and p.name!="producer-manifest.json"]
save(ROOT/"producer-manifest.json",{"schema":"oneirifact.motion-extension-producer-manifest/v1","pack_id":PACK,"head":os.environ.get("SOURCE_HEAD_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),"release_normalization":"Canonical release pack manifest is independently assembled after artifact intake.","files":files})
print(json.dumps({"pack_id":PACK,"packages":len(packages),"files":len(files),"bytes":sum(x["bytes"] for x in files),"media":len(media)}))
