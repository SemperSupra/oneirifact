"""Verify native scene outputs, actual image pixels and GLB structure independently."""
import hashlib
import json
import struct
from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageDraw, ImageStat

out=Path(sys.argv[1])
spec=Path(__file__).with_name("designs.json").read_bytes()
receipts=[]
images=[]
for ident in ("ripple","spiral"):
    folder=out/ident
    r=json.loads((folder/"receipt.json").read_text())
    assert r["blender"].startswith("5.2.4") and r["renderer"]=="Cycles CPU"
    assert r["source_sha256"]==hashlib.sha256(spec).hexdigest()
    assert r["profile"]==next(p for p in json.loads(spec)["profiles"] if p["id"]==ident)
    assert r["shade"]["vertices"]==2*128*33 and r["shade"]["volume_m3"]>0
    assert r["shade"]["faces"]==2*128*32+2*128
    wanted={"hero.png","lantern.blend","lantern.glb"}|({"detail.png"} if ident=="spiral" else set())
    assert set(r["files"])==wanted
    for name,meta in r["files"].items():
        data=(folder/name).read_bytes()
        assert len(data)==meta["bytes"] and hashlib.sha256(data).hexdigest()==meta["sha256"]
        if name.endswith(".png"):
            with Image.open(folder/name) as img:
                img.load()
                assert img.format=="PNG" and img.size==(640,480)
                rgb=img.convert("RGB")
                assert max(ImageStat.Stat(rgb).stddev)>12
                assert len(rgb.getcolors(65536) or [])!=1
                images.append((ident+" / "+name,rgb.copy()))
        elif name.endswith(".glb"):
            magic,version,length=struct.unpack_from("<4sII",data)
            assert magic==b"glTF" and version==2 and length==len(data)
            n,kind=struct.unpack_from("<II",data,12)
            assert kind==0x4e4f534a and n<=len(data)-20
            gltf=json.loads(data[20:20+n])
            nodes={v.get("name") for v in gltf["nodes"]}
            assert set(r["product_parts"])<=nodes and "Studio ground" not in nodes
            assert len(gltf["meshes"])>=5
        else:
            assert data.startswith((b"BLENDER",b"\x28\xb5\x2f\xfd"))
    receipts.append(r)
assert receipts[0]["shade"]["geometry_sha256"]!=receipts[1]["shade"]["geometry_sha256"]
with Image.open(out/"ripple/hero.png") as a,Image.open(out/"spiral/hero.png") as b:
    delta=ImageChops.difference(a.convert("RGB"),b.convert("RGB"))
    changed=sum(p!=(0,0,0) for p in delta.getdata())
    assert changed>30000
sheet=Image.new("RGB",(1280,1050),(23,26,32))
draw=ImageDraw.Draw(sheet)
for i,(label,img) in enumerate(images):
    x=(i%2)*640;y=(i//2)*520
    sheet.paste(img,(x,y+24));draw.text((x+12,y+6),label,fill="white")
sheet.save(out/"contact-sheet.png")
summary={"status":"PASS","scope":"Original public procedural design/native rendering only; not Oneirifact engine qualification",
         "variants":2,"rendered_images":len(images),"native_blends":2,"glb_models":2,
         "changed_hero_pixels":changed,"total_hero_pixels":640*480,
         "contact_sheet_sha256":hashlib.sha256((out/"contact-sheet.png").read_bytes()).hexdigest(),
         "variants_receipts":receipts}
(out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
print("LANTERN_INDEPENDENT_VERIFICATION",json.dumps(summary,sort_keys=True))
