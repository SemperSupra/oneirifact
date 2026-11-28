# Motion browser package contract v1

One versioned, SHA-256-pinned asset ZIP contains `catalog.json`, package directories and a canonical `pack-manifest.json`. All paths are relative to that ZIP; the browser resolves them against the versioned pack directory. Project policy preserves old package IDs and release bytes: a new revision uses a new pack ID and release tag. The lock detects changed bytes; it does not assume that the hosting platform enforces release immutability.

The catalog schema is `oneirifact.motion-browser/v1`, with `pack_id`, `title`, `packages` and `scope`. Each package has:

- `id`: stable lowercase letters, digits and hyphens; unique within the pack.
- `title`, `group` and `source_kind` (`authored` or `captured`).
- `actors`: one or more objects with `id`, `sex_variant`, `stature_m`, `morphology_label`, `footwear` and `source_bind_sha256`. Source labels do not infer age-related capability.
- `clips`: nonempty list of `{id,title,animation_name,duration_s,evaluation,preview}`. The exact `animation_name` must exist in the GLB. `preview` is null or `{path,bytes,sha256,fps,frames,duration_s}`. A lower-rate MP4 is distinct from native animation cadence.
- `assets`: `model`, `native_scene`, `poster`, `contact_sheet`, `receipt` and `rights`, each `{path,bytes,sha256}`. The native scene and model are exact source files, not silent reduced display derivatives. A poster may be one actual original render; the contact sheet may be the same file if appropriate.
- `provenance`: public repository, exact producer head/run, provider artifact ID/bytes/SHA256, source revision and source notices. No private DLE records, Library links, account identifiers or controller filesystem paths.
- `qualification`: explicit `transport`, `realism`, `contact`, `physics` and `retarget` states. Prototypes remain held where applicable; provider success is not blanket qualification.
- `included_layers`, `omitted_layers` and `notes`: explicit source/consumer scope. Native/render-only props must not be implied present in the GLB.
- `model_inventory`: mesh/skin/joint counts, preserved weight sets and maximum positive influences, generated from the exact GLB.

Optional `assets.evidence` and top-level `evidence` lists contain additional `{path,bytes,sha256,title}` references. Every retained diagnostic or producer record remains covered by the canonical file manifest. A normalized display catalog may coexist with a byte-identical `producer-catalog.json`; the normalization receipt records that rename and every preserved source entry.

Optional `measured_limits` contains a source-receipt reference, scope and the original recorded metrics. These are diagnostics rather than accepted physical tolerances. Display normalization preserves every producer qualification value exactly, including `FAIL_DIAGNOSTIC` and `HOLD_GEOMETRIC_PROXIMITY_ONLY`; a passing geometry transport result cannot promote contact, physics, realism or technique. Original authored R255 studies use `HOLD_AUTHORED_KINEMATICS` for realism.

The original bounded browser consumes self-contained glTF 2.0 GLBs with triangle meshes, node matrices/TRS, up to three complete `JOINTS_n`/`WEIGHTS_n` sets (12 available slots, currently at most 9 positive influences), multiple skins/actors, and named LINEAR/STEP translation, rotation and scale channels. All sets are preserved. Unsupported compression, external buffers, morph targets or other required extensions are explicit errors; never truncate influences or quietly substitute a static pose. Root motion remains in the model. Camera following is a view choice, not a geometry transformation.

Native .blend, actual MP4, original notices and producer receipts remain downloadable even when browser 3D is unavailable. Additional styles/activities may ship as independently pinned packs. Physics, technique, contact and realism acceptance require their own evidence and do not follow from model loading.

The independent release lock lists each versioned tag/asset, whole-archive SHA256, exact file inventory counts and byte budget. Restore verifies the archive and every inner file before placing it under `site/motion/data/<pack_id>/`. The live browser needs no account and no temporary workflow artifact URL.
