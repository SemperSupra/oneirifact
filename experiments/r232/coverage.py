"""Audit actual admitted atlas meshes, not completeness inferred from an image.
Explicit source-name and hierarchy evidence; absence of a label is not anatomical absence.
No new geometry, grafting, or clinical admission.
"""
import hashlib,io,json,re,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
PINS={"male":"18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9","female":"513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"}
TERMS={
"mammary_gland":r"\bmammary gland\b|\bbreast\b",
"mammary_duct":r"lactiferous|mammary duct|milk duct",
"mammary_lobule":r"lobule|mammary lobe",
"nipple":r"\bnipple\b",
"areola":r"\bareola\b",
"breast_fat":r"mammary fat|breast fat|mammary adipose",
"suspensory_breast_ligament":r"cooper.*ligament|suspensory ligament of (the )?breast",
"vulva":r"\bvulva\b|female external genital",
"mons_pubis":r"mons pubis|mons veneris",
"labia_majora":r"labium majus|labia majora|greater labium",
"labia_minora":r"labium minus|labia minora|lesser labium",
"clitoris":r"\bclitoris\b|\bclitoral\b",
"vestibular_bulb":r"vestibular bulb|bulb of vestibule",
"vestibular_gland":r"vestibular gland|bartholin",
"vaginal_opening":r"vaginal (opening|orifice|ostium)|introitus",
"urethral_opening":r"urethral (opening|orifice|meatus)|external urethral",
"vagina":r"\bvagina\b|\bvaginal\b",
"urethra":r"\burethra\b",
"uterus":r"\buterus\b|uterine",
"ovary":r"\bovary\b|ovarian",
"penis":r"\bpenis\b|penile",
"scrotum":r"\bscrotum\b|scrotal"
}
def norm(s):
    return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()
def digest(b):return hashlib.sha256(b).hexdigest()
def checked(path,sex):
    with path.open("rb") as f:
        assert hashlib.file_digest(f,"sha256").hexdigest()==PINS[sex]
    return zipfile.ZipFile(path)
def names(r,sex):
    return [x[1] for x in r["concepts"]] if sex=="male" else [r["source_node"]]
def hits(r,sex,pattern):
    return any(re.search(pattern,norm(x)) for x in names(r,sex))
def main(inp,out):
    out.mkdir(parents=True,exist_ok=False)
    all_rows={};full_inventory={}
    for sex in ("male","female"):
        with checked(inp/(sex+".zip"),sex) as z:
            rec=json.loads(z.read("receipt.json"))
            raw=z.read("inventory.json")
            assert digest(raw)==rec["files"]["inventory.json"]["sha256"]
            inv=json.loads(raw);full_inventory[sex]=inv
            rows=[]
            for term,pattern in TERMS.items():
                direct=[r for r in inv if hits(r,sex,pattern)]
                inherited=[r for r in inv if sex=="female" and r not in direct and any(re.search(pattern,norm(x)) for x in r.get("hierarchy",[]))]
                rows.append({"feature":term,"direct_named_mesh_candidates":[{"id":r["id"],"names":names(r,sex),"layer":r["category"],"triangles":r["triangles"]} for r in direct],"hierarchy_only_candidates":[{"id":r["id"],"names":names(r,sex),"layer":r["category"],"triangles":r["triangles"]} for r in inherited],"status":"LABEL_EVIDENCE_ONLY" if direct or inherited else "NO_NAMED_CANDIDATE_IN_INVENTORY"})
            all_rows[sex]=rows
    # Recover explicitly named breast structures + descendants of named breast
    # parents from the actual source, preserving the named model's exact frame.
    female=full_inventory["female"];selected={}
    breast=r"\bmammary\b|\bbreast\b|\bnipple\b|\bareola\b|lactiferous"
    with checked(inp/"female.zip","female") as z:
        rec=json.loads(z.read("receipt.json"))
        for layer in sorted({r["category"] for r in female}):
            rows=[r for r in female if r["category"]==layer and (hits(r,"female",breast) or any(re.search(breast,norm(n)) for n in r.get("hierarchy",[])))]
            if not rows:continue
            path="layers/"+layer+".glb";raw=z.read(path);assert digest(raw)==rec["files"][path]["sha256"]
            s=trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
            for r in rows:
                tf,g=s.graph[r["id"]];m=s.geometry[g].copy();m.apply_transform(tf)
                assert len(m.faces)==r["triangles"] and np.isfinite(m.vertices).all()
                selected[r["id"]]=(r,m)
        assert selected,"no mammary geometry recovered"
        scene=trimesh.Scene()
        for n,(r,m) in sorted(selected.items()):scene.add_geometry(m,node_name=n,geom_name=n)
        raw=scene.export(file_type="glb");(out/"female-mammary-reference.glb").write_bytes(raw)
        q=trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
        assert set(q.graph.nodes_geometry)==set(selected)
        err=0.
        for n,(r,m) in selected.items():
            tf,g=q.graph[n];v=q.geometry[g].copy();v.apply_transform(tf)
            assert v.faces.shape==m.faces.shape
            err=max(err,float(np.max(np.abs(v.vertices[v.faces]-m.vertices[m.faces]))))
        assert err<=2e-6
        (out/"ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt")+b"\nR232: exact named mammary subset from HRA female reference. No added tissue or anatomical admission. Standalone mammary reference models are sculpted anatomical references, not subject-specific breast scans.\n")
    report={"schema":"oneirifact.sex-specific-coverage-audit/v1","source_pins":PINS,"inventory_counts":{s:len(v) for s,v in full_inventory.items()},"features":all_rows,"mammary_subset":{"nodes":len(selected),"triangles":sum(len(m.faces) for _,m in selected.values()),"sha256":digest(raw),"transport_max_m":err,"source_ids":[{"id":n,"name":r["source_node"],"category":r["category"],"triangles":r["triangles"]} for n,(r,_) in sorted(selected.items())]},"scope":"Name/hierarchy audit and exact donor subset; no inference from missing labels, no female external anatomy synthesis, no anatomical or native qualification."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2))
    print("R232_COVERAGE",json.dumps({"counts":report["inventory_counts"],"features":{s:[(r["feature"],len(r["direct_named_mesh_candidates"]),len(r["hierarchy_only_candidates"])) for r in rows] for s,rows in all_rows.items()},"mammary":report["mammary_subset"]}),flush=True)
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
