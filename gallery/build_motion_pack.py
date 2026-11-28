"""Build the public motion corpus from exact admitted public producer archives."""
import argparse,hashlib,json,math,struct,subprocess,zipfile
from pathlib import Path
import motion_pack as pack

HERE=Path(__file__).resolve().parent
TITLES={'standing':'Standing','sitting':'Seated hold','sit_to_stand':'Sit to stand','squatting':'Squat','crouching':'Crouch','walking':'Walk','jogging':'Jog','running':'Run','brushing_teeth':'Brush gesture','walking_brush':'Walk and brush','showering':'Shower gesture','eating_ice_cream_cone':'Ice-cream approach','swimming_front_crawl':'Front crawl','bathing_seated_wash':'Seated wash'}
POSTERS={'standing':'01-standing.png','sitting':'02-sitting.png','sit_to_stand':'02-sitting.png','squatting':'03-squat.png','walking':'04-walk.png','brushing_teeth':'05-brushing.png','walking_brush':'05-brushing.png','crouching':'07-crouching.png','jogging':'08-jogging.png','running':'09-running.png','showering':'10-showering.png','eating_ice_cream_cone':'11-ice-cream.png','swimming_front_crawl':'01-crawl-entry.png','bathing_seated_wash':'03-seated-wash.png'}
def glb(raw):
    pack.require(raw[:4]==b'glTF' and struct.unpack_from('<II',raw,4)==(2,len(raw)),'GLB header')
    n,t=struct.unpack_from('<II',raw,12);pack.require(t==0x4e4f534a,'GLB JSON');d=pack.parse(raw[20:20+n]);p=20+n
    size,t=struct.unpack_from('<II',raw,p);pack.require(t==0x004e4942 and p+8+size==len(raw),'GLB BIN')
    pack.require(not d.get('extensionsRequired') and all('uri' not in b for b in d['buffers']),'self-contained uncompressed GLB')
    return d,raw[p+8:]
def accessor(d,b,i):
    a=d['accessors'][i];v=d['bufferViews'][a['bufferView']];pack.require('sparse' not in a,'sparse accessor unsupported')
    fmt,size={5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}[a['componentType']]
    n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',size*n)
    values=[struct.unpack_from('<'+fmt*n,b,start+k*stride) for k in range(a['count'])]
    if a.get('normalized'):
        bound={5121:255,5123:65535,5120:127,5122:32767}[a['componentType']];values=[tuple(max(-1,x/bound) for x in row) for row in values]
    return values
def model_inventory(d,b):
    skins=[];positive_max=0;weight_error=0;body_vertices=0
    for node in d['nodes']:
        if 'skin' not in node:continue
        skin=d['skins'][node['skin']];primitives=[]
        for p in d['meshes'][node['mesh']]['primitives']:
            pack.require(p.get('mode',4)==4 and not p.get('targets'),'triangle mesh without unsupported morph targets')
            attrs=p['attributes'];sets=sorted(int(k.split('_')[1]) for k in attrs if k.startswith('WEIGHTS_'))
            pack.require(sets==list(range(len(sets))) and 1<=len(sets)<=3,'weight sets must be complete and at most three')
            weights=[accessor(d,b,attrs['WEIGHTS_'+str(k)]) for k in sets];joints=[accessor(d,b,attrs['JOINTS_'+str(k)]) for k in sets]
            count=len(weights[0]);pack.require(all(len(w)==count for w in weights+joints),'joint/weight count')
            for vi in range(count):
                w=[x for s in weights for x in s[vi]];j=[x for s in joints for x in s[vi]]
                pack.require(all(math.isfinite(x) and x>=0 for x in w) and all(type(x)==int and 0<=x<len(skin['joints']) for x in j),'invalid full influences')
                positive_max=max(positive_max,sum(x>0 for x in w));weight_error=max(weight_error,abs(sum(w)-1))
            body_vertices+=count;primitives.append({'vertices':count,'weight_sets':len(sets),'slots':4*len(sets)})
        skins.append({'node':node.get('name',''),'joints':len(skin['joints']),'primitives':primitives})
    pack.require(skins and positive_max<=12 and weight_error<2e-5,'full-weight skin inventory')
    return {'skins':skins,'total_skin_vertices':body_vertices,'maximum_positive_influences':positive_max,'maximum_weight_sum_error':weight_error,'source_weights_preserved':True}
def metadata_file(folder,root,raw,name):
    p=folder/name;p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():pack.require(p.read_bytes()==raw,'asset collision')
    else:p.write_bytes(raw)
    return {'path':p.relative_to(root).as_posix(),'bytes':len(raw),'sha256':pack.sha(raw)}
def build(inputs,archives,out):
    spec=pack.parse(inputs.read_bytes());pack.require(spec['schema']=='oneirifact.motion-browser-inputs/v1','input schema')
    out.mkdir(parents=True,exist_ok=False);data=out/'data';data.mkdir();packages=[]
    archives.mkdir(parents=True,exist_ok=True)
    for entry in spec['inputs']:
        source=archives/entry['archive']
        if not source.exists():
            with source.open('wb') as f:subprocess.run(['gh','api','repos/'+spec['repository']+'/actions/artifacts/'+str(entry['artifact_id'])+'/zip'],stdout=f,check=True,timeout=120)
        pack.require(source.stat().st_size==entry['archive_bytes'] and pack.digest(source)==entry['archive_sha256'],'source archive custody')
        with zipfile.ZipFile(source) as z:
            pack.require(z.testzip() is None,'source ZIP CRC');names=set(z.namelist());family=entry['family'];captured=family=='r247';water=family=='r246';daily=family=='r248'
            receipt_name='capture-receipt.json' if captured else 'consumer-receipt.json';receipt=pack.parse(z.read(receipt_name));case=receipt['case']
            pack.require(receipt['source_head_commit']==entry['producer_head'],'producer head')
            if entry['archive_producer_head']!=entry['producer_head']:
                media=pack.parse(z.read('media-packaging-receipt.json'))
                pack.require(media['packager_head_commit']==entry['archive_producer_head'] and media['source_head_commit']==entry['producer_head'],'media/source head custody')
            for name,r in receipt['files'].items():
                raw=z.read(name);pack.require(len(raw)==r['bytes'] and pack.sha(raw)==r['sha256'],'producer inner asset '+name)
            capture=receipt.get('capture');pid=family+'-'+case['id']+('-'+capture.replace('_','-') if captured else '')
            folder=data/pid;folder.mkdir();model_name='captured-motion-baseline.glb' if captured else 'aquatic-prototypes.glb' if water else 'activity-prototypes.glb'
            model_raw=z.read(model_name);d,b=glb(model_raw);inv=model_inventory(d,b)
            write=lambda raw,name:metadata_file(folder,data,raw,name)
            assets={'model':write(model_raw,'model.glb'),'native_scene':write(z.read(model_name[:-4]+'.blend'),'scene.blend'),'receipt':write(z.read(receipt_name),'producer-receipt.json')}
            legal=sorted(n for n in names if '/' not in n and ('LICENSE' in n or 'READMEFIRST' in n))
            pack.require(legal,'original source rights missing')
            rights='\n\n'.join('===== '+n+' =====\n'+z.read(n).decode('utf-8') for n in legal)
            assets['rights']=write(rights.encode(),'rights.txt')
            stills={}
            chosen=sorted(n for n in names if '/' not in n and n.endswith('.png') and (n[:2].isdigit() or 'contact-sheet' in n or n=='captured-motion-review.png'))
            for n in chosen:stills[n]=write(z.read(n),'stills/'+n.lower())
            if captured:stills['capture-first.png']=write(z.read('render-frames/0000.png'),'stills/capture-first.png')
            contact='captured-motion-review.png' if captured else 'aquatic-native-contact-sheet.png' if water else 'daily-contact-sheet.png' if daily else 'activity-contact-sheet.png'
            poster='capture-first.png' if captured else '01-crawl-entry.png' if water else '08-jogging.png' if daily else '04-walk.png'
            assets.update(poster=stills[poster],contact_sheet=stills[contact],stills=list(stills.values()))
            videos={v['activity_id']:v for v in receipt.get('videos',[])};states={a['activity_id']:a for a in receipt.get('activities',[])};clips=[]
            for animation in d['animations']:
                name=animation['name'];time_max=max(row[0] for sampler in animation['samplers'] for row in accessor(d,b,sampler['input']))
                title=('Captured walk' if capture=='07_01' else 'Captured stool sit / stand') if captured else TITLES.get(name,name.replace('_',' ').title())
                clip={'id':name,'title':title,'animation_name':name,'duration_s':time_max,'evaluation':'all_captured_frames' if captured else states[name]['native_rig_evaluation'],'preview':None,'poster':stills.get(POSTERS.get(name,''),assets['poster'])}
                if captured:
                    media_name='captured-source-vs-retargeted.mp4';v={'fps':receipt['render']['fps'],'frames':receipt['render']['frames']}
                else:v=videos.get(name);media_name=v.get('file') if v else None
                if media_name:
                    clip['preview']={**write(z.read(media_name),'previews/'+name.lower()+'.mp4'),'fps':v['fps'],'frames':v['frames'],'duration_s':v['frames']/v['fps']}
                clips.append(clip)
            nonuniform=case['id']=='maleolderflat';m=case['morphology'];sex=case['sex_variant'];stature=m['stature_m']
            footwear='Barefoot' if captured or water else 'Stiletto support proxy' if case['shoe_profile']=='stiletto' else 'Flat support proxy'
            group='Captured baselines' if captured else 'Aquatic studies' if water else 'Daily activities' if daily else 'Morphology & footwear'
            title=(('Nonuniform male shape' if nonuniform else sex.title()+' · '+format(stature,'.2f')+' m')+' · '+('capture '+capture if captured else 'aquatic' if water else 'daily' if daily else case['shoe_profile']))
            p={'id':pid,'title':title,'group':group,'source_kind':entry['source_kind'],'actors':[{'id':case['id'],'sex_variant':sex,'stature_m':stature,'morphology_label':'Nonuniform source morph' if nonuniform else 'Athletic exterior with uniform stature adaptation','footwear':footwear,'source_bind_sha256':m['source_bind_sha256']}],
               'clips':clips,'assets':assets,'provenance':{'repository':spec['repository'],'producer_head':entry['producer_head'],'producer_run_id':receipt['run_id'],'artifact_run_id':entry['producer_run_id'],'artifact_producer_head':entry['archive_producer_head'],'artifact_id':entry['artifact_id'],'artifact_sha256':entry['archive_sha256'],'artifact_bytes':entry['archive_bytes'],'source_revision':case['source']['source_variant']},
               'qualification':{'transport':'PASS_WITH_RECORDED_PROBES','maximum_sampled_transport_error_m':receipt['worst_transport_error_m'],'realism':'HELD','contact':'NOT_QUALIFIED','physics':'NOT_QUALIFIED','retarget':'HELD' if captured else 'NOT_APPLICABLE'},
               'included_layers':['Source exterior','163-bone deformation rig']+([] if captured or water else ['Rigid footwear support proxies']),
               'omitted_layers':['Internal anatomical meshes','Physiological tissues']+(['Native water, tub and sponge context'] if water else ['Native task props and scene context'] if not captured else ['Comparison source skeleton in the rendered video']),
               'notes':(['Captured body motion; no contact correction, floor or seat fitting.'] if captured else ['Original authored kinematic prototype; natural motion and physical interaction remain under review.'])+(['Six secondary clips retain five sampled native keys; use the dense daily packages for their fuller evaluation.'] if family=='r245' else []),'model_inventory':inv}
            packages.append(p);print('MOTION_PACKAGE',pid,len(clips),sum(bool(c['preview']) for c in clips),flush=True)
    catalog={'schema':'oneirifact.motion-browser/v1','pack_id':spec['pack_id'],'title':'Reusable motion research · R245–R248','scope':'Actual source products from public CPU execution. Replay evidence is separate from realistic motion, physical contact and internal anatomy.','packages':packages}
    (data/'catalog.json').write_text(json.dumps(catalog,indent=2,allow_nan=False)+'\n')
    target=out/(spec['pack_id']+'.zip');digest,entries=pack.pack(data,target);pack.verify(target,digest)
    lock={'pack_id':spec['pack_id'],'repository':spec['repository'],'tag':spec['pack_id'],'asset':target.name,'sha256':digest,'files':len(entries),'unpacked_bytes':sum(r['bytes'] for r in entries.values()),'packages':len(packages),'previews':sum(bool(c['preview']) for p in packages for c in p['clips'])}
    report={'schema':'oneirifact.motion-browser-pack-receipt/v1','status':'PASS_EXACT_PUBLIC_SOURCE_PACK','input_manifest_sha256':pack.digest(inputs),'release_lock':lock,'files':entries}
    (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');(out/'release-lock.json').write_text(json.dumps({'schema':'oneirifact.motion-browser-releases/v1','packs':[lock]},indent=2)+'\n')
    print('MOTION_PACK_COMPLETE',json.dumps(lock),flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--inputs',type=Path,default=HERE/'motion-inputs.json');a.add_argument('--archives',type=Path,required=True);a.add_argument('--out',type=Path,required=True);q=a.parse_args();build(q.inputs,q.archives,q.out)
