"""Independent tetrahedral moments and explicit adversarial source/status controls.

Analytic fixtures test the critic; only the separate actual-source records are
organ evidence. No synthetic control is reported as organ coupling.
"""
import argparse,copy,json
from pathlib import Path
import numpy as np
from geometry import assess,exact_quotient
from contract import digest,validate_status,reject_duplicate_compartments


def tetrahedral_moments(v,f):
    origin=(v.min(0)+v.max(0))/2
    t=v[f]-origin;a,b,c=t[:,0],t[:,1],t[:,2]
    volume=np.einsum('ij,ij->i',a,np.cross(b,c))/6
    total=volume.sum();s=a+b+c
    first=np.einsum('i,ij->j',volume/4,s)
    second=np.einsum('i,ij,ik->jk',volume/20,s,s)
    for p in [a,b,c]:second+=np.einsum('i,ij,ik->jk',volume/20,p,p)
    center=first/total
    inertia=np.trace(second)*np.eye(3)-second-total*(np.dot(center,center)*np.eye(3)-np.outer(center,center))
    return float(total),center+origin,inertia


def check_moments(name,v,f,properties):
    volume,center,inertia=tetrahedral_moments(v,f)
    errors={'volume_m3':abs(volume-properties['volume_m3']),'centroid_m':float(np.linalg.norm(center-properties['volume_centroid_source_m'])),'inertia_per_density_m5':float(np.max(np.abs(inertia-properties['inertia_per_density_m5_about_volume_centroid'])))}
    return {'id':name,'errors':errors,'status':'PASS' if errors['volume_m3']<=1e-12 and errors['centroid_m']<=1e-9 and errors['inertia_per_density_m5']<=1e-12 else 'FAIL'}


def run(folder):
    report=json.loads((folder/'audit.json').read_text());data=np.load(folder/'original-selected-surfaces.npz')
    crosschecks=[]
    for r in report['organs']+report['derived_same_source_compartments']:
        p=r['geometry']['geometric_properties']
        if p is not None:
            key=r['array_key'];crosschecks.append(check_moments(r['id'],data[key+'_vertices'],data[key+'_faces'],p))
    controls=[]
    def expect(name,condition,kind='ANALYTIC_CRITIC_CONTROL'):
        controls.append({'id':name,'kind':kind,'status':'PASS' if bool(condition) else 'FAIL'})
    def rejects(name,fn):
        try:fn()
        except ValueError as e:controls.append({'id':name,'kind':'ACTUAL_SOURCE_CONTROLLED_CORRUPTION','status':'PASS','rejection':str(e)})
        else:controls.append({'id':name,'kind':'ACTUAL_SOURCE_CONTROLLED_CORRUPTION','status':'FAIL'})
    # Manual rectangular prism with known exact volume/centroid/inertia.
    v=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],float)*[.02,.03,.04]+[.2,-.1,1.]
    f=np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
    m=assess(v,f)[0];p=m['geometric_properties'];vol=.04*.06*.08
    expected=np.diag([vol*(.06**2+.08**2)/12,vol*(.04**2+.08**2)/12,vol*(.04**2+.06**2)/12])
    expect('analytic_box_integrals',abs(p['volume_m3']-vol)<1e-15 and np.max(abs(np.array(p['volume_centroid_source_m'])-[.2,-.1,1.]))<1e-12 and np.max(abs(np.array(p['inertia_per_density_m5_about_volume_centroid'])-expected))<1e-15)
    soup=v[f].reshape(-1,3);sf=np.arange(len(soup)).reshape(-1,3);m,q,g,*_=assess(soup,sf)
    expect('exact_seam_quotient_exercised',m['before']['boundary_edges']==36 and m['exact_quotient']['boundary_edges']==0 and m['ordered_triangle_corners_byte_identical'] and m['geometric_properties'] is not None)
    expect('missing_face_is_not_repaired',assess(v,f[:-1])[0]['geometric_properties'] is None)
    expect('duplicate_face_is_not_discarded',assess(v,np.vstack([f,f[0]]))[0]['geometric_properties'] is None)
    expect('reversed_closed_orientation_withheld',assess(v,f[:,[0,2,1]])[0]['geometric_properties'] is None)
    # Two closed tetrahedra touching only at one vertex have a bad vertex link.
    tv=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
    tf=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
    neg=tv*np.array([-1,-1,-1]);nv=np.vstack([tv,neg[1:]]);nf=np.vstack([tf,np.where(tf[:,[0,2,1]]==0,0,tf[:,[0,2,1]]+3)])
    pinched=assess(nv,nf)[0]
    expect('pinched_vertex_rejected_despite_closed_edges',pinched['exact_quotient']['boundary_edges']==0 and pinched['exact_quotient']['nonmanifold_edges']==0 and pinched['exact_quotient']['nonmanifold_vertex_links']>0 and pinched['geometric_properties'] is None)
    t=assess(tv,tf)[0]['geometric_properties'];expected=np.full((3,3),1/480);np.fill_diagonal(expected,1/80)
    expect('analytic_tetrahedron_integrals',abs(t['volume_m3']-1/6)<1e-15 and np.max(abs(np.array(t['volume_centroid_source_m'])-.25))<1e-15 and np.max(abs(np.array(t['inertia_per_density_m5_about_volume_centroid'])-expected))<1e-15)
    # Recheck source-derived numeric values after a large rigid translation.
    actual=next(r for r in report['organs'] if r['geometry']['geometric_properties'] is not None)
    key=actual['array_key'];av=data[key+'_vertices'];af=data[key+'_faces'];shift=np.array([10.,-5.,3.])
    shifted=assess(av+shift,af)[0]['geometric_properties'];original=actual['geometry']['geometric_properties']
    expect('actual_source_translation_invariance',abs(shifted['volume_m3']-original['volume_m3'])<1e-12 and np.linalg.norm(np.array(shifted['volume_centroid_source_m'])-shift-original['volume_centroid_source_m'])<1e-9 and np.max(abs(np.array(shifted['inertia_per_density_m5_about_volume_centroid'])-original['inertia_per_density_m5_about_volume_centroid']))<1e-12,'ACTUAL_SOURCE_GEOMETRIC_CROSSCHECK')
    expect('actual_source_missing_triangle_withheld',assess(av,af[:-1])[0]['geometric_properties'] is None,'ACTUAL_SOURCE_CONTROLLED_CORRUPTION')
    badv=av.copy();badv[0,0]=np.nan;rejects('nonfinite_actual_source',lambda:assess(badv,af))
    rejects('fractional_indices_rejected',lambda:assess(av,af.astype(float)+.25))
    status=json.loads((folder/'status'/'baseline.json').read_text())
    def case(s):return {'id':s['case_id'],'morphology_revision':s['morphology_revision'],'exterior_geometry_sha256':s['exterior_geometry_sha256']}
    baseline=case(status);atlas=report['atlas'];records=report['organs']
    expect('baseline_reference_status_accepted',validate_status(status,atlas,baseline,records),'ACTUAL_SOURCE_REFERENCE_CONTRACT')
    def signed(s):s=copy.deepcopy(s);s.pop('status_revision',None);s['status_revision']=digest(s);return s
    def mutated(name,edit):
        q=copy.deepcopy(status);edit(q);q=signed(q)
        rejects(name,lambda:validate_status(q,atlas,baseline,records))
    mutated('missing_actual_organ_rejected',lambda s:s['organs'].pop())
    mutated('changed_source_geometry_rejected',lambda s:s['organs'][0].update(source_geometry_sha256='0'*64))
    mutated('mirrored_source_frame_rejected',lambda s:s['organs'][0]['source_to_reference_matrix'][0].__setitem__(0,-1))
    mutated('nonuniform_source_stretch_rejected',lambda s:s['organs'][0]['source_to_reference_matrix'][0].__setitem__(0,2))
    mutated('misregistered_reference_rejected',lambda s:s['organs'][0]['source_to_reference_matrix'][0].__setitem__(3,.1))
    mutated('invented_mass_rejected',lambda s:s['organs'][0].update(mass_kg=1))
    mutated('invented_coupled_output_rejected',lambda s:s['organs'][0].update(coupled_output_geometry_sha256=s['organs'][0]['source_geometry_sha256']))
    rejects('unregistered_overlay_rejected',lambda:validate_status(status,atlas,baseline,records,mode='anatomical_overlay'))
    new=json.loads((folder/'status'/'common-height_m-high.json').read_text())
    rejects('stale_actual_morphology_rejected',lambda:validate_status(status,atlas,case(new),records))
    revised=dict(atlas);revised['archive_sha256']='f'*64
    rejects('stale_atlas_revision_rejected',lambda:validate_status(status,revised,baseline,records))
    dup=copy.deepcopy(actual);dup['id']='deliberate_renamed_duplicate'
    rejects('exact_coincident_compartment_overlap_rejected',lambda:reject_duplicate_compartments([actual,dup]))
    if report['sex']=='female':
        selected=[r for r in records if r['family']=='spleen'];vv=[];ff=[];offset=0
        for r in selected[:-1]:
            k=r['array_key'];a=data[k+'_vertices'];b=data[k+'_faces'];vv.append(a);ff.append(b+offset);offset+=len(a)
        missing=assess(np.concatenate(vv),np.concatenate(ff))[0]
        expect('actual_spleen_missing_patch_not_filled',missing['geometric_properties'] is None and missing['exact_quotient']['boundary_edges']>0,'ACTUAL_SOURCE_CONTROLLED_CORRUPTION')
    result={'schema':'oneirifact.organ-audit-independent-controls/v1','status':'PASS_BOUNDED_GEOMETRY_AND_REJECTION_CONTROLS' if all(r['status']=='PASS' for r in crosschecks+controls) else 'FAIL','actual_source_moment_crosschecks':crosschecks,'controls':controls,'count':len(controls),'limits':['No scientific realism or tissue calibration qualification','Exact coincident duplicate overlap only; general inter-organ/self-collision not run','Synthetic fixtures only qualify the geometry critic','Conditional geometric integrals do not define heterogeneous tissue mass']}
    (folder/'independent-controls.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'actual_moment_crosschecks':len(crosschecks),'controls':len(controls),'failed':[r['id'] for r in crosschecks+controls if r['status']!='PASS']}),flush=True)
    if result['status']=='FAIL':raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);run(p.parse_args().folder)
