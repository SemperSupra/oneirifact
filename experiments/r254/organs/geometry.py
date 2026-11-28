"""Exact-index quotient and conditional geometric moments of real source surfaces.

No repair, filling, tolerance weld, density assignment, or anatomy fitting.
The inertia integral has units m^5 (inertia divided by uniform density).
"""
import hashlib
import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def sha(data):
    return hashlib.sha256(data).hexdigest()


def geometry_hash(vertices, faces):
    return sha(np.asarray(vertices, dtype='<f8').tobytes()+np.asarray(faces, dtype='<u4').tobytes())


def exact_quotient(vertices, faces):
    if np.asarray(vertices).dtype.kind not in 'fiu' or np.asarray(faces).dtype.kind not in 'iu':
        raise ValueError('numeric coordinates and integer indices required')
    v=np.asarray(vertices,dtype='<f8');f=np.asarray(faces,dtype=np.int64)
    if v.ndim!=2 or v.shape[1]!=3 or f.ndim!=2 or f.shape[1]!=3 or not len(v) or not len(f):
        raise ValueError('nonempty triangle mesh required')
    if not np.isfinite(v).all() or f.min()<0 or f.max()>=len(v):
        raise ValueError('invalid coordinates or face index')
    # Byte equivalence is stronger than a tolerance weld; -0 is retained separately.
    rows=np.ascontiguousarray(v).view(np.dtype((np.void,24))).ravel()
    _,representative,inverse=np.unique(rows,return_index=True,return_inverse=True)
    q=v[representative];g=inverse[f]
    if q[g].tobytes()!=v[f].tobytes():
        raise ValueError('ordered triangle corner bytes changed')
    return q,g,representative,inverse


def topology(v,f):
    edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
    canonical=np.sort(edges,axis=1)
    unique,inverse,count=np.unique(canonical,axis=0,return_inverse=True,return_counts=True)
    winding=np.bincount(inverse,weights=np.where(edges[:,0]<edges[:,1],1,-1),minlength=len(unique))
    _,duplicates=np.unique(np.sort(f,axis=1),axis=0,return_counts=True)
    cross=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
    degenerate=np.count_nonzero(np.linalg.norm(cross,axis=1)==0)
    used=np.unique(f)
    graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(v),len(v))).tocsr()
    _,labels=connected_components(graph,directed=False)
    components=len(np.unique(labels[used]))
    # A two-face edge condition alone does not exclude a pinched vertex.
    links={int(i):[] for i in used}
    for a,b,c in f:
        links[int(a)].append((int(b),int(c)));links[int(b)].append((int(c),int(a)));links[int(c)].append((int(a),int(b)))
    bad_links=0
    for pairs in links.values():
        adjacency={}
        for a,b in pairs:
            adjacency.setdefault(a,[]).append(b);adjacency.setdefault(b,[]).append(a)
        if any(len(n)!=2 for n in adjacency.values()):bad_links+=1;continue
        reached=set();pending=[next(iter(adjacency))]
        while pending:
            node=pending.pop()
            if node in reached:continue
            reached.add(node);pending.extend(adjacency[node])
        if len(reached)!=len(adjacency):bad_links+=1
    return {'vertices':len(v),'used_vertices':len(used),'triangles':len(f),'edges':len(unique),'boundary_edges':int(np.count_nonzero(count==1)),'nonmanifold_edges':int(np.count_nonzero(count>2)),'inconsistent_two_face_edges':int(np.count_nonzero((count==2)&(winding!=0))),'duplicate_faces':int(np.sum(duplicates-1)),'zero_area_faces':int(degenerate),'nonmanifold_vertex_links':bad_links,'components':components,'euler_characteristic':int(len(used)-len(unique)+len(f))}


def assess(vertices,faces):
    q,g,representative,inverse=exact_quotient(vertices,faces)
    v=np.asarray(vertices,dtype=np.float64);f=np.asarray(faces,dtype=np.int64)
    before=topology(v,f);after=topology(q,g)
    origin=(q.min(0)+q.max(0))/2
    m=trimesh.Trimesh(q-origin,g,process=False)
    formal=float(m.volume)
    forbidden=['boundary_edges','nonmanifold_edges','inconsistent_two_face_edges','duplicate_faces','zero_area_faces','nonmanifold_vertex_links']
    reasons=[k for k in forbidden if after[k]]
    if formal<=0:reasons.append('nonpositive_oriented_integral')
    if after['components']!=1:reasons.append('multiple_components_require_material_region_semantics')
    result={'before':before,'exact_quotient':after,'source_geometry_sha256':geometry_hash(v,f),'quotient_geometry_sha256':geometry_hash(q,g),'triangle_corner_sha256':sha(v[f].tobytes()),'ordered_triangle_corners_byte_identical':q[g].tobytes()==v[f].tobytes(),'no_added_removed_or_reordered_faces':len(g)==len(f),'bounds_m':[q.min(0).tolist(),q.max(0).tolist()],'formal_signed_surface_integral_m3':formal,'formal_integral_is_physical_volume':False,'eligibility':'WITHHELD_TOPOLOGY' if reasons else 'CLOSED_ORIENTED_GEOMETRIC_INTEGRAL_ONLY','withheld_reasons':reasons,'self_intersection':'NOT_RUN','inter_organ_overlap':'NOT_RUN','tissue_domain_semantics':'UNQUALIFIED','geometric_properties':None,'physical_mass_kg':None,'physical_inertia_kg_m2':None,'density_kg_per_m3':None}
    if not reasons:
        p=m.mass_properties
        result['geometric_properties']={'volume_m3':float(p['volume']),'volume_centroid_source_m':(np.asarray(p['center_mass'])+origin).tolist(),'inertia_per_density_m5_about_volume_centroid':np.asarray(p['inertia']).tolist(),'normalization':'Integral of squared distance over the oriented enclosed geometry; no physical density assigned.','scope':'Conditional on non-self-intersecting intended material-domain interpretation; not a total-organ or body-mass admission.'}
    return result,q,g,representative,inverse
