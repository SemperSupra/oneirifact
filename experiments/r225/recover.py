"""R225 conservative ontology and additional donor recovery over R224.
No synonym is a geometry admission. Exact source identities retained.
"""
import sys,hashlib,json,zipfile,re,csv
from pathlib import Path
from collections import defaultdict,Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r224"))
from worklist import norm,variants
PINS={"worklist":"2af4a629319751eb638904d3e1b232e7354d256109c26544779fd574d8e57d44","male":"18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9","female":"513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542","ct":"6ebcae2937da21450e7f536ceb92d91e96a422862e80320476e7c1d6ef08ee27","ontology":"002450b72156f1bdaf16e12374c3693a55117124a72e7eda90a4e7b045d399fd"}
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def checked(p,k):
    assert sha(p)==PINS[k],k
    return zipfile.ZipFile(p)
def ontology(p):
    assert sha(p)==PINS["ontology"]
    terms={};current=None
    for l in p.read_text(encoding="utf-8").splitlines()+["[End]"]:
        if l.startswith("["):
            if current and current.get("id","").startswith("UBERON:") and not current.get("obsolete") and current.get("name"):
                terms[current["id"]]=current
            current={"synonyms":[],"fma":[]} if l=="[Term]" else None
        elif current is not None:
            if l.startswith("id: "):current["id"]=l[4:]
            elif l.startswith("name: "):current["name"]=l[6:]
            elif l=="is_obsolete: true":current["obsolete"]=True
            elif l.startswith("synonym: "):
                m=re.match(r'synonym: "((?:[^"\\]|\\.)*)" EXACT(?: |$)',l)
                if m:current["synonyms"].append(m.group(1))
            elif l.startswith("xref: FMA:"):
                m=re.match(r"xref: FMA:(\d+)",l)
                if m:current["fma"].append("FMA"+m.group(1))
    byname=defaultdict(set)
    for id,t in terms.items():
        for n in [t["name"],*t["synonyms"]]:byname[norm(n)].add(id)
    return terms,byname
def ct_index(receipt):
    idx=defaultdict(list)
    for r in receipt["inventory"]:
        stem=Path(r["path"]).stem.lower();n=norm(stem)
        # Grouped digit meshes stay compound, not individual phalanges.
        n=n.replace("phalange ","phalanges ")
        m=re.fullmatch(r"(.+?) (\d+) (left|right)",n)
        if m:label=m.group(1)+" "+m.group(3);idx[label].append({"id":r["id"],"source":r["path"],"kind":"NUMBERED_OR_COMPOUND_ELEMENT"})
        idx[n].append({"id":r["id"],"source":r["path"],"kind":"EXACT_SOURCE_FILENAME"})
        if stem=="skull_cranial_maxilla":idx["skull"].append({"id":r["id"],"source":r["path"],"kind":"COMPOUND_CRANIUM"})
        if stem=="skull_mandible":idx["mandible"].append({"id":r["id"],"source":r["path"],"kind":"EXACT_SOURCE_FILENAME"})
        if r.get("atlas_match"):idx[norm(r["atlas_match"])].append({"id":r["id"],"source":r["path"],"kind":"SOURCE_ATLAS_MATCH"})
    return idx
def main(inp,out):
    out.mkdir(parents=True,exist_ok=False)
    terms,byname=ontology(inp/"human-view.obo")
    with checked(inp/"worklist.zip","worklist") as z:work=json.loads(z.read("worklist.json"))["requirements"]
    source={};fmas=defaultdict(set)
    for sex in ("male","female"):
        with checked(inp/(sex+".zip"),sex) as z:
            inv=json.loads(z.read("inventory.json"));d=defaultdict(set)
            for row in inv:
                if sex=="male":
                    for fma,n in row["concepts"]:
                        d[norm(n)].add(row["id"]);fmas[fma].add(row["id"])
                else:d[norm(row["source_node"])].add(row["id"])
            source[sex]=d
    with checked(inp/"ct.zip","ct") as z:ct=ct_index(json.loads(z.read("receipt.json")))
    result=[]
    for w in work:
        sex=w["sex"];name=w["structure"];side=w["laterality"];query=variants(name,side)
        ids=set().union(*(byname.get(q,set()) for q in query))
        # Do not infer side from a generic term. Only exact side-qualified
        # labels enter the synonym/xref expansion; ambiguity stays visible.
        candidates=set();matches=[];concepts=[]
        for id in sorted(ids):
            t=terms[id];concepts.append({"id":id,"label":t["name"],"fma":t["fma"]})
            for alias in [t["name"],*t["synonyms"]]:
                k=norm(alias)
                if side!="unspecified" and not all(s in k.split() for s in side.split()):continue
                for mesh in sorted(source[sex].get(k,set())):candidates.add(mesh);matches.append({"mesh_id":mesh,"term":id,"via":"EXACT_SYNONYM_OR_LABEL","label":alias})
            # Use FMA xrefs only for a uniquely matched ontology term, and
            # retain parent mapping as a proposal, not an isolated organ.
            if sex=="male" and len(ids)==1:
                for fma in t["fma"]:
                    for mesh in sorted(fmas.get(fma,set())):candidates.add(mesh);matches.append({"mesh_id":mesh,"term":id,"via":"FMA_XREF_CANDIDATE","label":fma})
        # Explicit source-inspected bilateral subregions of one midline organ.
        special=[]
        if sex=="female" and name=="pineal gland" and side=="unspecified":
            for n in ("pineal body left","pineal body right"):
                special.extend(sorted(source[sex].get(n,set())))
            assert len(special)==2 and len(set(special))==2
        ctrows=[]
        if sex=="female" and w["system"]=="skeletal":
            ctrows=[x for k in sorted(query) for x in ct.get(k,[])]
            ctrows=list({x["id"]:x for x in ctrows}.values())
        initial=w["status"]
        status=("EXISTING_REVIEW" if initial!="NO_EXACT_NAME_MATCH" else
                "EXPLICIT_SUBREGION_RECOVERY" if special else
                "ONTOLOGY_CANDIDATE_REVIEW" if candidates else
                "SEPARATE_DONOR_CANDIDATE" if ctrows else "UNRESOLVED")
        result.append({**w,"r225_status":status,"ontology_terms":concepts,"ontology_mesh_candidates":sorted(candidates),"ontology_match_evidence":matches,"explicit_subregion_meshes":special,"ct_donor_candidates":ctrows,"geometry_admission":"NOT_QUALIFIED"})
    # Granular typical adult skeleton worklist supplements, not replaces,
    # the gross requirements. Each side/digit/ordinal is independently keyed.
    bones=[]
    def add(family,name,side="midline",ordinal=None,digit=None):
        for sex in ("male","female"):bones.append({"sex":sex,"family":family,"structure":name,"laterality":side,"ordinal":ordinal,"digit":digit,"status":"IDENTITY_AND_GEOMETRY_REVIEW_REQUIRED"})
    for n in ["frontal","occipital","sphenoid","ethmoid","mandible","vomer","hyoid","sternum","sacrum","coccyx"]:add("axial",n)
    for side in ("left","right"):
        for n in ["parietal","temporal","maxilla","zygomatic","nasal","lacrimal","palatine","inferior nasal concha","malleus","incus","stapes"]:add("axial",n,side)
        for i in range(1,13):add("rib","rib",side,i)
        for n in ["clavicle","scapula","humerus","radius","ulna","scaphoid","lunate","triquetrum","pisiform","trapezium","trapezoid","capitate","hamate","hip bone","femur","patella","tibia","fibula","talus","calcaneus","navicular","cuboid","medial cuneiform","intermediate cuneiform","lateral cuneiform"]:add("appendicular",n,side)
        for i in range(1,6):
            add("hand","metacarpal",side,i);add("foot","metatarsal",side,i)
            for region in ("hand","foot"):
                for section in (["proximal","distal"] if i==1 else ["proximal","middle","distal"]):add(region,section+" phalanx",side,digit=i)
    for name,n in [("cervical vertebra",7),("thoracic vertebra",12),("lumbar vertebra",5)]:
        for i in range(1,n+1):add("vertebral",name,ordinal=i)
    assert Counter(b["sex"] for b in bones)=={"male":206,"female":206}
    teeth=[{"sex":s,"FDI":q*10+i,"quadrant":q,"position":i,"status":"IDENTITY_AND_GEOMETRY_REVIEW_REQUIRED"} for s in ("male","female") for q in range(1,5) for i in range(1,9)]
    counts=Counter(x["r225_status"] for x in result)
    summary={"requirements":len(result),"status_counts":dict(counts),"ontology_terms_parsed":len(terms),"ontology_version":"2026-11-05 human-view","granular_bone_requirements":len(bones),"permanent_tooth_requirements":len(teeth),"scope":"Conservative candidate retrieval. Multiple matches, crossrefs, compound geometry and donor registration need individual review; no complete or clinical anatomy claim."}
    (out/"recovery.json").write_text(json.dumps({"summary":summary,"requirements":result,"granular_bones":bones,"permanent_teeth":teeth,"source_pins":PINS},indent=2))
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    (out/"ATTRIBUTION.txt").write_text("Uberon human-view, release 2026-11-05, Uberon community CC BY 3.0 https://creativecommons.org/licenses/by/3.0/ ; https://github.com/obophenotype/uberon/releases/tag/v2026-11-05 ; Mungall et al. Genome Biology 2012 13:R5. Adaptation: exact name/synonym/xref candidate retrieval. Original source identity retained; no ontology release or clinical assertions. BodyParts3D, DBCLS CC BY4.0; HRA/HuBMAP CC BY4.0; BoneHub Visible Human dataset CC BY4.0. See archived donor attribution and R222/R224 receipts.\n")
    print("R225_RECOVERY",json.dumps(summary))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
