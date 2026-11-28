# R246 aquatic activity intent, version 0.1.0

This child extends activity coverage without changing the frozen R245 compiler,
its execution receipt, or the separate land-motion consumer. It implements two
original **authored kinematic prototypes**: front crawl and tub-seated chest
washing. Definitions, resolved instances, targets, observations and qualification
remain separate. Fluid simulation is not a prerequisite for these motions.

## Minimal callable API

```python
import compiler  # experiments/r246/aquatic/compiler.py

activity = "swimming_front_crawl"  # or "bathing_seated_wash"
shoe = compiler.barefoot(morphology)
context = compiler.context_from_template(activity, morphology)
clip = compiler.compile_clip(
    activity, morphology, shoe, context,
    limb_measurements=measurements,
    seed=24601, fps=24, duration_s=None, start_time_s=0.0,
)
```

`morphology` is the unchanged R245 post-morph measurement contract. `measure.py`
reads the **actual generated GLB** and adds rest-world shoulder, elbow and wrist
anchors and segment lengths, an existing chest skin vertex ID and coordinate,
the source position-buffer digest and the same source-bind SHA256. It verifies
arm and leg anchors against the source bind. No source geometry, rig, triangles,
or skin influences are edited by this workcell.

The source preparation dependency is exact public PR99 commit
`7fc8141fef8e2133ecceb2474005e82da4da69ad`, specifically
`experiments/r245/consumer/prepare.py` and `gltf.py`. Inputs are R239 artifact
15260769266, archive SHA256
`f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f`,
and R235 artifact 15258079477, archive SHA256
`025145c2af4dc0c0d8936e764b88dd03a06a9e389197cadf97eb9b1d634d54fc`.

### Arm measurement object

```json
{
  "schema": "oneirifact.aquatic-source-measurements/v1",
  "source_bind_sha256": "<same exact GLB hash as morphology>",
  "arms": {
    "L": {
      "shoulder_m": [0.17, 1.24, 0.015],
      "elbow_m": [0.30, 1.06, 0.04],
      "wrist_m": [0.44, 0.95, 0.18],
      "upper_m": 0.22388613177352378,
      "lower_m": 0.2264950330581225
    },
    "R": {"<measured values required>": "not a mirror or demographic inference"}
  },
  "chest_surface_anchor_m": [0.0, 1.10, 0.12],
  "chest_source_vertex_id": 0,
  "source_mesh_position_sha256": "<actual position-buffer hash>",
  "bone_node_ids": {},
  "method": "<actual measurement receipt>"
}
```

This schematic object illustrates field names only. Executable, numerically
consistent JSON inputs are produced by `measure.py` and retained in every
artifact case. A caller must supply actual measured left and right limbs.

## Coordinates and target reference semantics

Canonical coordinates remain metres, +Y world up, +Z travel, +X left, with xyzw
quaternions. `root_orientation_xyzw` is a world delta applied to measured rest
offsets about `hip_center_m`. **Rotate the hip and shoulder offsets**, then add
the translated hip center. A translation-only R245 reach calculation is invalid
for prone swimming. The new critic includes an intentionally unrotated negative.

Every frame contains already resolved world positions:

| Field | Meaning |
| --- | --- |
| `hip_center_m`, `root_orientation_xyzw` | Desired body root translation and world rotation delta |
| `body_anchors.hips_m`, `body_anchors.shoulders_m` | Source bind anchors rotated and translated by the intended root |
| `body_anchors.head_m`, `mouth_m` | Root-transformed rest anchor references; they are not observations after neck/head pose |
| `body_anchors.chest_surface_anchor_m` | Root-transformed measured skin vertex reference; native consumer must also observe the actual deformed vertex |
| `hands_m` | Resolved world wrist positions for the two-link consumer |
| `hand_targets[side].reference` | Explicit original reference: `world`, `world:tub:rim` or `body:chest_surface_anchor` |
| `hand_targets[side].offset_m` | Body-relative offset for washing, already resolved into `position_m`/`hands_m` |
| `arm_poles[side]` | World-space elbow pole position and explicit `reference: world` |
| `feet[side].rotation_xyzw` | World delta for measured rest foot offsets; no geometry scale |
| `feet[side].knee_pole_m` | World-space knee pole |
| `joint_intents.head_orientation_xyzw` | Intended world head rotation delta; actual neck/head motion must be measured |

**Do not translate resolved world hands toward a posed mouth or head.** That
adapter was specific to the R245 hand tasks. Swimming hand paths are anchored to
the water surface and moving shoulders. Bathing has one explicit stationary rim
target and one body-relative chest target. A native adapter may evaluate the
chest vertex after pose, but must record the original target, resulting actual
vertex and actual hand/sponge independently; it must not echo a target as an
observation or conceal a retargeting offset.

## Implemented motion and context

Front crawl uses a horizontal root, periodic body roll, alternating underwater
pull and above-surface recovery wrist paths, three flutter cycles per arm cycle,
and a smooth head-turn breathing-intent window. The head turn is not evidence
that an airway clears the surface. Every foot contact flag is false, every
support-region list is empty, and water is context, not a ground-support claim.
The root advances at the explicit context speed. Its loop cycle delta is
`[0, 0, speed * period]`; world water context does not translate with the root.

Bathing is a seated chest-washing loop with a sponge. The context explicitly
specifies interior width/length, floor, rim, seat center/width/depth, and rim
hand location. The source-scaled legs target the bounded tub floor. The pelvis
has a seat-support intent and the other hand a rim-support intent. These are
**authored targets**, with `contact_verified: false`. Tub entry/exit and
land-to-water transitions are unsupported. Do not apply an arbitrary blend and
claim those transitions implemented.

Standalone resolved contexts are exported for each clip. The template ratios
are original authoring choices, not ergonomic or physiological standards.
Callers may provide an explicit context, but unknown physical parameters and
wrong context kinds reject. Deliberately unreachable contexts emit diagnostic
targets with `reach_distance_screen: FAIL`; the compiler never changes source
segment lengths or silently substitutes a trajectory. Consumers should refuse
to emit a qualified pose from those failed cases.

Only explicitly measured **barefoot** geometry is supported in this aquatic
version. Requests for flats, stilettos, fins, or other aquatic footwear reject.
The nine source-case names originate in the R245 footwear matrix; they represent
five unique body binds, all explicitly rebound to barefoot here. No shoe-profile
qualification transfers to aquatic motion.

## Replay, checks and product

The default clips are two 2.4-second front-crawl cycles and two 3.2-second washing
cycles at 24 Hz. The last interval may be shorter than `1/fps`; use `time_s`.
Absolute `start_time_s` gives deterministic seek. The seed is recorded but no
random process is used. Definition, instance and complete clip hashes are
separate. Frozen core, source preparer and source artifacts are pinned.

The bounded critic checks source-rotated anchors, necessary two-link reach,
selected context geometry, one-sided motion boundaries, complete target and
orientation loops including toes and props, root delta, deterministic replay,
seek and explicit contact references. Controls include a 10 mm discontinuity,
unrotated source anchors, unreachable surface wrists and tub rim, a water bottom
intersecting foot targets, false segment length and unsupported shoe/context
inputs. Negative clips are retained as evidence, not silently discarded.

The public CPU artifact includes 18 clips from nine cases, separate definitions
and instances, standalone contexts, source-bound measurement JSON, unchanged
full-weight bind GLBs, negative examples, receipts and clearly labelled target
figures. The figure chords are **not solved limb geometry**. Native Blender
pose/reimport, observed skin/prop contacts, joint limits, balance, airway
clearance, realism and optional physics remain separate qualification work.
