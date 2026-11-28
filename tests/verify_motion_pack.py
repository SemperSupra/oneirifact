"""Qualify exact motion delivery and exercise bounded custody/truncation negatives."""
import copy,json,stat,sys,tempfile,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gallery'))
import motion_pack as pack
import build_motion_pack as builder

def rejected(fn):
    try:fn()
    except (ValueError,KeyError,zipfile.BadZipFile):return True
    return False

def verify(source,output):
    lock=pack.parse((builder.HERE/'motion-release-lock.json').read_bytes())['packs'][0]
    entries=pack.verify(source,lock['sha256']);models=[];previews=0;controls={}
    with zipfile.ZipFile(source) as z:
        c=pack.parse(z.read('catalog.json'))
        pack.require(c['pack_id']==lock['pack_id'] and len(c['packages'])==17,'locked package coverage')
        for p in c['packages']:
            d,b=builder.glb(z.read(p['assets']['model']['path']));inv=builder.model_inventory(d,b)
            pack.require(inv==p['model_inventory'],'catalog model inventory mismatch')
            pack.require(inv['maximum_positive_influences']==9,'original ninth influence missing')
            pack.require(all(s['joints']==163 and all(q['weight_sets']==3 for q in s['primitives']) for s in inv['skins']),'full source rig/influence-set coverage')
            animations={a['name']:a for a in d['animations']}
            pack.require(set(animations)=={a['animation_name'] for a in p['clips']},'exact named animation coverage')
            for clip in p['clips']:
                a=animations[clip['animation_name']]
                duration=max(v[0] for sampler in a['samplers'] for v in builder.accessor(d,b,sampler['input']))
                pack.require(duration==clip['duration_s'],'animation duration differs')
                if clip['preview']:
                    previews+=1;raw=z.read(clip['preview']['path'])
                    pack.require(raw[4:8]==b'ftyp' and clip['preview']['fps']>0 and clip['preview']['frames']>0,'actual MP4 container metadata')
            rights=z.read(p['assets']['rights']['path']).decode()
            pack.require('CC0' in rights and (p['source_kind']!='captured' or 'Carnegie' in rights),'source rights coverage')
            models.append({'id':p['id'],'animations':len(animations),'skin_vertices':inv['total_skin_vertices'],'maximum_positive_influences':inv['maximum_positive_influences'],'complete_weight_sets':3})
        pack.require(previews==32 and previews==lock['previews'],'all produced preview coverage')
        pack.require(len(entries)==lock['files'] and sum(r['bytes'] for r in entries.values())==lock['unpacked_bytes'],'locked delivery bounds')
        pack.require('oneirifact-private' not in json.dumps(c).lower() and 'library_file_id' not in json.dumps(c),'public-only catalog')
        # A source model with a missing set or a ninth-weight truncation must fail.
        sample=next(p for p in c['packages'] if p['source_kind']=='authored')
        d,b=builder.glb(z.read(sample['assets']['model']['path']))
        bad=copy.deepcopy(d)
        for m in bad['meshes']:
            for primitive in m['primitives']:
                if 'WEIGHTS_1' in primitive['attributes']:del primitive['attributes']['WEIGHTS_1']
        controls['missing_middle_weight_set_rejected']=rejected(lambda:builder.model_inventory(bad,b))
        bad=copy.deepcopy(d)
        for m in bad['meshes']:
            for primitive in m['primitives']:
                primitive['attributes'].pop('WEIGHTS_2',None);primitive['attributes'].pop('JOINTS_2',None)
        controls['eight_influence_truncation_rejected']=rejected(lambda:builder.model_inventory(bad,b))
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);data=root/'data';data.mkdir();raw=b'original test payload'
        (data/'asset.bin').write_bytes(raw);ref={'path':'asset.bin','bytes':len(raw),'sha256':pack.sha(raw)}
        catalog={'schema':'oneirifact.motion-browser/v1','pack_id':'fixture','packages':[{'id':'fixture','source_kind':'authored','actors':[{}],'qualification':{'realism':'HELD'},'assets':{k:ref for k in ('model','native_scene','poster','contact_sheet','receipt','rights')},'clips':[{'id':'clip','animation_name':'clip','duration_s':1}]}]}
        (data/'catalog.json').write_text(json.dumps(catalog));positive=root/'positive.zip';sha,_=pack.pack(data,positive)
        pack.restore(positive,sha,root/'restored');controls['positive_exact_restore']=pack.inventory(data)==pack.inventory(root/'restored')
        controls['wrong_archive_digest_rejected']=rejected(lambda:pack.verify(positive,'0'*64))
        for label,payload in [('changed_inner_payload',b'corrupted test payload'),('path_escape',b'escape')]:
            target=root/(label+'.zip')
            with zipfile.ZipFile(positive) as zin,zipfile.ZipFile(target,'w') as zout:
                for info in zin.infolist():zout.writestr(info,payload if label=='changed_inner_payload' and info.filename=='asset.bin' else zin.read(info.filename))
                if label=='path_escape':
                    i=zipfile.ZipInfo('../escape.bin');i.external_attr=(stat.S_IFREG|0o644)<<16;zout.writestr(i,payload)
            controls[label+'_rejected']=rejected(lambda:pack.verify(target,pack.digest(target)))
    pack.require(all(controls.values()),'controlled corruption escaped: '+str(controls))
    result={'schema':'oneirifact.motion-browser-pack-verification/v1','status':'PASS','archive_sha256':lock['sha256'],'packages':models,'preview_count':previews,'files':len(entries),'unpacked_bytes':sum(r['bytes'] for r in entries.values()),'controls':controls,'limits':['MP4 decode and browser GPU animation are separate site qualification gates.','Transport does not qualify realistic motion, contact, dynamics or internal anatomy.']}
    output.write_text(json.dumps(result,indent=2)+'\n');print('MOTION_PACK_QUALIFICATION_PASS',len(models),previews,len(controls))

if __name__=='__main__':verify(Path(sys.argv[1]),Path(sys.argv[2]))
