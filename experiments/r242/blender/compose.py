"""Assemble actual Blender render panels without changing the rendered geometry."""
import hashlib,json,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(sys.argv[1]);sex=sys.argv[2];font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
title=ImageFont.truetype(font,30);label=ImageFont.truetype(font,23);small=ImageFont.truetype(font,19)
image=Image.new("RGB",(1800,986),"#101c29");d=ImageDraw.Draw(image)
d.text((25,18),sex.title()+" integrated model — actual Blender 5.2.4 consumer",font=title,fill="#e8f0f5")
d.text((25,58),"Nine pelvic/leg bone components · full-weight animated exterior · cross-donor anatomical fit remains held",font=small,fill="#b3c7d5")
panels=[("exterior-pose","Exterior / diagnostic pose"),("anatomy-rest","Pelvis + legs / rest"),("anatomy-pose","Pelvis + legs / diagnostic pose")]
for i,(name,caption) in enumerate(panels):
    p=Image.open(root/(sex+"-"+name+".png")).convert("RGB");assert p.size==(600,840)
    image.paste(p,(600*i,106));d.text((600*i+22,82),caption,font=label,fill="#e8f0f5")
d.text((25,958),"Actual imported surfaces; transparency reveals internal geometry. No clinical, contact, completeness or native-engine acceptance.",font=small,fill="#b3c7d5")
path=root/(sex+"-integrated-blender-review.png");image.save(path)
receipt=json.loads((root/"blender-consumer-receipt.json").read_text())
receipt["files"][path.name]={"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
(root/"blender-consumer-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
