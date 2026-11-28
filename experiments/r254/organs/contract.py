"""Fail-closed reference/overlay contract; does not simulate or fit internal anatomy."""
import hashlib,json,math
import numpy as np


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def proper_rigid(matrix):
    a=np.asarray(matrix)
    if a.shape!=(4,4) or a.dtype.kind not in 'fiu' or not np.isfinite(a).all():
        raise ValueError('invalid dimensioned source-frame matrix')
    if any(isinstance(x,(bool,np.bool_)) for row in matrix for x in row):raise ValueError('boolean source-frame coordinate')
    if not np.allclose(a[3],[0,0,0,1],atol=1e-12,rtol=0):raise ValueError('projective frame forbidden')
    if not np.allclose(a[:3,:3].T@a[:3,:3],np.eye(3),atol=1e-12,rtol=0) or not math.isclose(float(np.linalg.det(a[:3,:3])),1.,abs_tol=1e-12):
        raise ValueError('mirrored or stretched source frame forbidden')
    return a


def make_status(atlas,case,organs):
    payload={'schema':'oneirifact.organ-coupling-status/v1','atlas':atlas,'morphology_revision':case['morphology_revision'],'exterior_geometry_sha256':case['exterior_geometry_sha256'],'case_id':case['id'],'organs':[{'id':r['id'],'source_geometry_sha256':r['geometry']['source_geometry_sha256'],'reference_frame':atlas['frame'],'source_to_reference_matrix':np.eye(4).tolist(),'reference_response':'UNCHANGED_SEPARATE_SOURCE_REFERENCE','coupled_output_geometry_sha256':None,'parameter_propagation':'NOT_IMPLEMENTED','pose_binding':'MISSING','attachment_graph':'MISSING','secondary_response':'NOT_IMPLEMENTED','density_kg_per_m3':None,'mass_kg':None,'inertia_kg_m2':None,'geometric_property_eligibility':r['geometry']['eligibility'],'structural_role':r['role'],'source_role_is_rigidity_law':False} for r in organs],'registration':'UNAVAILABLE_FOR_THIS_EXTERIOR_REVISION','overlay':{'allowed_modes':['source_frame','separate_panels'],'anatomical_overlay_allowed':False,'default_visible':False},'physics':{'status':'NOT_IMPLEMENTED','segment_organ_mass_partition':'UNKNOWN_DO_NOT_SUM','deformable_material_and_volume_mesh':'MISSING','attachment_contact_conditions':'MISSING','gravity_inertia_secondary_response':'NOT_IMPLEMENTED'},'complete_anatomy':'NOT_CLAIMED'}
    payload['status_revision']=digest(payload)
    return payload


def validate_status(status,atlas,case,source_records,mode='source_frame'):
    if not isinstance(status,dict) or status.get('schema')!='oneirifact.organ-coupling-status/v1':raise ValueError('status schema')
    d=dict(status);revision=d.pop('status_revision',None)
    if digest(d)!=revision:raise ValueError('altered status')
    if status['atlas']!=atlas:raise ValueError('stale source atlas')
    if status['morphology_revision']!=case['morphology_revision'] or status['exterior_geometry_sha256']!=case['exterior_geometry_sha256']:raise ValueError('stale morphology revision')
    expected={r['id']:r['geometry']['source_geometry_sha256'] for r in source_records}
    actual={r['id']:r['source_geometry_sha256'] for r in status['organs']}
    if len(actual)!=len(status['organs']) or actual!=expected:raise ValueError('missing, duplicate or changed source organ')
    for r in status['organs']:
        a=proper_rigid(r['source_to_reference_matrix'])
        if not np.array_equal(a,np.eye(4)):raise ValueError('misregistered source reference')
        if r['coupled_output_geometry_sha256'] is not None or r['mass_kg'] is not None or r['inertia_kg_m2'] is not None or r['density_kg_per_m3'] is not None:raise ValueError('unsupported physical/coupling claim')
    if mode not in status['overlay']['allowed_modes'] or status['overlay']['anatomical_overlay_allowed'] or status['registration']!='UNAVAILABLE_FOR_THIS_EXTERIOR_REVISION':raise ValueError('unqualified anatomical overlay requested')
    if status!=make_status(atlas,case,source_records):raise ValueError('unsupported status fields or capability claim')
    return True


def reject_duplicate_compartments(records):
    # Exact coincident duplicates are a proved overlap; general collisions are NOT_RUN.
    seen={}
    for r in records:
        h=r['geometry']['triangle_corner_sha256']
        if h in seen:raise ValueError('coincident duplicate compartment: '+seen[h]+' / '+r['id'])
        seen[h]=r['id']
    return True
