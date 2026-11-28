"""R226: explicit single-element candidates; no geometry admission or grafting."""
import collections as c
import hashlib,json,re,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r224"))
from worklist import norm
PINS={"recovery":"10eef29eee45c11da7bdb0e91638be28755473f8bfaf5c2eb157474268ec7140","male":"18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9","female":"513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542","ct":"6ebcae2937da21450e7f536ceb92d91e96a422862e80320476e7c1d6ef08ee27"}
def read(p,k,name):
    with p.open("rb") as f:
        assert hashlib.file_digest(f,"sha256").hexdigest()==PINS[k],k
    with zipfile.ZipFile(p) as z:return json.loads(z.read(name))
def sided(names,side):
    if side=="midline":return set(names)
    return {norm(v) for n in names for v in (side+" "+n,n+" "+side,n+" of "+side,n+" of "+side+" side")}
def bone_alias(b):
    name=b["structure"]; side=b["laterality"]; ordinal=b["ordinal"]; digit=b["digit"]; family=b["family"]
    if digit is not None:
        # Require named hand/foot and exact digit; never treat grouped phalanges as single bones.
        part=name+" "+str(digit)
        names=[family+" "+part,part+" of "+family,name+" of digit "+str(digit)+" of "+family,
               name+" of "+family+" digit "+str(digit)]
    elif ordinal is not None:
        n=str(ordinal)
        names=[name+" "+n,n+" "+name]
        if family=="vertebral":
            v={"cervical":"c","thoracic":"t","lumbar":"l"}[name.split()[0]]
            names += [v+n,"vertebra "+v+n,"vertebra "+v+" "+n,v+" "+n]
        if family=="rib":names += ["rib "+n.zfill(2),n+"th rib"] if ordinal>=4 else ["rib "+n.zfill(2),["first","second","third"][ordinal-1]+" rib"]
    else:
        names=[name,name+" bone"]
        if name=="hip bone":names+=["os coxae","innominate bone","coxal bone"]
    return sided([norm(n) for n in names],side)
def tooth_alias(t):
    # Only explicit FDI marking; bare number or generic 'tooth' is insufficient.
    n=str(t["FDI"])
    return {norm(x) for x in ("FDI "+n,"tooth FDI "+n,"FDI tooth "+n,"tooth "+n+" FDI")}
def key(r):
    if "FDI" in r:return r["sex"]+":FDI:"+str(r["FDI"])
    return ":".join(str(r[x]) for x in ("sex","family","structure","laterality","ordinal","digit"))
def source_rows(m,f,ct):
    for sex,rows in (("male",m),("female",f)):
        for r in rows:
            labels=[{"label":n,"concept":a} for a,n in r["concepts"]] if sex=="male" else [{"label":r["source_node"],"concept":None}]
            yield {"sex":sex,"corpus":"BodyParts3D" if sex=="male" else "HRA","id":r["id"],"labels":labels}
    for r in ct:
        stem=Path(r["path"]).stem
        # Filename side is explicit; the only additional aliases are the prior atlas match.
        labels=[{"label":stem,"concept":None}]
        if r.get("atlas_match"):labels.append({"label":r["atlas_match"],"concept":None})
        # Explicitly mark compound names; no segmentation or single-element interpretation.
        n=norm(stem)
        compound=bool(re.search(r"\b(phalanges|skull|cranium|maxilla)\b",n)) and n not in ("mandible","skull mandible")
        if n=="skull mandible":labels.append({"label":"mandible","concept":None})
        yield {"sex":"female","corpus":"CT","id":r["id"],"path":r["path"],"labels":labels,"compound_hold":compound}
def selftest():
    b={"structure":"rib","laterality":"left","ordinal":2,"digit":None,"family":"rib"}
    q=bone_alias(b)
    assert norm("rib_02_left") in q and norm("rib_2_right") not in q and norm("rib_12_left") not in q
    b.update(structure="proximal phalanx",family="hand",digit=2,ordinal=None)
    q=bone_alias(b)
    assert norm("hand proximal phalanx 2 left") in q and norm("phalanges left") not in q and norm("foot proximal phalanx 2 left") not in q
    assert norm("tooth 11") not in tooth_alias({"FDI":11}) and norm("tooth FDI 11") in tooth_alias({"FDI":11})
def main(inp,out):
    selftest();out.mkdir(parents=True,exist_ok=False)
    rr=read(inp/"recovery.zip","recovery","recovery.json")
    m=read(inp/"male.zip","male","inventory.json")
    f=read(inp/"female.zip","female","inventory.json")
    ct=read(inp/"ct.zip","ct","receipt.json")["inventory"]
    assert len(ct)==143
    records=rr["granular_bones"]+rr["permanent_teeth"]
    assert len(records)==476 and len({key(r) for r in records})==476
    idx=c.defaultdict(list);all_sources={};used=c.defaultdict(set)
    for src in source_rows(m,f,ct):
        sid=(src["corpus"],src["id"]);assert sid not in all_sources
        all_sources[sid]=src
        for label in src["labels"]:
            idx[src["sex"],norm(label["label"])].append((sid,label))
    rows=[]
    for r in records:
        aliases=tooth_alias(r) if "FDI" in r else bone_alias(r)
        hits={}
        for alias in sorted(aliases):
            for sid,label in idx[r["sex"],alias]:
                src=all_sources[sid]
                hit=hits.setdefault(sid,{"source":src,"matched_labels":[]})
                if label not in hit["matched_labels"]:hit["matched_labels"].append(label)
                used[sid].add(key(r))
        rows.append({"requirement":r,"key":key(r),"exact_aliases":sorted(aliases),"candidates":list(hits.values()),"geometry_admission":"NOT_QUALIFIED"})
    for r in rows:
        hits=r["candidates"]
        if not hits:r["status"]="UNRESOLVED_EXACT_LABEL"
        elif any(h["source"].get("compound_hold") or len(used[h["source"]["corpus"],h["source"]["id"]])>1 for h in hits):
            r["status"]="HOLD_COMPOUND_OR_SHARED_ID"
        elif len(hits)>1:r["status"]="MULTIPLE_DONOR_CANDIDATES"
        else:r["status"]="SINGLE_LABEL_CANDIDATE_REVIEW"
    unmapped_ct=[src for sid,src in all_sources.items() if sid[0]=="CT" and sid not in used]
    summary={"requirements":len(rows),"by_sex":{s:dict(c.Counter(r["status"] for r in rows if r["requirement"]["sex"]==s)) for s in ("male","female")},"ct_total":len(ct),"ct_mapped_any":len(ct)-len(unmapped_ct),"ct_unmapped":len(unmapped_ct),"scope":"Conservative labels only. No proof of presence/absence, individual mesh separation, anatomical geometry, tooth equivalence or registration."}
    (out/"identity.json").write_text(json.dumps({"summary":summary,"source_pins":PINS,"records":rows,"unmapped_ct":unmapped_ct},indent=2))
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    print("R226_IDENTITY",json.dumps(summary))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
