"""R229 source-preserving decomposition of female CT grouped digit meshes.

Connectivity is a geometric observation, not a bone name or anatomy admission.
No reconstruction from missing geometry, no donor fusion, no clinical claim.
"""
import hashlib,io,json,re,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from PIL import Image,ImageDraw,ImageFont

CT_SHA="6ebcae2937da21450e7f536ceb92d91e96a422862e80320476e7c1d6ef08ee27"
ID_SHA="320928150b0c0590713287d3841dae897651f07f9d1de303b61885e9839d89eb"
PATTERN=re.compile(r"PHALANGE_(HAND|FOOT)_([1-5])_(LEFT|RIGHT)\.stl")
PREFIX="visible_human_3d_models/CT/Mesh/02_Female/"
def sha(b):return hashlib.sha256(b).hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)
def checked(p,h):
    with p.open("rb") as f:require(hashlib.file_digest(f,"sha256").hexdigest()==h,"source digest")
    return zipfile.ZipFile(p)
def load(raw):return trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
def world(s,n):
    t,g=s.graph[n];q=s.geometry[g].copy();q.apply_transform(t)
    require(len(q.faces)>0 and np.isfinite(q.vertices).all(),"invalid mesh")
    return q
def partition(f,by_vertex=False):
    # Connect all triangles sharing a complete edge (or, for the independent
    # vertex-contact diagnostic, a vertex). Includes non-manifold incidence.
    n=len(f)
    if by_vertex:
        key=f.reshape(-1,1)
    else:
        key=np.sort(f[:,[0,1,1,2,2,0]].reshape(-1,2),axis=1)
    ids=np.repeat(np.arange(n),3)
    order=np.lexsort(tuple(key[:,i] for i in reversed(range(key.shape[1]))))
    k=key[order];v=ids[order]
    same=np.all(k[1:]==k[:-1],axis=1)
    a,b=v[:-1][same],v[1:][same]
    graph=coo_matrix((np.ones(len(a),dtype=np.uint8),(a,b)),shape=(n,n)).tocsr()
    count,labels=connected_components(graph,directed=False,return_labels=True)
    return count,labels
def inspect(m):
    original=m.vertices[m.faces]
    welded=trimesh.Trimesh(vertices=m.vertices.copy(),faces=m.faces.copy(),process=False)
    welded.merge_vertices(digits_vertex=9)
    require(len(welded.faces)==len(m.faces),"welding altered triangle count")
    drift=float(np.max(np.abs(welded.vertices[welded.faces]-original)))
    require(drift<=2e-6,"welding changed coordinates")
    ec,el=partition(welded.faces);vc,vl=partition(welded.faces,True)
    require(ec>=vc and len(el)==len(original),"partition inconsistency")
    # Stable ordering by first source face, not size or inferred anatomy.
    groups=[np.flatnonzero(el==i) for i in range(ec)]
    groups.sort(key=lambda g:int(g[0]))
    require(np.array_equal(np.sort(np.concatenate(groups)),np.arange(len(m.faces))),"lost or duplicated faces")
    return groups,vc,drift
def subset(m,indices):
    f=m.faces[indices];used,new=np.unique(f.reshape(-1),return_inverse=True)
    q=trimesh.Trimesh(vertices=m.vertices[used],faces=new.reshape(-1,3),process=False)
    require(np.array_equal(q.vertices[q.faces],m.vertices[m.faces[indices]]),"source triangle order changed")
    return q
def selftest():
    x=trimesh.creation.icosphere(subdivisions=1,radius=.01)
    y=x.copy();y.apply_translation([.1,0,0])
    q=trimesh.util.concatenate([x,y])
    groups,v,d=inspect(q)
    require(len(groups)==v==2 and d<=2e-6,"disconnected fixture")
    # Two triangles meet at one vertex: edge and vertex diagnostics disagree.
    f=np.array([[0,1,2],[0,3,4]])
    require(partition(f)[0]==2 and partition(f,True)[0]==1,"contact fixture")
def color(k):
    palette=[[.79,.65,.43,1],[.35,.66,.8,1],[.75,.42,.59,1],[.52,.73,.49,1]]
    return trimesh.visual.material.PBRMaterial(name="component_"+str(k),baseColorFactor=palette[k%len(palette)],metallicFactor=0,roughnessFactor=.9)
def preview(out,rows,meshes):
    im=Image.new("RGB",(1280,1030),"#17232f");d=ImageDraw.Draw(im)
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",18)
    small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",14)
    d.text((15,14),"Female CT grouped digit meshes — actual source triangle components",font=font,fill="white")
    d.text((15,42),"Individual colors mark edge components, not proximal/middle/distal identity. Each panel fit independently.",font=small,fill="#b9c8d0")
    for i,(r,parts) in enumerate(zip(rows,meshes)):
        x=(i%5)*256;y=78+(i//5)*234
        d.text((x+9,y),r["region"]+" "+r["side"]+" "+str(r["digit"]),font=font,fill="white")
        d.text((x+9,y+27),str(r["edge_components"])+" components / "+str(r["typical_count"])+" typical",font=small,fill="#b9c8d0")
        v=np.concatenate([q.vertices for q in parts]);lo=v.min(0);hi=v.max(0);axes=np.argsort(hi-lo)[-2:]
        a,b=axes;center=(lo+hi)/2;scale= min(224/max(hi[a]-lo[a],1e-9),163/max(hi[b]-lo[b],1e-9))
        for k,q in enumerate(parts):
            verts=q.vertices[::max(1,len(q.vertices)//6500)]
            rgb=tuple(int(c*255) for c in color(k).baseColorFactor[:3]) if False else ["#d4b27c","#75b1cd","#c982a3","#9bb888"][k%4]
            d.point([(x+128+(p[a]-center[a])*scale,y+141-(p[b]-center[b])*scale) for p in verts],fill=rgb)
    im.save(out/"digit-components.png")
def main(ct,identity,out):
    selftest();out.mkdir(parents=True,exist_ok=False)
    with checked(ct,CT_SHA) as z,checked(identity,ID_SHA) as iz:
        cr=json.loads(z.read("receipt.json"));ir=json.loads(iz.read("identity.json"))
        require(len(cr["inventory"])==143 and len(ir["unmapped_ct"])==24,"source inventory")
        src=load(z.read("ct-skeleton-original-frame.glb"))
        idx={r["id"]:r for r in cr["inventory"]}
        scene=trimesh.Scene();records=[];views=[];transport={};other=[]
        for row in ir["unmapped_ct"]:
            rec=idx[row["id"]];require(rec["path"]==row["path"],"source identity")
            m=world(src,row["id"]);require(len(m.faces)==rec["triangles"],"source triangle count")
            name=Path(row["path"]).name;match=PATTERN.fullmatch(name)
            if not match:
                status="HOLD_COMPOUND_SKULL" if "SKULL" in name else "VARIANT_L6_PRESERVED" if "L6" in name else "HIP_BONE_LABEL_CANDIDATE_REVIEW"
                other.append({"id":row["id"],"source_path":row["path"],"triangles":len(m.faces),"bounds_m":m.bounds.tolist(),"status":status,"geometry_admission":"NOT_QUALIFIED"})
                continue
            region,digit,side=match.groups();digit=int(digit);typical=2 if digit==1 else 3
            groups,vcount,drift=inspect(m)
            details=[];parts=[]
            if len(groups)>256:
                # Do not discard any fragments. Preserve full source as one node.
                label=row["id"]+"__unsplit_hold";parts=[m]
                scene.add_geometry(m,node_name=label,geom_name=label);transport[label]=m
                status="HOLD_EXCESS_COMPONENTS_UNSPLIT"
            else:
                for i,g in enumerate(groups):
                    q=subset(m,g);q.visual=trimesh.visual.TextureVisuals(material=color(i))
                    label=row["id"]+"__component_"+str(i).zfill(3)
                    scene.add_geometry(q,node_name=label,geom_name=label);transport[label]=q;parts.append(q)
                    details.append({"id":label,"first_source_face":int(g[0]),"triangles":len(g),"bounds_m":q.bounds.tolist(),"watertight":bool(q.is_watertight),"anatomical_identity":"UNASSIGNED"})
                status=("COMPONENT_COUNT_MATCH_TYPICAL_ONLY" if len(groups)==typical and vcount==typical else "HOLD_COMPONENT_COUNT_OR_POINT_CONTACT")
            records.append({"source_id":row["id"],"source_path":row["path"],"source_stl_sha256":rec["sha256"],"region":region,"side":side,"digit":digit,"source_triangles":len(m.faces),"edge_components":len(groups),"vertex_components":vcount,"typical_count":typical,"weld_coordinate_max_m":drift,"components":details,"status":status,"geometry_admission":"NOT_QUALIFIED"})
            views.append(parts)
        require(len(records)==20 and len(other)==4,"missing group")
        raw=scene.export(file_type="glb");(out/"ct-digit-components.glb").write_bytes(raw)
        reloaded=load(raw);require(set(reloaded.graph.nodes_geometry)==set(transport),"GLB node identity")
        drift=0.
        for n,m in transport.items():
            q=world(reloaded,n);require(q.faces.shape==m.faces.shape,"GLB face count")
            drift=max(drift,float(np.max(np.abs(m.vertices[m.faces]-q.vertices[q.faces]))))
        require(drift<=2e-6,"GLB triangle drift")
        require(sum(r["source_triangles"] for r in records)==sum(len(m.faces) for m in transport.values()),"triangle conservation")
        preview(out,records,views)
        (out/"ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt")+b"\nR229 edge-connected triangle partitions, original metric frame, presentation colors only. No individual bone identity or anatomical placement admission.\n")
        summary={"source_archive_sha256":CT_SHA,"identity_archive_sha256":ID_SHA,"groups":len(records),"count_match_groups":sum(r["status"]=="COMPONENT_COUNT_MATCH_TYPICAL_ONLY" for r in records),"expected_typical_components":sum(r["typical_count"] for r in records),"observed_edge_components":sum(r["edge_components"] for r in records),"observed_vertex_components":sum(r["vertex_components"] for r in records),"export_nodes":len(transport),"source_triangles":sum(r["source_triangles"] for r in records),"transport_max_m":drift,"subset_sha256":sha(raw),"status":"SEPARATE_TOPOLOGY_CANDIDATE_NO_ANATOMY_ADMISSION"}
        (out/"receipt.json").write_text(json.dumps({"summary":summary,"groups":records,"other_unmapped":other},indent=2))
        print("R229_DIGIT_COMPONENTS",json.dumps(summary),flush=True)
        for r in records:print(r["source_id"],r["edge_components"],r["vertex_components"],r["typical_count"],r["status"],flush=True)
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
