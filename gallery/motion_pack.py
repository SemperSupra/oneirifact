"""Deterministic public motion pack, with exact safe restore and per-file hashes."""
import hashlib,json,re,stat,zipfile
from pathlib import Path

SCHEMA="oneirifact.motion-browser-pack/v1"
MAX_TOTAL=256<<20;MAX_FILE=32<<20;MAX_FILES=512
MANIFEST="pack-manifest.json"
SEGMENT=re.compile(r"[a-z0-9][a-z0-9._-]*\Z")
HEX=re.compile(r"[0-9a-f]{64}\Z")
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def parse(raw):
    def unique(items):
        d={}
        for k,v in items:require(k not in d,'duplicate JSON key');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def safe(name):return isinstance(name,str) and len(name)<240 and all(SEGMENT.fullmatch(p) for p in name.split('/'))
def asset(path):return {'path':path.name,'bytes':path.stat().st_size,'sha256':digest(path)}
def catalog_check(c,entries):
    require(c['schema']=='oneirifact.motion-browser/v1' and SEGMENT.fullmatch(c['pack_id']),'catalog schema/id')
    seen=set();refs={'catalog.json'}
    def link(a):
        require(type(a)==dict and safe(a['path']) and a['path'] in entries,'missing/unsafe catalog asset')
        r=entries[a['path']];require(a['sha256']==r['sha256'] and a['bytes']==r['bytes'],'catalog asset digest/size')
        refs.add(a['path'])
    for p in c['packages']:
        require(SEGMENT.fullmatch(p['id']) and p['id'] not in seen,'duplicate/invalid package');seen.add(p['id'])
        require(p['source_kind'] in ('authored','captured') and p['actors'] and p['clips'],'package scope')
        require(p['qualification']['realism'] in ('HELD','HOLD_AUTHORED_KINEMATICS'),'realism must remain held for these research releases')
        for key in ('model','native_scene','poster','contact_sheet','receipt','rights'):link(p['assets'][key])
        for still in p['assets'].get('stills',[]):link(still)
        for evidence in p['assets'].get('evidence',[]):link(evidence)
        clip_ids=set()
        for clip in p['clips']:
            require(clip['id'] not in clip_ids and clip['duration_s']>0 and clip['animation_name'],'invalid/duplicate clip');clip_ids.add(clip['id'])
            if clip.get('preview'):link(clip['preview'])
            if clip.get('poster'):link(clip['poster'])
    for evidence in c.get('evidence',[]):link(evidence)
    require(refs==set(entries),'unreferenced pack entries')
    return len(seen)
def manifest(entries):return json.dumps({'schema':SCHEMA,'files':[{'path':n,**entries[n]} for n in sorted(entries)]},sort_keys=True,separators=(',',':')).encode()+b'\n'
def inventory(folder):
    entries={};total=0
    for p in sorted(folder.rglob('*')):
        require(not p.is_symlink(),'symlink in pack')
        if p.is_dir():continue
        n=p.relative_to(folder).as_posix();size=p.stat().st_size;total+=size
        require(safe(n) and n!=MANIFEST and p.is_file(),'unsafe pack file')
        require(0<size<=MAX_FILE and total<=MAX_TOTAL and len(entries)<MAX_FILES,'pack budget')
        entries[n]={'bytes':size,'sha256':digest(p)}
    catalog_check(parse((folder/'catalog.json').read_bytes()),entries)
    return entries
def pack(folder,dest):
    entries=inventory(folder)
    with zipfile.ZipFile(dest,'x') as z:
        for n,b in [(n,(folder/n).read_bytes()) for n in sorted(entries)]+[(MANIFEST,manifest(entries))]:
            i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.create_system=3;i.external_attr=(stat.S_IFREG|0o644)<<16;i.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(i,b,compresslevel=6)
    return digest(dest),entries
def verify(path,expected):
    require(HEX.fullmatch(expected) and digest(path)==expected,'pack archive digest')
    with zipfile.ZipFile(path) as z:
        info=z.infolist();names=[i.filename for i in info]
        require(len(names)==len(set(names)) and len(names)<=MAX_FILES+1 and MANIFEST in names,'pack entries')
        require(all(safe(i.filename) and stat.S_ISREG(i.external_attr>>16) and 0<i.file_size<=MAX_FILE for i in info),'pack file')
        require(sum(i.file_size for i in info)<=MAX_TOTAL+(1<<20),'unpacked budget')
        raw=z.read(MANIFEST);d=parse(raw);require(d['schema']==SCHEMA,'manifest schema')
        entries={r['path']:{'bytes':r['bytes'],'sha256':r['sha256']} for r in d['files']}
        require(raw==manifest(entries) and set(entries)==set(names)-{MANIFEST},'canonical manifest')
        for n,r in entries.items():
            b=z.read(n);require(len(b)==r['bytes'] and sha(b)==r['sha256'],'inner asset '+n)
        catalog_check(parse(z.read('catalog.json')),entries)
    return entries
def restore(path,expected,dest):
    entries=verify(path,expected);require(not dest.exists(),'restore destination exists');dest.mkdir(parents=True)
    with zipfile.ZipFile(path) as z:
        for n in entries:
            p=dest/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
    require(inventory(dest)==entries,'restored inventory differs')
    return entries
