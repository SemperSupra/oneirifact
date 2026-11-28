"""Normalize exact R255 producer archives into versioned, hash-pinned display packs.

All original entries survive byte-for-byte. The original catalog is renamed, with
the normalized catalog adding provider provenance and measured-limit references.
Source qualification states are preserved, including failed contact diagnostics.
"""
import argparse,copy,json,subprocess,zipfile
from pathlib import Path
import motion_pack as p
from build_motion_pack import glb,accessor,model_inventory

HERE=Path(__file__).resolve().parent
GROUPS={'support-events':'Falls & support events','acrobatics-combat':'Acrobatics & combat studies','exercise-dance':'Exercise & dance studies'}
TITLES={'observations.json':'Evaluated body observations','kinematic-fit.json':'Every kinematic fitting offset','contact-episodes.json':'Measured contact episodes','media-verification.json':'Rendered media verification','producer-catalog.json':'Original producer catalog','producer-manifest.json':'Original producer file manifest','batch-receipt.json':'Original batch receipt'}

def ref(name,raw,title=None):
    result={'path':name,'bytes':len(raw),'sha256':p.sha(raw)}
    if title:result['title']=title
    return result

def unchanged_qualification(normalized,original):
    before={row['id']:row['qualification'] for row in original['packages']}
    after={row['id']:row['qualification'] for row in normalized['packages']}
    p.require(before==after,'producer qualification states were altered')

def normalize(entry,repository,source,out):
    p.require(source.stat().st_size==entry['archive_bytes'] and p.digest(source)==entry['archive_sha256'],'provider archive bytes/digest')
    with zipfile.ZipFile(source) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        p.require(len(names)==len(set(names)) and len(names)<=p.MAX_FILES and all(p.safe(n) for n in names),'producer paths')
        p.require(all(0<i.file_size<=p.MAX_FILE for i in infos) and sum(i.file_size for i in infos)<=p.MAX_TOTAL,'producer size bounds')
        p.require(z.testzip() is None,'producer ZIP CRC')
        raw={name:z.read(name) for name in names}
    manifest=p.parse(raw['producer-manifest.json']);original=p.parse(raw['catalog.json'])
    p.require(manifest['schema']=='oneirifact.motion-extension-producer-manifest/v1','producer manifest schema')
    p.require(manifest['pack_id']==entry['pack_id']==original['pack_id'] and manifest['head']==entry['producer_head'] and str(manifest['run_id'])==str(entry['producer_run_id']),'producer identity')
    records={r['path']:r for r in manifest['files']}
    p.require(len(records)==len(manifest['files']) and set(records)==set(raw)-{'producer-manifest.json'},'producer file inventory')
    for name,r in records.items():p.require(len(raw[name])==r['bytes'] and p.sha(raw[name])==r['sha256'],'producer inner digest '+name)
    p.require(original['schema']=='oneirifact.motion-browser/v1' and len(original['packages'])==entry['packages'],'producer catalog scope')
    target=out/entry['pack_id'];data=target/'data';data.mkdir(parents=True,exist_ok=False)
    aliases={name:'producer-catalog.json' if name=='catalog.json' else name for name in raw}
    for name,value in raw.items():
        dest=data/aliases[name];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(value)
    catalog=copy.deepcopy(original);used={'catalog.json'};reports=[]
    def check_asset(a):
        name=a['path'];p.require(name in raw and a['sha256']==p.sha(raw[name]) and a['bytes']==len(raw[name]),'producer catalog asset mismatch')
        used.add(name)
    for package in catalog['packages']:
        p.require(package['id'].endswith('-v2') and package['source_kind']=='authored','only corrected authored v2 products')
        p.require(package['qualification']['transport']=='PASS' and package['qualification']['realism']=='HOLD_AUTHORED_KINEMATICS' and package['qualification']['physics']=='NOT_SIMULATED','producer acceptance envelope')
        p.require(package['qualification']['contact'] in ('FAIL_DIAGNOSTIC','HOLD_GEOMETRIC_PROXIMITY_ONLY'),'explicit contact disposition')
        for a in package['assets'].values():check_asset(a)
        receipt=p.parse(raw[package['assets']['receipt']['path']]);p.require(receipt['source_head_commit']==entry['producer_head'] and str(receipt['run_id'])==str(entry['producer_run_id']),'native receipt producer')
        p.require(receipt['transport']=='PASS' and receipt['worst_transport_error_m']<=receipt['transport_tolerance_m']<=5e-5,'native replay transport')
        p.require(all(package['qualification'][k]==receipt[k] for k in package['qualification']),'catalog acceptance differs from original receipt')
        d,b=glb(raw[package['assets']['model']['path']]);inventory=model_inventory(d,b)
        p.require(len(inventory['skins'])==len(package['actors']) and inventory['total_skin_vertices']==13380*len(package['actors']),'actual actor/skin coverage')
        p.require(inventory['maximum_positive_influences']==9 and all(s['joints']==163 and all(q['weight_sets']==3 for q in s['primitives']) for s in inventory['skins']),'complete original source influences')
        animations={a['name']:a for a in d['animations']};p.require(set(animations)=={c['animation_name'] for c in package['clips']},'exact named clips')
        for clip in package['clips']:
            duration=max(v[0] for s in animations[clip['animation_name']]['samplers'] for v in accessor(d,b,s['input']))
            p.require(abs(duration-clip['duration_s'])<1e-5,'native/exported clip duration')
            check_asset(clip['preview']);p.require(raw[clip['preview']['path']][4:8]==b'ftyp','actual preview container')
            clip['poster']=package['assets']['poster']
        package['producer_model_inventory']=package['model_inventory'];package['model_inventory']=inventory
        prov=package['provenance'];p.require(prov['repository']==repository and prov['producer_head']==entry['producer_head'],'catalog provenance')
        prov.update(artifact_id=entry['artifact_id'],provider_artifact=entry['artifact_id'],artifact_bytes=entry['archive_bytes'],artifact_sha256=entry['archive_sha256'],artifact_run_id=entry['producer_run_id'],artifact_producer_head=entry['producer_head'])
        package['group']=GROUPS[package['group']]
        folder=Path(package['assets']['receipt']['path']).parent.as_posix()+'/'
        evidence=[]
        for name in sorted(raw):
            if name.startswith(folder) and name not in used:
                evidence.append(ref(name,raw[name],TITLES.get(Path(name).name,Path(name).name)));used.add(name)
        package['assets']['evidence']=evidence
        package['measured_limits']={'source_receipt':package['assets']['receipt'],'scope':'Recorded kinematic diagnostics, not accepted physical tolerances. Fitting can introduce shifts, sliding or abrupt changes.','metrics':receipt['metrics']}
        reports.append({'id':package['id'],'actors':len(package['actors']),'original_qualification':receipt['contact'],'worst_native_transport_error_m':receipt['worst_transport_error_m'],'model_inventory':inventory})
    catalog['evidence']=[ref(aliases[name],raw[name],TITLES.get(aliases[name],aliases[name])) for name in sorted(raw) if aliases[name] not in used]
    unchanged_qualification(catalog,original)
    (data/'catalog.json').write_text(json.dumps(catalog,indent=2,allow_nan=False)+'\n')
    preserved=[]
    for name,value in raw.items():
        p.require((data/aliases[name]).read_bytes()==value,'original product entry changed');preserved.append({'original_path':name,'pack_path':aliases[name],'bytes':len(value),'sha256':p.sha(value)})
    archive=target/(entry['pack_id']+'.zip');sha,files=p.pack(data,archive);p.verify(archive,sha)
    lock={'pack_id':entry['pack_id'],'repository':repository,'tag':entry['pack_id'],'asset':archive.name,'sha256':sha,'files':len(files),'unpacked_bytes':sum(r['bytes'] for r in files.values()),'packages':len(catalog['packages']),'previews':sum(bool(c['preview']) for a in catalog['packages'] for c in a['clips'])}
    false=copy.deepcopy(catalog);false['packages'][0]['qualification']['contact']='PASS'
    try:unchanged_qualification(false,original)
    except ValueError:contact_control=True
    else:contact_control=False
    false=copy.deepcopy(catalog);false['packages'][0]['qualification']['realism']='PASS'
    try:p.catalog_check(false,files)
    except ValueError:realism_control=True
    else:realism_control=False
    p.require(contact_control and realism_control,'false acceptance controls')
    report={'schema':'oneirifact.motion-extension-display-intake/v1','status':'PASS_SOURCE_AND_DISPOSITION_PRESERVED','release_lock':lock,'input':entry,'preserved_original_entries':preserved,'original_entry_count':len(preserved),'renamed_entry':{'catalog.json':'producer-catalog.json'},'packages':reports,'controls':{'contact_false_pass_rejected':contact_control,'realism_false_pass_rejected':realism_control},'hosting_scope':'Versioned release and SHA-256 lock; platform-enforced release immutability is not assumed.'}
    (target/'intake-receipt.json').write_text(json.dumps(report,indent=2)+'\n');(target/'release-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print('MOTION_EXTENSION_INTAKE_PASS',json.dumps(lock),flush=True);return lock

def build(inputs,archives,out,only=None):
    spec=p.parse(inputs.read_bytes());p.require(spec['schema']=='oneirifact.motion-extension-inputs/v1' and spec['repository']=='SemperSupra/oneirifact','input schema/origin')
    archives.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=False);locks=[]
    for entry in spec['inputs']:
        if only and entry['pack_id']!=only:continue
        source=archives/entry['archive']
        if not source.exists():
            with source.open('wb') as f:subprocess.run(['gh','api','repos/'+spec['repository']+'/actions/artifacts/'+str(entry['artifact_id'])+'/zip'],stdout=f,check=True,timeout=120)
        locks.append(normalize(entry,spec['repository'],source,out))
    p.require(locks,'requested pack absent');(out/'extension-release-lock.json').write_text(json.dumps({'schema':'oneirifact.motion-browser-releases/v1','packs':locks},indent=2)+'\n')
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--inputs',type=Path,default=HERE/'motion-extension-inputs.json');a.add_argument('--archives',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--only');q=a.parse_args();build(q.inputs,q.archives,q.out,q.only)
