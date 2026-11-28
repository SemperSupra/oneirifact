# Source-compiled construction studies

Build three useful constructions from reusable, editable Oneirifact definitions:

| Construction | Definitions | Instances | Output |
|---|---:|---:|---|
| Studded-block bridge | 2 | 10 | Two three-course piers, spanning beam and parapets |
| Notched-beam cabin | 2 | 15 | Thirteen crossed beams and two pitched roof panels |
| Socketed tetrahedral frame | 5 | 10 | Six struts and four three-socket hubs |

These are original generic construction studies. They do not reproduce branded CAD or certify compatibility with commercial building toys. The log-inspired cabin uses a rectangular notched-beam profile. Bricks include underside cavities and tubes; connector plans describe nominal alignment and clearance.

## One-command replay

With Python 3.11+, OpenSCAD and Blender installed, run from the repository root:

```sh
python3 experiments/construction-recipes/build_compiled.py --output /tmp/construction-output
```

The output directory must not already exist, which prevents stale output from being reported as a new build. Use `--case brick_bridge`, `--case log_cabin` or `--case rod_hub_frame` for one study. Supply `--blender /path/to/blender` if Blender is not on `PATH`; `--no-render` builds and checks meshes only. OpenSCAD 2021.01 and Blender 4.3.2 were used for the local comparison; the public workflow obtains checksum-pinned Blender 5.2.4 and records the runner's OpenSCAD version. The two Blender versions are distinct execution subjects, not pixel-equivalence claims.

Each case produces individual binary STL meshes, independent mesh audit JSON, assembled and exploded PNGs, an editable `.blend`, a model-only GLB, executable logs, source hashes, named-instance metadata and a replay receipt. Floor, lights and camera are presentation context; they are excluded from the model-only GLB. Dimensional claims come from geometry and source checks, not pixels.

## What is executed

1. `generate.py` constructs canonical source graphs, component definitions, assembly layouts, connector plans, bill of materials and assembly order. It contains no alternate geometry evaluator.
2. The supplied `compiled/*/*/source-first.scad` programs were emitted by the existing Oneirifact source-first compiler. They are preserved outputs, rather than reimplemented Boolean code. `compiled-lock.json` records the public fixture and generated-program content hashes. Exact compiler provenance is retained in the private audit.
3. Each compiled program is tied to exact normalized `source.graph.json` bytes and its original adapter manifest. The manifests' `source_sha256` and `openscad_program_sha256` must match. Their original execution status describes compilation time; new execution evidence is recorded separately in replay receipts.
4. The builder regenerates the fixtures and compares their semantics. It also checks that the native-pinned `spec.json` keeps the same instance IDs, definitions and transforms as the editable candidate scene. Native definition hashes are preserved from the canonical engine; they are not invented by hashing pretty-printed JSON in another language.
5. OpenSCAD executes the nine programs to produce meshes. A separate STL reader checks directed edge incidence, boundary edges, winding, collapsed faces and positive signed volume.
6. `render_native.py --parts-directory` imports these actual component meshes and applies the preserved source instance transforms. Display materials and exploded-view offsets do not alter the construction geometry.
7. The builder independently reads back GLB instance IDs and source-binding metadata, PNG dimensions/IHDR checksums, and output receipt digests. A successful Blender exit alone is insufficient for the replay to pass.

The compiler's generated Blender boilerplate is not part of this package. Rendering uses the original standalone mesh-display script. No third-party toy meshes, LDraw parts or private source dependencies are required to replay these preserved studies.

## Verification and negative controls

```sh
python3 experiments/construction-recipes/build_compiled.py --verify-only
python3 -m unittest discover -s experiments/construction-recipes -p 'test_*.py' -v
python3 experiments/construction-recipes/verify.py experiments/construction-recipes/fixtures
```

The tests reject changed SCAD bytes, broken source-to-program binding, open or inconsistently oriented surfaces, overused edges, quantization-collapsed triangles and nonfinite coordinates. The assembly verifier checks stud lattices/course heights, notch axes and roof planes, strut endpoints/socket axes, bill of materials and unique occurrence identities. It rejects moved, duplicated and unexpectedly scaled instances in each study.

Binary STL stores float32 coordinates. The independent edge audit uses **exact decoded float32 positions**, with no additional tolerance-based welding, and rejects zero-area triangles. It separately reports minimum edge length and the number of faces that a **10-nanometre diagnostic grid** would collapse. The apex hub demonstrates why these must be separate: its very small exported sliver faces are topologically closed at the format's actual coordinates, while additional grid welding can create artificial non-manifold edges. That diagnostic is a numerical fragility warning, not a repair or a claim of nanometre shape accuracy. The checks do not establish self-intersection freedom, vertex-link manifoldness, material behavior or printability.

The evidence separates:

- Source validity, hashes and nominal construction layout.
- Successful execution of the actual compiler-emitted programs.
- Per-part exported mesh edge closure and orientation.
- Assembly rendering with preserved identities and transforms.
- Physical fit, insertion paths, friction, structural loads and manufacturing, which remain unqualified.

Native voxel output and OpenSCAD output are different evaluator products of the same source. This package does not claim their meshes are byte-identical or equally accurate. Native meshing fidelity is evaluated separately.

## Source changes and regeneration

Edit a generator or fixture to explore a new design, then regenerate canonical source. A changed graph requires recompilation through Oneirifact's existing source-first adapter before replacing its preserved SCAD and source-binding lock. The replay builder fails closed on changed artifacts; rewriting a lock does not itself qualify a design.

The GitHub Actions workflow runs three independent standard Ubuntu cases, capped at 15 minutes each, and retains their artifacts for 30 days. It performs no deployment.

This extends the original public [generic construction study](https://github.com/SemperSupra/oneirifact/blob/5babcc88696f9c1f1725c1109c29f0c4e40bb735/experiments/modular-construction/generate.py) with source-compatible definitions, useful builds, source/compiled-artifact bindings and independent assembly checks. The earlier independent field/marching-cubes generator is not used.
