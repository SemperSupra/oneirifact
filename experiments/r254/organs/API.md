# R254 organ geometry and coupling status

This lane supplies measured source surfaces and conditional geometric integrals.
It does not supply a physical organ simulator or an anatomical registration to
the adult exterior. A closed surface and a volume are not a material, mass,
attachment, or deformation law.

The public inputs are frozen R222 BodyParts3D/HRA references and the exact shipped
R237 adult exterior package. Original vertices, ordered triangle corners,
source IDs, hierarchy, attribution and all source reference revisions remain
available. Exact index quotients are separate derived artifacts. No tolerance
weld, hole filling, source reflection, scaling, or containment fitting is used.

## Minimal callable API

```python
from geometry import assess
from contract import make_status, validate_status

properties, vertices, faces, source_representatives, index_map = assess(source_v, source_f)
status = make_status(atlas_identity, actual_morph_case, measured_source_records)
validate_status(status, atlas_identity, actual_morph_case, measured_source_records,
                mode="source_frame")
```

`assess` reports raw and exact-quotient topology. A single closed, consistently
oriented, nondegenerate edge/vertex manifold with positive oriented integral
can receive geometric volume, volume centroid and an inertia integral in m^5.
General self-intersection and intended material-domain semantics remain
unqualified. Open or malformed surfaces receive no such property payload.
The formal signed surface integral is diagnostic only and is never called
physical volume. Density, mass in kg and inertia in kg m^2 remain null.

The inertia integral is about the volume centroid. Multiplying it by an
independently supported uniform density would give inertia for that assumed
material distribution. No density is assigned to these organs. Layered,
heterogeneous and hollow tissues need their actual material regions; overlapping
organ components must not be summed as disjoint tissue or added to an already
total segment mass.

## Browser / model overlay contract

Each actual morphology case produces a `oneirifact.organ-coupling-status/v1`
record with an integrity digest and the exact exterior parameter revision,
exterior geometry hash and source-atlas identity. It contains every audited
source organ ID; this subset is not an anatomy completeness claim.

```json
{
  "schema": "oneirifact.organ-coupling-status/v1",
  "morphology_revision": "exact saved parameter bytes SHA256",
  "exterior_geometry_sha256": "actual evaluated visible positions SHA256",
  "registration": "UNAVAILABLE_FOR_THIS_EXTERIOR_REVISION",
  "overlay": {
    "allowed_modes": ["source_frame", "separate_panels"],
    "anatomical_overlay_allowed": false,
    "default_visible": false
  },
  "organs": [{
    "id": "exact source identifier",
    "reference_response": "UNCHANGED_SEPARATE_SOURCE_REFERENCE",
    "coupled_output_geometry_sha256": null,
    "parameter_propagation": "NOT_IMPLEMENTED",
    "pose_binding": "MISSING",
    "attachment_graph": "MISSING",
    "secondary_response": "NOT_IMPLEMENTED",
    "density_kg_per_m3": null,
    "mass_kg": null,
    "inertia_kg_m2": null
  }]
}
```

Do not place this geometry inside the changed exterior as though it were
registered. A source-frame view or clearly separate comparison panel is allowed.
Cached states with changed morphology, missing organ IDs, altered source data,
mirrored/stretched/misplaced reference transforms, or invented physical values
are rejected. A shape parameter that moves the exterior does not imply that its
source atlas reference has responded.

## Physical layer prerequisites

A later physical layer needs a qualified source-to-body registration at the
selected morphology; disjoint material-domain and mass accounting; density
provenance and uncertainty; organ/fascia/ligament attachment and sliding/contact
conditions; suitable volume meshes; constitutive laws with regime and units;
and an admitted solver with gravity, inertia, damping and timestep evidence.
Pose-driven kinematic following and physical secondary response are separate.
Use established solver adapters, not a new complex solver. Source organ identity
must survive every transfer.

MuJoCo's official inertial/geometry distinction is useful architecture guidance:
body mass, center of mass and inertia are distinct from display/collision
geometry. Its deformable flex facilities are a separate representation, not an
automatic property of a rendered surface.

- https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-inertial
- https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-geom
- https://mujoco.readthedocs.io/en/stable/XMLreference.html#deformable-flex
- https://trimesh.org/trimesh.base.html#trimesh.base.Trimesh.mass_properties

The actual integrator used here is pinned trimesh 4.6.8, cross-checked by an
independent signed-tetrahedron moment formula and analytic controls. This is a
geometry qualification only, not a solver or tissue qualification.
