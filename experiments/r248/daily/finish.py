"""Explicit encoder, decoded actual video witness and dense daily coverage ledger."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw,ImageFont,ImageStat
import imageio_ffmpeg

out=Path(sys.argv[1]);p=out/"consumer-receipt.json"
receipt=json.loads(p.read_text());assert receipt["extension"]["id"]=="r248-dense-daily-activity"
assert receipt["status"]=="PASS_NATIVE_CONSUMER_TRANSPORT"
assert all(x["evaluated_frames"]==x["authored_frames"] for x in receipt["activities"])
encoder=Path(imageio_ffmpeg.get_ffmpeg_exe())
binary_sha=hashlib.sha256(encoder.read_bytes()).hexdigest()
assert imageio_ffmpeg.__version__=="0.6.0" and binary_sha=="e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99"
bindir=out.parent/"daily-encoder-bin";bindir.mkdir(exist_ok=True)
link=bindir/"ffmpeg"
if not link.exists():link.symlink_to(encoder)
env=dict(os.environ);env["PATH"]=str(bindir)+os.pathsep+env.get("PATH","")
samples={};frame_manifest={}
for video in receipt["videos"]:
    frames=sorted((out/video["folder"]).glob("*.png"));assert len(frames)==video["frames"]
    samples[video["activity_id"]]={i:Image.open(frames[i]).convert("RGB").copy() for i in {0,len(frames)//2,len(frames)-1}}
    frame_manifest[video["activity_id"]]=[{"name":str(f.relative_to(out)),"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()} for f in frames]
(out/"source-render-frame-manifest.json").write_text(json.dumps(frame_manifest,indent=2)+"\n")
base=Path(__file__).resolve().parents[2]/"r245/consumer/finish.py"
subprocess.run([sys.executable,str(base),str(out)],env=env,check=True)
validation=[]
for video in receipt["videos"]:
    name=video["activity_id"];ref=samples[name];size=next(iter(ref.values())).size;w,h=size
    raw=subprocess.check_output([str(encoder),"-hide_banner","-loglevel","error","-i",str(out/(name+".mp4")),"-f","rawvideo","-pix_fmt","rgb24","-"])
    count=len(raw)//(w*h*3);assert len(raw)%(w*h*3)==0 and count==video["frames"]
    errors=[]
    for i,source in sorted(ref.items()):
        image=Image.frombytes("RGB",size,raw[i*w*h*3:(i+1)*w*h*3])
        error=max(ImageStat.Stat(ImageChops.difference(source,image)).mean);assert error<8
        errors.append({"frame":i,"max_channel_mean_error_255":error})
    frames,seconds=imageio_ffmpeg.count_frames_and_secs(str(out/(name+".mp4")))
    assert frames==count and abs(seconds-count/video["fps"])<.13
    validation.append({"activity_id":name,"status":"PASS_FULL_DECODE","frame_count":count,"fps":video["fps"],"duration_s":seconds,"source_image_samples":errors})

font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font=lambda size:ImageFont.truetype(font_path,size)
board=Image.new("RGB",(1308,1402),(16,24,35));draw=ImageDraw.Draw(board)
draw.text((24,18),"R248 / DENSE DAILY & FITNESS REPLAY",font=font(31),fill=(238,243,247))
draw.text((24,61),receipt["case"]["id"]+" | all 12 entries at authored 24 fps",font=font(22),fill=(123,211,213))
draw.text((24,100),"Actual Blender render. Authored kinematics; realism, grip and water mechanics remain unqualified.",font=font(18),fill=(184,198,211))
views=[("02-sitting.png","Sit-to-stand","Full sampled transition"),("07-crouching.png","Crouching","Full sampled hold"),("08-jogging.png","Jogging","Full sampled contact phases"),("09-running.png","Running","Full sampled contact phases"),("10-showering.png","Showering","Head-wash intent / fixed context lines"),("11-ice-cream.png","Ice-cream cone","Rigid prop / measured tip, grip unqualified")]
for i,(name,title,note) in enumerate(views):
    x=16+(i%3)*432;y=146+(i//3)*610
    board.paste(Image.open(out/name).convert("RGB"),(x,y))
    draw.text((x+8,y+566),title,font=font(22),fill=(238,243,247))
    draw.text((x+8,y+594),note,font=font(14),fill=(173,189,205))
board.save(out/"daily-contact-sheet.png",optimize=True)
prop_metrics={}
for phase in ("native-ik","reopened-blend","consumer"):
    observations=json.loads((out/(phase+"-observations.json")).read_text())
    distances={}
    for case in observations["cases"]:
        for clip in case["clips"]:
            for row in clip["frames"]:
                for key in ("ice_cream_tip_to_mouth_proxy_m","toothbrush_tip_to_mouth_proxy_m"):
                    if key in row["actual"]:distances.setdefault(key,[]).append(row["actual"][key])
    prop_metrics[phase]={k:{"samples":len(v),"minimum_m":min(v),"maximum_m":max(v),"contact_acceptance":"NOT_QUALIFIED"} for k,v in distances.items()}
extension={"schema":"oneirifact.dense-daily-product/v1","status":"PASS_TRANSPORT_DENSE_COVERAGE_AND_VIDEO_DECODE","source_head_commit":receipt["source_head_commit"],"run_id":receipt["run_id"],"encoder":{"package":"imageio-ffmpeg==0.6.0","binary_sha256":binary_sha,"version":subprocess.check_output([str(encoder),"-version"],text=True).splitlines()[0]},"videos":validation,"actual_prop_metrics":prop_metrics,"realism":"NOT_QUALIFIED"}
(out/"daily-product-receipt.json").write_text(json.dumps(extension,indent=2)+"\n")
receipt=json.loads(p.read_text());receipt["files"]={f.name:{"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(out.iterdir()) if f.is_file() and f!=p}
p.write_text(json.dumps(receipt,indent=2)+"\n")
print("R248_COMPLETE",json.dumps(extension),flush=True)
