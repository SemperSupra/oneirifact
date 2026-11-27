"""Create genuine render/model pairs from the original public pavilion recipe."""
import hashlib
import json
from pathlib import Path
import sys
import bpy

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import pavilion

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=2:
        raise SystemExit("usage: export_gallery.py -- PROFILE OUTPUT")
    profile_id, output=args
    out=Path(output).resolve()
    doc, raw=pavilion.load_specs(ROOT/"specs.json")
    profile=next(p for p in doc["profiles"] if p["id"]==profile_id)
    receipt=pavilion.render(profile,raw,pavilion._output_path(str(out),profile_id))
    scene=bpy.context.scene
    # The blend retains the entire render scene, including ground, cameras and lights.
    scene.render.filepath="//"+profile_id+".png"
    bpy.ops.wm.save_as_mainfile(filepath=str(out/(profile_id+".blend")))
    # Portable mesh-only model omits the oversized evaluation ground and render rig.
    bpy.ops.object.select_all(action="DESELECT")
    expected=[]
    for obj in scene.objects:
        if obj.type=="MESH" and obj.name!="neutral evaluation ground":
            obj.select_set(True)
            expected.append(obj.name)
    if len(expected)!=receipt["object_count"]-1:
        raise RuntimeError("mesh occurrence mismatch")
    bpy.ops.export_scene.gltf(filepath=str(out/(profile_id+".glb")),export_format="GLB",use_selection=True)
    receipt["gallery"]={"blend_sha256":sha(out/(profile_id+".blend")),"glb_sha256":sha(out/(profile_id+".glb")),"glb_mesh_names":sorted(expected),"exporter_sha256":sha(Path(__file__))}
    (out/(profile_id+".json")).write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
if __name__=="__main__":
    main()
