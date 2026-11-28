"""Package actual rendered frames, independent critic results and replay files."""
import hashlib,json,subprocess,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
out=Path(sys.argv[1]);receipt_path=out/"consumer-receipt.json"
receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else {"status":"INCOMPLETE_CONSUMER_RUN","videos":[],"files":{}}
def font(size):
    path=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(str(path),size) if path.exists() else ImageFont.load_default()
renders=[("01-standing.png","Standing","Relaxed authored arm targets"),("02-sitting.png","Sitting","Chair is support context; contact unqualified"),
 ("03-squat.png","Squat","Native two-link solve; original segment bones"),("04-walk.png","Walking","Authored world-anchored support phases"),
 ("05-brushing.png","Hand-to-mouth task","Rigid brush proxy; grip/contact unqualified"),("06-footwear.png","Footwear support geometry","Actual heel, forefoot and articulated toe")]
if all((out/p).exists() for p,_,_ in renders):
    board=Image.new("RGB",(1308,1402),(16,24,35));draw=ImageDraw.Draw(board)
    case=receipt.get("case",json.loads((out/"case.json").read_text()))
    draw.text((24,20),"R245 / ACTUAL BLENDER ACTIVITY PROTOTYPES",font=font(31),fill=(238,243,247))
    draw.text((24,64),case["id"]+"  |  "+case["shoe_profile"]+"  |  "+format(case["morphology"]["stature_m"],".3f")+" m",font=font(22),fill=(123,211,213))
    draw.text((24,100),"Original full-weight skin and 163-bone rig. Authored kinematics; motion realism remains unqualified.",font=font(19),fill=(184,198,211))
    for i,(path,title,subtitle) in enumerate(renders):
        x=16+(i%3)*432;y=146+(i//3)*610
        board.paste(Image.open(out/path).convert("RGB"),(x,y))
        draw.text((x+8,y+566),title,font=font(22),fill=(238,243,247))
        draw.text((x+8,y+594),subtitle,font=font(13),fill=(173,189,205))
    board.save(out/"activity-contact-sheet.png",optimize=True)
for video in receipt.get("videos",[]):
    destination=out/(video["activity_id"]+".mp4")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate",str(video["fps"]),"-i",str(out/video["folder"]/"%04d.png"),
      "-c:v","libx264","-preset","fast","-crf","21","-pix_fmt","yuv420p","-movflags","+faststart",str(destination)],check=True)
    video["file"]=destination.name;video["bytes"]=destination.stat().st_size;video["sha256"]=hashlib.sha256(destination.read_bytes()).hexdigest()
    # Preview frames are reproducible from the included scene/source; retain MP4 and contact-sheet stills.
    for p in (out/video["folder"]).glob("*.png"):p.unlink()
    (out/video["folder"]).rmdir()
critics={}
for path in out.glob("independent-critic*.json"):
    r=json.loads(path.read_text());critics[path.name]={"failed_or_invalid_clip_count":r["failed_or_invalid_clip_count"],
       "clips":[{"activity_id":c.get("activity_id"),"status":c["status"],"failed_gates":c.get("failed_gates",[])} for case in r["cases"] for c in case["clips"]]}
receipt["independent_critics"]=critics
receipt["contact_acceptance"]="BOUNDED_RESULTS_REPORTED_WITH_LIMITATIONS" if critics else "NOT_RUN"
receipt["files"]={p.name:{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file() and p!=receipt_path}
receipt_path.write_text(json.dumps(receipt,indent=2)+"\n")
print("R245_PACKAGED",json.dumps({"status":receipt["status"],"videos":len(receipt["videos"]),"critics":critics}),flush=True)
