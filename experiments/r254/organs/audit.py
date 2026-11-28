"""Audit actual frozen organ surfaces and the shipped exterior parameter evaluator."""
import argparse,collections,hashlib,io,json,os,platform,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from geometry import assess,geometry_hash,sha
from contract import make_status,validate_status

PINS={'male':{'artifact_id':15238389268,'zip_sha256':'18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9'},'female':{'artifact_id':15238269509,'zip_sha256':'513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542'}}


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def file_sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8<<20),b''):h.update(chunk)
    return h.hexdigest()


def checked_zip(path,sex):
    if file_sha(path)!=PINS[sex]['zip_sha256']:raise ValueError('source archive digest')
    z=zipfile.ZipFile(path)
    if z.testzip() is not None:raise ValueError('source ZIP CRC')
    receipt=json.loads(z.read('receipt.json'))
    if receipt['sex']!=sex or receipt['units']!='metres':raise ValueError('source sex label or units')
    for name,record in receipt['files'].items():
        h=hashlib.sha256()
        with z.open(name) as f:
            for chunk in iter(lambda:f.read(8<<20),b''):h.update(chunk)
        if h.hexdigest()!=record['sha256'] or z.getinfo(name).file_size!=record['bytes']:raise ValueError('source file digest: '+name)
    return z,receipt


def save_glb(path,meshes):
    scene=trimesh.Scene()
    palette=[[170,115,100,255],[105,170,175,255],[180,155,95,255],[140,125,190,255],[150,180,130,255]]
    for i,(name,v,f) in enumerate(meshes):
        m=trimesh.Trimesh(v,f,process=False)
        m.visual=trimesh.visual.ColorVisuals(mesh=m,vertex_colors=np.tile(palette[i%len(palette)],(len(v),1)))
        scene.add_geometry(m,node_name=name,geom_name=name)
    path.write_bytes(scene.export(file_type='glb'))
    check=trimesh.load(path,force='scene',process=False)
    errors=[]
    for name,v,f in meshes:
        q=check.geometry[name]
        if not np.array_equal(q.faces,f):raise ValueError('export triangle index/order changed')
        errors.append(float(np.max(np.abs(q.vertices-np.asarray(v,dtype=np.float32)))))
    if max(errors,default=0)!=0:raise ValueError('export float32 source coordinate transport')
    return {'sha256':file_sha(path),'meshes':len(meshes),'float32_roundtrip_max_error_m':max(errors,default=0),'original_ordered_triangle_count':sum(len(f) for _,v,f in meshes)}


def main(sex,archive,morph_folder,out):
    out.mkdir(parents=True,exist_ok=False);(out/'derived').mkdir();(out/'status').mkdir()
    lock=json.loads(Path(__file__).with_name('selection.json').read_text())
    z,receipt=checked_zip(archive,sex)
    inventory=json.loads(z.read('inventory.json'));by_id={r['id']:r for r in inventory}
    selected=lock[sex];cache={};records=[];arrays={};source_meshes=[];proofs={};corrections=[]
    for index,selection in enumerate(selected):
        ident=selection['id'];r=by_id[ident]
        if r['category']!=selection['source_category'] or r['triangles']!=selection['source_triangles'] or r['vertices']!=selection['source_vertices']:raise ValueError('source identity lock changed')
        category=r['category']
        if category not in cache:
            cache[category]=trimesh.load(io.BytesIO(z.read('layers/'+category+'.glb')),file_type='glb',force='scene',process=False)
        scene=cache[category];m=scene.geometry[ident]
        tf,key=scene.graph[ident]
        if key!=ident or not np.array_equal(tf,np.eye(4)):raise ValueError('unexpected unbaked source transform')
        v=np.array(m.vertices,dtype=np.float64);f=np.array(m.faces,dtype=np.int64)
        if not np.allclose(np.array([v.min(0),v.max(0)]),r['bounds_m'],atol=2e-7,rtol=0):raise ValueError('source frame/bounds mismatch')
        metrics,q,g,representative,inverse=assess(v,f)
        key='s'+str(index).zfill(3);arrays[key+'_vertices']=v;arrays[key+'_faces']=f
        proofs[key+'_source_representatives']=representative;proofs[key+'_source_index_to_quotient']=inverse
        record={**selection,'array_key':key,'source_record':r,'geometry':metrics,'effective_structure_family':selection['family'],'mechanical_properties':{'density':'UNKNOWN','material_domain':'UNQUALIFIED','compliance':'UNKNOWN','attachments':'MISSING','rigid_or_deformable_solver_binding':'NOT_IMPLEMENTED'}}
        records.append(record);source_meshes.append((ident,v,f))
        if metrics['geometric_properties'] is not None:
            record['derived_index_quotient_glb']=save_glb(out/'derived'/(ident+'.glb'),[(ident,q,g)])
        # Correct two concrete substring-classifier defects by exact admitted ID.
        if sex=='male' and ident in ('FJ3129','FJ3130'):
            corrections.append({'id':ident,'before_display_category':category,'corrected_family':'endocrine','basis':'Exact source FMA-mapped adrenal-gland identity; renal substring must not classify adrenal as urinary.','geometry_changed':False})
        if sex=='female' and ident=='hra_0382_VH_F_diaphragmatic_surface_of_liver':
            corrections.append({'id':ident,'before_display_category':category,'corrected_family':'digestive','basis':'Exact source liver-surface identity and VH_F_liver parent; diaphragmatic substring is not a respiratory-organ identity.','geometry_changed':False})
    atlas={'source_pr':43,'source_commit':'6528fbc21c49885e63f9912ea01c09f6c471abed','dataset':receipt['provenance']['source'],'sex_reference_label':sex,'artifact_id':PINS[sex]['artifact_id'],'archive_sha256':PINS[sex]['zip_sha256'],'inventory_sha256':sha(z.read('inventory.json')),'frame':receipt['provenance']['frame'],'units':'metres'}
    derived=[]
    if sex=='female':
        spec=lock['female_spleen_assembly'];members=spec['members']
        actual=[r['id'] for r in inventory if spec['source_parent'] in r.get('hierarchy',[])]
        if set(actual)!=set(members) or len(members)!=5:raise ValueError('incomplete same-parent spleen patch assembly')
        vv=[];ff=[];offset=0
        for ident in members:
            name,v,f=next(row for row in source_meshes if row[0]==ident);vv.append(v);ff.append(f+offset);offset+=len(v)
        v=np.concatenate(vv);f=np.concatenate(ff);metrics,q,g,representative,inverse=assess(v,f)
        if metrics['geometric_properties'] is None:raise ValueError('source spleen exact quotient did not close cleanly')
        arrays['spleen_assembly_vertices']=v;arrays['spleen_assembly_faces']=f
        proofs['spleen_assembly_source_representatives']=representative;proofs['spleen_assembly_source_index_to_quotient']=inverse
        derived.append({'id':'derived_HRA_same_parent_spleen_exact_index_quotient','members':members,'source_parent':spec['source_parent'],'recipe':spec['policy'],'array_key':'spleen_assembly','geometry':metrics,'new_anatomy_inferred':False,'registered_to_morphed_exterior':False,'physical_mass_kg':None,'product':save_glb(out/'derived'/'source-spleen-exact-quotient.glb',[('source_spleen_exact_quotient',q,g)])})
    source_product=save_glb(out/'selected-source-organs.glb',source_meshes)
    np.savez_compressed(out/'original-selected-surfaces.npz',**arrays)
    np.savez_compressed(out/'exact-index-maps.npz',**proofs)
    for name in ['ATTRIBUTION.txt','LICENSE-source.html','LICENSE-update.html']:
        if name in z.namelist():(out/name).write_bytes(z.read(name))
    write_json(out/'source-inventory.json',inventory)
    write_json(out/'selection-lock.json',lock)
    write_json(out/'classification-corrections.json',corrections)
    morph=json.loads((morph_folder/'morphology-audit.json').read_text())
    cases=[r for r in morph['cases'] if r['sex']==sex]
    if len(cases)!=41:raise ValueError('actual morphology matrix size')
    propagation=[]
    for case in cases:
        # Ensure these are actual saved evaluator outputs, not a response table alone.
        if file_sha(morph_folder/case['position_file'])!=case['exterior_geometry_sha256'] or file_sha(morph_folder/case['spec_file'])!=case['morphology_revision']:raise ValueError('changed actual morphology output')
        status=make_status(atlas,case,records);validate_status(status,atlas,case,records)
        filename=case['id'].split('/',1)[1]+'.json';write_json(out/'status'/filename,status)
        propagation.append({'case_id':case['id'],'morphology_revision':case['morphology_revision'],'exterior_displacement_from_baseline':case['displacement_from_baseline'],'responding_coupled_organ_ids':[],'unchanged_separate_reference_ids':[r['id'] for r in records],'not_generated_coupled_ids':[r['id'] for r in records],'organ_function':'NOT_IMPLEMENTED','status_file':'status/'+filename})
    report={'schema':'oneirifact.real-organ-geometric-audit/v1','sex':sex,'atlas':atlas,'source_manifest_files_verified':len(receipt['files']),'source_product':source_product,'selected_source_meshes':len(records),'selected_source_triangles':sum(r['source_triangles'] for r in records),'organs':records,'derived_same_source_compartments':derived,'classification_corrections':corrections,'morphology_cases':propagation,'actual_organs_responding_to_morphology':0,'parameter_propagation_status':'MISSING_IMPLEMENTATION','geometric_qualifications':{'closed_source_elements':sum(r['geometry']['geometric_properties'] is not None for r in records),'closed_same_source_assemblies':len(derived)},'coupling_candidate':'NOT_EMITTED_NO_QUALIFIED_SOURCE_TO_EXTERIOR_REGISTRATION','physics':{'organ_mass_density':'UNKNOWN','organ_mass_kg':None,'whole_body_mass_kg':None,'inertia_kg_m2':None,'tissue_compliance_and_damping':'UNKNOWN','attachment_graph':'MISSING','gravity_and_acceleration_response':'NOT_IMPLEMENTED','general_collision_and_self_intersection':'NOT_RUN','overlapping_material_region_partition':'UNQUALIFIED_DO_NOT_SUM'},'not_claimed':['clinical accuracy','complete organ inventory','whole-body physical mass','anatomical fit','organ response to age or mass-shape sliders','secondary motion','native Oneirifact engine integration'],'environment':{'python':platform.python_version(),'numpy':np.__version__,'trimesh':trimesh.__version__,'source_head_commit':os.environ.get('SOURCE_HEAD_COMMIT'),'github_run_id':os.environ.get('GITHUB_RUN_ID')}}
    write_json(out/'audit.json',report)
    print(json.dumps({'sex':sex,'selected_source_meshes':len(records),'source_triangles':report['selected_source_triangles'],'conditional_geometric_properties':report['geometric_qualifications'],'actual_morph_cases':len(cases),'organ_coupling':report['parameter_propagation_status']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('sex',choices=['male','female']);p.add_argument('archive',type=Path);p.add_argument('morph_folder',type=Path);p.add_argument('output',type=Path);a=p.parse_args();main(a.sex,a.archive,a.morph_folder,a.output)
