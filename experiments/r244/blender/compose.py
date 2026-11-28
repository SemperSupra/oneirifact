"""Compose three actual Blender source-reference renders."""
import hashlib,json,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
out=Path(sys.argv[1]);font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
title=ImageFont.truetype(font,30);label=ImageFont.truetype(font,23);small=ImageFont.truetype(font,19)
im=Image.new("RGB",(1800,1072),"#101c29");d=ImageDraw.Draw(im)
d.text((24,16),"BodyParts3D — actual source skin and skeletal layer",font=title,fill="#eaf1f5")
d.text((24,55),"Static source collection · original coordinates · one biological donor unestablished · no rig or animation",font=small,fill="#bfd0dc")
panels=[("source-skin.png","Source skin + separate hair"),("source-skeletal-layer.png","205 named skeletal-layer meshes"),("source-skin-skeletal-overlay.png","Transparent skin + skeletal layer")]
for i,(filename,caption) in enumerate(panels):
    img=Image.open(out/filename).convert("RGB");assert img.size==(600,920)
    im.paste(img,(600*i,105));d.text((600*i+22,80),caption,font=label,fill="#eaf1f5")
d.text((24,1037),"FJ2810 skin remains open (1,512 boundary edges). No hole closure or fitting; containment and anatomical completeness remain held.",font=small,fill="#bfd0dc")
path=out/"source-body-blender-review.png";im.save(path)
receipt=json.loads((out/"blender-consumer-receipt.json").read_text())
receipt["files"][path.name]={"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
(out/"blender-consumer-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
