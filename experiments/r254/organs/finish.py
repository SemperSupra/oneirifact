"""Finalize actual-source evidence without upgrading missing coupling to PASS."""
import argparse,hashlib,json,os,shutil
from pathlib import Path
from PIL import Image


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def finish(folder,morph):
    audit=json.loads((folder/'audit.json').read_text());controls=json.loads((folder/'independent-controls.json').read_text())
    if controls['status']!='PASS_BOUNDED_GEOMETRY_AND_REJECTION_CONTROLS':raise ValueError('independent geometry or negative controls failed')
    for name in ['source-geometry-before-after.png','actual-morphology-organ-response.png']:
        with Image.open(folder/name) as im:im.verify()
    sex=audit['sex'];dst=folder/'actual-exterior-cases';dst.mkdir()
    shutil.copytree(morph/sex,dst/sex);shutil.copyfile(morph/'faces.u32',dst/'faces.u32')
    source=json.loads((morph/'morphology-audit.json').read_text());source['cases']=[r for r in source['cases'] if r['sex']==sex]
    (dst/'morphology-audit.json').write_text(json.dumps(source,indent=2)+'\n')
    for name in ['API.md','source-state.json']:
        shutil.copyfile(Path(__file__).with_name(name),folder/name)
    result={'schema':'oneirifact.organ-coupling-audit-receipt/v1','status':'PASS_BOUNDED_SOURCE_GEOMETRY_AUDIT','source_head_commit':os.environ.get('SOURCE_HEAD_COMMIT'),'run_id':os.environ.get('GITHUB_RUN_ID'),'sex':sex,'source_atlas':audit['atlas'],'actual_morphology_cases':len(source['cases']),'actual_selected_source_meshes':audit['selected_source_meshes'],'actual_source_triangles':audit['selected_source_triangles'],'geometric_integral_counts':audit['geometric_qualifications'],'independent_source_moment_crosschecks':len(controls['actual_source_moment_crosschecks']),'negative_and_analytic_controls':controls['count'],'organ_parameter_propagation':'MISSING_IMPLEMENTATION','real_organ_attachment_mass_and_secondary_response':'NOT_IMPLEMENTED_OR_UNKNOWN','anatomical_overlay':'NOT_QUALIFIED','geometric_coupling_candidate':'NOT_EMITTED_NO_QUALIFIED_REGISTRATION','physics_and_realism':'NOT_QUALIFIED','files':{}}
    for p in sorted(folder.rglob('*')):
        if p.is_file():result['files'][p.relative_to(folder).as_posix()]={'bytes':p.stat().st_size,'sha256':sha(p)}
    (folder/'receipt.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['files','source_atlas']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('morphology',type=Path);a=p.parse_args();finish(a.folder,a.morphology)
