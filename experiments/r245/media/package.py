"""Recover MP4 products from immutable actual Blender render archives on public CPU.

This does not rerender, re-solve motion, change source models, or transfer realism.
The preserved producer receipt and the packaging receipt have separate identities.
"""
import hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
import imageio_ffmpeg

archive=Path(sys.argv[1]);expected=sys.argv[2];artifact_id=int(sys.argv[3]);out=Path(sys.argv[4])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(archive)==expected,"source archive SHA mismatch"
out.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None,"source archive CRC failure"
    for info in z.infolist():
        path=Path(info.filename)
        assert not path.is_absolute() and ".." not in path.parts,"unsafe artifact path"
        assert not ((info.external_attr>>16)&0o170000)==0o120000,"symlinks are not source render evidence"
    z.extractall(out)
receipt_path=out/"consumer-receipt.json";original=receipt_path.read_bytes();producer=json.loads(original)
assert producer["status"]=="PASS_NATIVE_CONSUMER_TRANSPORT"
assert producer["source_head_commit"]=="7fc8141fef8e2133ecceb2474005e82da4da69ad" and str(producer["run_id"])=="46152155189"
checked=[]
for name,entry in producer["files"].items():
    path=out/name;assert path.is_file() and path.stat().st_size==entry["bytes"] and sha(path)==entry["sha256"],"producer inner-file custody mismatch: "+name
    checked.append(name)
(out/"source-consumer-receipt.json").write_bytes(original)
assert imageio_ffmpeg.__version__=="0.6.0"
encoder=Path(imageio_ffmpeg.get_ffmpeg_exe());version=subprocess.check_output([str(encoder),"-version"],text=True).splitlines()[0]
localbin=out.parent/(out.name+"-encoder-bin");localbin.mkdir();(localbin/"ffmpeg").symlink_to(encoder)
environment=dict(os.environ);environment["PATH"]=str(localbin)+os.pathsep+environment.get("PATH","")
inputs={};frame_manifest={}
for video in producer["videos"]:
    paths=sorted((out/video["folder"]).glob("*.png"));assert len(paths)==video["frames"] and paths
    first=Image.open(paths[0]).convert("RGB");size=first.size
    assert all(Image.open(p).size==size for p in paths)
    samples={i:Image.open(paths[i]).convert("RGB").copy() for i in sorted({0,len(paths)//2,len(paths)-1})}
    inputs[video["activity_id"]]={"size":size,"frame_count":len(paths),"fps":video["fps"],"samples":samples}
    frame_manifest[video["activity_id"]]=[{"name":str(p.relative_to(out)),"bytes":p.stat().st_size,"sha256":sha(p)} for p in paths]
(out/"source-render-frame-manifest.json").write_text(json.dumps(frame_manifest,indent=2)+"\n")
finish=Path(__file__).resolve().parents[1]/"consumer"/"finish.py"
subprocess.run([sys.executable,str(finish),str(out)],env=environment,check=True)
validation=[]
for activity,data in inputs.items():
    mp4=out/(activity+".mp4");w,h=data["size"]
    decoded=subprocess.run([str(encoder),"-hide_banner","-loglevel","error","-i",str(mp4),"-f","rawvideo","-pix_fmt","rgb24","-"],check=True,stdout=subprocess.PIPE).stdout
    frame_bytes=w*h*3;assert len(decoded)%frame_bytes==0
    count=len(decoded)//frame_bytes;assert count==data["frame_count"],"MP4 lost or duplicated source frames"
    errors=[]
    for index,source in data["samples"].items():
        result=Image.frombytes("RGB",(w,h),decoded[index*frame_bytes:(index+1)*frame_bytes])
        mean=max(ImageStat.Stat(ImageChops.difference(source,result)).mean)
        assert mean<8.,"encoded visual error exceeds declared 8/255 mean per-channel tolerance"
        errors.append({"frame":index,"max_channel_mean_abs_error_255":mean})
    frames,seconds=imageio_ffmpeg.count_frames_and_secs(str(mp4));assert frames==count and abs(seconds-count/data["fps"])<.13
    validation.append({"activity_id":activity,"status":"PASS_ENCODE_AND_FULL_DECODE","width":w,"height":h,"frame_count":count,"fps":data["fps"],"duration_s":seconds,"source_frame_samples":errors,"mp4_sha256":sha(mp4)})
recovery={"schema":"oneirifact.render-media-recovery/v1","status":"PASS_MEDIA_PACKAGING_AND_DECODE","source_artifact_id":artifact_id,
 "source_archive_sha256":expected,"source_archive_bytes":archive.stat().st_size,"source_run_id":producer["run_id"],"source_head_commit":producer["source_head_commit"],
 "packager_run_id":os.environ.get("GITHUB_RUN_ID"),"packager_head_commit":os.environ.get("SOURCE_HEAD_SHA"),
 "original_failure":"Public ubuntu-24.04 runner had no ffmpeg executable; Blender production/replay and independent kinematic critics had already completed.",
 "source_consumer_status":producer["status"],"verified_producer_inner_files":checked,
 "encoder":{"dependency":"imageio-ffmpeg==0.6.0","wheel_sha256":"c7e46fcec401dd990405049d2e2f475e2b397779df2519b544b8aab515195282","version":version,"binary_sha256":sha(encoder)},
 "videos":validation,"scope":"Actual preserved CPU-rendered source frames encoded to MP4. Full decoder frame counts and first/middle/last lossy visual errors checked. No model, motion, anatomy or realism changes/admission."}
(out/"media-packaging-receipt.json").write_text(json.dumps(recovery,indent=2)+"\n")
receipt=json.loads(receipt_path.read_text());assert receipt["source_head_commit"]==producer["source_head_commit"]
receipt["media_packaging"]={"status":recovery["status"],"packager_run_id":recovery["packager_run_id"],"packager_head_commit":recovery["packager_head_commit"],"source_artifact_id":artifact_id,"source_archive_sha256":expected}
receipt["files"]={p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(out.iterdir()) if p.is_file() and p!=receipt_path}
receipt_path.write_text(json.dumps(receipt,indent=2)+"\n")
print("R245_MEDIA_COMPLETE",json.dumps({"case":producer["case"]["id"],"status":recovery["status"],"producer_status":producer["status"],"videos":validation,"encoder":recovery["encoder"]}),flush=True)
