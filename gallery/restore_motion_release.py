"""Restore exact versioned public motion packs; browser uses only same-origin assets."""
import argparse,json,subprocess,tempfile
from pathlib import Path
import motion_pack as p
ROOT=Path(__file__).resolve().parents[1]
def restore(lock_path=None,source=None,dest=None):
    lock=p.parse((lock_path or ROOT/'gallery/motion-release-lock.json').read_bytes())
    p.require(lock['schema']=='oneirifact.motion-browser-releases/v1' and lock['packs'],'release lock schema')
    dest=dest or ROOT/'site/motion/data';p.require(not dest.exists(),'motion restore destination exists');dest.mkdir(parents=True)
    indexes=[]
    with tempfile.TemporaryDirectory(prefix='motion-release-') as temp:
        for entry in lock['packs']:
            p.require(entry['repository']=='SemperSupra/oneirifact' and p.SEGMENT.fullmatch(entry['tag']) and entry['pack_id']==entry['tag'] and entry['asset']==entry['tag']+'.zip','release identity')
            path=source if source and len(lock['packs'])==1 else source/entry['asset'] if source else Path(temp)/entry['asset']
            if source is None:
                url='https://github.com/'+entry['repository']+'/releases/download/'+entry['tag']+'/'+entry['asset']
                subprocess.run(['curl','--fail','--silent','--show-error','--location','--proto','=https','--proto-redir','=https','--tlsv1.2','--connect-timeout','12','--max-time','180','--max-filesize',str(p.MAX_TOTAL),'--output',str(path),url],check=True,timeout=190)
            files=p.restore(path,entry['sha256'],dest/entry['pack_id'])
            c=p.parse((dest/entry['pack_id']/'catalog.json').read_bytes())
            p.require(len(files)==entry['files'] and sum(f['bytes'] for f in files.values())==entry['unpacked_bytes'],'release inventory')
            p.require(len(c['packages'])==entry['packages'] and sum(bool(v['preview']) for package in c['packages'] for v in package['clips'])==entry['previews'],'release product counts')
            indexes.append({'pack_id':entry['pack_id'],'catalog':'data/'+entry['pack_id']+'/catalog.json','base_url':'data/'+entry['pack_id']+'/','archive_url':'https://github.com/'+entry['repository']+'/releases/download/'+entry['tag']+'/'+entry['asset'],'archive_sha256':entry['sha256']})
    (dest.parent/'catalogs.json').write_text(json.dumps({'schema':'oneirifact.motion-browser-index/v1','packs':indexes},indent=2)+'\n')
    print('MOTION_DURABLE_RESTORE_PASS',json.dumps(indexes),flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--lock',type=Path);a.add_argument('--source',type=Path);a.add_argument('--dest',type=Path);q=a.parse_args();restore(q.lock,q.source,q.dest)
