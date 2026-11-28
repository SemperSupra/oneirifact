"""Package actual aquatic geometry renders and verify complete MP4 decoding."""
import hashlib,json,subprocess,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops,ImageStat
import imageio_ffmpeg
out=Path(sys.argv[1]);path=out/"consumer-receipt.json";r=json.loads(path.read_text())
assert imageio_ffmpeg.__version__=="0.6.0";encoder=Path(imageio_ffmpeg.get_ffmpeg_exe())
version=subprocess.check_output([str(encoder),"-version"],text=True).splitlines()[0]
binary_sha=hashlib.sha256(encoder.read_bytes()).hexdigest()
assert binary_sha=="e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99"
r["encoder"]={"dependency":"imageio-ffmpeg==0.6.0","wheel_sha256":"c7e46fcec401dd990405049d2e2f475e2b397779df2519b544b8aab515195282","binary_sha256":binary_sha,"version":version}
for video in r["videos"]:
    frames=sorted((out/video["folder"]).glob("*.png"));assert len(frames)==video["frames"]
    samples={i:Image.open(frames[i]).convert("RGB").copy() for i in sorted({0,len(frames)//2,len(frames)-1})};w,h=samples[0].size
    dest=out/(video["activity_id"]+".mp4")
    subprocess.run([str(encoder),"-hide_banner","-loglevel","error","-y","-framerate",str(video["fps"]),"-i",str(out/video["folder"]/"%04d.png"),"-c:v","libx264","-preset","fast","-crf","21","-pix_fmt","yuv420p","-movflags","+faststart",str(dest)],check=True)
    decoded=subprocess.run([str(encoder),"-hide_banner","-loglevel","error","-i",str(dest),"-f","rawvideo","-pix_fmt","rgb24","-"],check=True,stdout=subprocess.PIPE).stdout
    assert len(decoded)==w*h*3*len(frames);errors=[]
    for i,source in samples.items():
        img=Image.frombytes("RGB",(w,h),decoded[i*w*h*3:(i+1)*w*h*3]);error=max(ImageStat.Stat(ImageChops.difference(source,img)).mean);assert error<8.
        errors.append({"frame":i,"mean_channel_error_255":error})
    count,seconds=imageio_ffmpeg.count_frames_and_secs(str(dest));assert count==len(frames) and abs(seconds-count/video["fps"])<.13
    video.update(file=dest.name,width=w,height=h,decoded_frames=count,encoded_duration_s=seconds,decode_status="PASS",source_samples=errors,sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    (out/(video["activity_id"]+"-frame-hashes.json")).write_text(json.dumps([{ "frame":i,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for i,p in enumerate(frames)],indent=2)+"\n")
    for p in frames:p.unlink()
    (out/video["folder"]).rmdir()
font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font=lambda n:ImageFont.truetype(font_path,n)
board=Image.new("RGB",(1316,1198),(16,24,35));draw=ImageDraw.Draw(board)
draw.text((20,18),"R246 / ACTUAL AQUATIC MOTION PROTOTYPES",font=font(31),fill=(239,244,247))
draw.text((20,60),r["case"]["id"]+" / explicitly barefoot / source rig and full skin weights preserved",font=font(22),fill=(127,212,215))
draw.text((20,98),"Static water and tub context. Observed native poses; no fluid, contact or motion-realism admission.",font=font(19),fill=(177,195,208))
items=[("01-crawl-entry.png","Front crawl / entry"),("02-crawl-recovery.png","Front crawl / arm recovery"),("03-seated-wash.png","Tub context / seated chest wash"),("04-wash-sweep.png","Rigid sponge / observed source chest vertex")]
for i,(name,label) in enumerate(items):
    x=12+(i%2)*652;y=140+(i//2)*522;board.paste(Image.open(out/name).convert("RGB"),(x,y));draw.text((x+8,y+484),label,font=font(22),fill=(239,244,247))
board.save(out/"aquatic-native-contact-sheet.png",optimize=True)
r["independent_critics"]={}
for phase in ("native-ik","reopened-blend","consumer"):
    p=out/("native-critic-"+phase+".json")
    if p.exists():
        critic=json.loads(p.read_text())
        r["independent_critics"][phase]={k:critic[k] for k in ("failed_or_invalid_clip_count","incomplete_clip_count","realism")}
        r["independent_critics"][phase]["clips"]=[{"activity_id":clip.get("activity_id"),"status":clip["status"],"failed_gates":clip.get("failed_gates",[])} for case in critic["cases"] for clip in case["clips"]]
r["contact_acceptance"]="Bounded actual-observation screens reported separately; physical contact and forces remain unqualified"
r["actual_footwear"]="barefoot; no footwear meshes in native render or body GLB"
r["files"]={p.name:{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file() and p!=path}
path.write_text(json.dumps(r,indent=2)+"\n")
print("R246_PACKAGED",json.dumps({"case":r["case"]["id"],"status":r["status"],"videos":r["videos"],"critics":r["independent_critics"]}),flush=True)
