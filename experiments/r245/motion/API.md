# Reusable activity intent v0.1

This is an original authored kinematic intent library. It does not establish realistic human motion. A native consumer solves the original rig, preserves its complete skin weights, exports actual observations, and submits those observations to independent critics.

## Minimal API

```python
from compiler import compile_clip, footwear_from_profile, compose_upper_body

# Measurements must follow morphology edits. Supply the source bind SHA and
# actual heel/forefoot/toe sole points plus the real toe-base joint pivot.
shoe = footwear_from_profile("stilettos", measured_morphology)
clip = compile_clip("walking", measured_morphology, shoe,
                    seed=24501, fps=24, duration_s=2.2)

brush = compile_clip("brushing_teeth", measured_morphology, shoe,
                     seed=24501, fps=24, duration_s=2.2)
composed = compose_upper_body(clip, brush, mask=("hands", "arms", "props"))
```

`example-morphology.json` is a **synthetic contract fixture**, not a measured adult. The native adapter must replace it with measured post-morph data. Shape, age labels, sex labels and style names do not imply weakness or a gendered gait. Measured proportions and explicit authored parameters determine targets.

## Inputs and frames

Coordinates use metres, +Y up and +Z forward, with +X on the model's left. The morphology requires `id`, `source_bind_sha256`, `stature_m`, `hip_center_m`, bilateral `hips_m`, `knees_m`, `ankles_m`, and bilateral `feet`. Each foot supplies `heel_from_ankle_m`, `forefoot_from_ankle_m`, `toe_from_ankle_m`, `toe_pivot_from_ankle_m`, and `width_m`. The first three are actual plantar support landmarks; the last vector is the actual skeletal toe-base pivot, not its ground projection. Optional shoulder width, thigh radius, clearance and measured head/mouth/wrist landmarks support task prototypes. Unknown physical input fields, nonfinite values, bool/string coordinates, unsupported pivot shifts and unreachable shoe geometry fail explicitly.

Footwear has separate heel and forefoot stack heights, heel and forefoot support width/length, and `toe_pivot_fraction=0` to retain the measured pivot. Profiles resolve dimensions from measured foot length/width. Platform forefoot height reduces pitch. Stiletto and block-heel support regions remain distinct even at equal pitch.

The compiler calibrates **fixed rest-frame outsole points**, then rotates those points rigidly with the foot. Shoe stack directions do not remain vertical during gait roll. Toe flexion is solved around the measured toe pivot for standing/toe-off support; swing interpolates its actual takeoff and landing values. `footwear_bindings` exposes these fixed points and the per-foot pitch axis for an independent consumer.

Each frame contains `time_s`, `source_time_s`, `phase`, `hip_center_m`, `root_orientation_xyzw`, bilateral `feet`, `hands_m`, `joint_intents`, `prop_contacts` and task `props`. A foot contains the desired `ankle_m`, world delta `rotation_xyzw`, `pitch_axis_unit`, actual target outsole `heel_m`/`forefoot_m`/`toe_m`, phase-authored heel/forefoot contact flags, contact reference, `toe_flexion_rad`, support footprints and a knee pole target. **These are desired targets, never observed FK.** Use `time_s` when baking; the last interval may be shorter when duration is not an integer number of frames.

For rig integration, apply the hip-center delta to the original rig root. Native IK resolves measured thigh/shank chains and ankle targets. The foot quaternion is a canonical world rotation delta applied to its measured rest frame. Toe flexion rotates about the same measured pitch axis at the actual toe-base pivot. Split deformation bones and all skin influences remain the consumer's preservation responsibility.

## Replay and composition

`definition` identifies the immutable library/activity versions and hashes. `instance` contains resolved morphology, footwear, timing, source bind hash and seed. The seed is provenance-only in this deterministic release; no random variation is claimed. The artifact saves definitions, resolved instances and baked intent frames separately.

Walking/jogging/running travel forward: stance contacts stay at fixed world anchors while the root advances. `loop.cycle_delta_m` states the per-cycle translation; replay adds it to the next cycle's root and contact targets. `start_time_s` provides deterministic seeking. Swing begins at the exact toe-off pose and ends at the next exact heel-strike pose; no foot-angle reset occurs at phase boundaries.

`sit_to_stand` is an implemented authored transition. Its pelvis stays on the authored seat through preparation and releases that contact before translating. Arbitrary contact-aware transition blending is explicitly unsupported. Upper-body composition accepts only hands, arms, spine and props; it preserves the base root and foot contacts and rejects target conflicts. Hand/prop prototypes use hip-relative world targets and still need actual dynamic head/mouth landmark and collision qualification in the consumer.

## Coverage and gates

Standing, sitting, crouching, squatting, walking, jogging and running have executable authored intent. Sit-to-stand is an additional transition. Showering, brushing teeth and eating an ice-cream cone have authored hand-task prototypes with explicit missing-contact/mechanics limits. Swimming and bathing remain planned because their stroke/root orientation or tub-contact kinematics are not implemented. Fluid simulation is a separate qualification question, not a prerequisite for authoring those motions.

`PASS_BOUNDED_INTENT_CONTRACT` covers deterministic replay, explicit unknown-input rejection, source/instance hashes, fixed shoe geometry, phase-boundary continuity, necessary target reachability, loop root deltas and masked composition. It does not mean a native consumer succeeded or that a motion is realistic. Actual joint range, foot penetration/slip, shoe rigid markers, body/prop contact, balance, appearance and temporal motion require independent observed evidence.
