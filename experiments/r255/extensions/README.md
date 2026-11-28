# R255 authored motion extension studies

Three independent public CPU packs contain twelve requested representative activities and a diagnostic pose sequence. All motion is original authored kinematics. Judo-inspired throwing and wrestling-inspired takedown use two independently bound actors. No motion is presented as captured human movement, a validated martial-arts technique, or simulated dynamics.

The source hierarchy, original inverse bind matrices, all three influence sets and all 13,380 source vertices per actor are preserved. Morphology is resolved before animation. The producer reuses only seven named function definitions from the immutable R246 consumer; its top-level producer is not executed. Separate two-link construction controls retain the original intermediate limb subdivisions. Saved Blender scenes and independently reimported GLBs are compared at every between-key midpoint and three full keys across all corresponding skin vertices. All native and GLB quaternion keys use a consistent hemisphere.

The geometric critic records source palm vertex proximity, original foot skin subset minima, whole-skin ground penetration, target residuals, limb length drift and intermediate-bone relative rotations. Failure remains visible and is distinct from transport success. Surface proximity is not contact force or anatomical acceptance; collision response, self-intersection and dynamic stability remain unqualified. A 10 cm heel/8 mm forefoot rigid support proxy has an explicitly authored heel detachment and response; it is not a fracture or physics model.

The diagnostic sequence preserves original rest/bind, then poses separate T/A references, shoulder elevation, elbow flexion, torso twist/flexion, hip/knee flexion, single-leg stance, squat, open hand and fist studies. Declared angles are test inputs, not physiological limits. The original source rest is never overwritten by a reference pose.

The public workflow uses pinned Blender 5.2.4 on standard `ubuntu-24.04` runners, no GPU and no paid cloud service. Each completed group emits its own gallery catalog, native scene/GLB per clip, actual CPU-rendered MP4 and contact sheet, source notices, transport/geometry observations and exact file manifest. Post-upload artifact identity is resolved by the independent immutable release lock rather than guessed inside its own upload.

## Explicit kinematic contact-fit correction

The immutable baseline is PR110 head `8693d0463ba8f23bcb5470ce8d4748d1ea02fe76`, public run `46166127034`. Its failures remain retained. The v2 child corrects wrestling role targets and grip timing, aligns cartwheel rotation with travel, and adds a bounded evaluated-geometry root/ankle fitting stage for the seven affected studies. It uses actual source palm vertices, stance-foot skin minima and whole-skin floor residuals. All original targets, fitted targets, individual iterations, root/ankle displacements, final residuals and foot-vertex drift/lift proxies are emitted. Thresholds are unchanged. This is kinematic geometric fitting, not contact forces, collision response or a dynamics simulation. It can introduce visible lift/slide, which remains measured and unaccepted. Source morphology, original rest transforms and all weights stay unchanged.

## Durable source replay

The frozen corrected producer is [PR115](https://github.com/SemperSupra/oneirifact/pull/115), head `53a49b7387cb01675f75cea10d8de15d89a09bac`, [public run 46168671427](https://github.com/SemperSupra/oneirifact/actions/runs/46168671427). This integration preserves the four original motion/solver files byte-for-byte. `source-closure.json` records those hashes. The former R246 helper path is now a local frozen vendor directory; its provenance pins both exact files and runtime checks their bytes before loading the seven allowed definitions. It does not require historical experiment branches to be merged.

The original three source cases are restored from the [published exact source package](https://github.com/SemperSupra/oneirifact/releases/download/motion-r255-source-inputs-v1/r255-source-bind-inputs-v1.zip). Its immutable input lock is `../source_input/input-lock.json`: 14,386,343 bytes, SHA256 `e369da7f5e2f10de8b0117ea8e8cbc4b700a00dfad0a784f713afba5df496e4f`, release asset `805385474`. Publication was performed by PR117 head `b7070b0e6732b4d1e110660703e7f3fc8a978bee` in run `46170638249`, before the later main merge. It was not a main-branch producer run. The source ZIP retains all original notices and complete selected preparation fixtures; no animated display file is stripped or reconstructed to stand in for source.

The `R255 durable source replay` workflow executes `exercise-dance` and `acrobatics-combat` in two public CPU jobs on changes to these source paths. This covers the single-actor and two-actor vendored paths. A manual dispatch selects one group, including the retained `support-events` group. There is no scheduled or automatic main-push production. Every replay receives a new run/attempt-based pack identity and does not replace the frozen v2 display products.

For a local replay, restore the published ZIP and use Blender 5.2.4:

```sh
python3 experiments/r255/source_input/prepare.py r255-source-bind-inputs-v1.zip inputs source-input-restore-receipt.json
SOURCE_HEAD_SHA="$(git rev-parse HEAD)" blender -b --factory-startup --threads 2 --python-exit-code 1 --python experiments/r255/extensions/produce.py -- inputs product exercise-dance
python3 experiments/r255/extensions/compare_replay.py product exercise-dance
cp source-input-restore-receipt.json product/
R255_PACK_REVISION=replay-local python3 experiments/r255/extensions/package.py product inputs exercise-dance
```

Media packaging requires Pillow 12.0.0 and the exact imageio-ffmpeg 0.6.0 Linux wheel/binary pinned in the workflow. The native producer uses Blender's bundled NumPy. The source restore verifies outer bytes, CRC, exact entry set, all 55 manifested original-entry hashes and each original bind hash. The producer then repeats saved-native and GLB all-skin replay at every between-key midpoint and three keys. This oracle covers skin vertices; it does not independently compare every rigid prop vertex.

`qualified-v2-metrics.json` contains actual frozen public product values and original receipt/GLB digests. `compare_replay.py` checks unchanged actor/source identity, scope, qualification and inventory, reports GLB byte identity separately, and compares scalar geometry metrics within 10 micrometres, angular drift within 1 microradian and root speed within 1 millimetre/second between repeat runs. These repeat tolerances do not modify the original 30 mm target/contact, -25 mm floor or 50 micrometre transport gates. A successful integration replay preserves the same held scientific status.

## Retained observed limits and next repair boundaries

The public v2 artifacts are reproducible research studies. They are not accepted as realistic human motion, correct martial-arts/exercise technique, load-bearing contact or simulated physics. The current evidence includes:

| Study | Retained finding |
|---|---|
| Slip | `FAIL_DIAGNOSTIC`: maximum IK target residual 30.503 mm, above the unchanged 30 mm gate. |
| Heel support loss | Whole-skin minimum remains 16.229 mm below the support plane. The detached heel is authored, with no fracture or dynamics solver. |
| Wrestling | Actual partner palm residual improves to 19.373 mm, but actor-a's fitted root offset resets by 222.853 mm between 2.208333 and 2.25 s at release. Maximum root speed is 5.35965 m/s. Partner separation and load transfer remain unqualified. |
| Push-up | Point residual is 3.442 micrometres, but the rendered hands appear cupped/palm-up. Independent palm orientation was not measured; a small point residual does not establish palm-down support. |
| Sit-up | The rendered pelvis remains raised, producing a bridge-like trunk flexion. A whole-skin floor minimum can be satisfied by the feet and does not prove pelvis/back support. |
| Cartwheel | Point residual is 1.087 micrometres, but the inverted pose has strongly bent arms and low head clearance. Technique and hand-to-foot load transfer are not accepted. |
| Diagnostic sequence | Discrete rig stress poses include abrupt transitions; the measured 9.768 m/s peak root speed is not presented as natural activity. Declared angles remain test inputs. |

Independent visual review inspected all 13 contact sheets (65 sparse poses) and two additional actual wrestling MP4 frames. It did not provide continuous video review, force measurement, full collision qualification or a new transport execution. These observations are retained as repair boundaries; this integration makes no new motion or threshold edits.
