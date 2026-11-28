# R257 exact display classification repair

The released viewer groups the exact male adrenal nodes `FJ3129` and `FJ3130`
under urinary and the female liver node
`hra_0382_VH_F_diaphragmatic_surface_of_liver` under respiratory. R254 documented
the errors; its audit output did not update the online layers.

This work moves those actual GLB nodes into the existing endocrine and digestive
layers. It also changes their inventory rows and the four affected model counts
and hashes in the catalog. Exact-ID overrides are wired into the original source
builder so a later raw-reference rebuild uses the same grouping.

## Exact scope

Input is the immutable `anatomy-display-r233-v3.zip`, SHA256
`d72fbb77b1b0603005131bbd387a36ce1c2c9965dfce13a30150a0f4b22d56be`.
Only seven of its eighty assets change: four GLBs, two inventories and the
catalog. The other forty-nine model files and all attribution/evidence assets
remain byte-identical. All 144 source nodes in the affected layers retain exact
position/index data, node transforms and material declarations. Existing colors
and historical material names are retained; color is not the category authority.

The result still has 53 models and seven datasets. The female digestive display
layer gains the original 12,448-triangle liver surface, increasing its display
triangle count to 102,420. No display geometry is reduced again to hide that
increase. Total corpus geometry is conserved.

The adapter accepts only the observed flat, identity-root, self-contained GLB
layout. It copies accessor bytes rather than loading and regenerating geometry.
Unexpected hierarchy, animation, texture or compression features fail closed.
This is a source-specific migration, not a general glTF scene editor.

## Evidence

The independent critic decodes the actual original and candidate packs without
calling the migration code. Eleven controlled corruptions must be rejected,
including metadata-only regrouping, moved vertices, changed triangle order,
changed transforms, duplicated/renamed identities and removed hold language.
Actual Chromium loads all four changed models; served GLB hashes/node sets and
the filtered UI inventories must agree. Four screenshots are retained.

No anatomical registration, real-organ morphology response, density, mass,
attachment, secondary motion or clinical capability is inferred. Original
unqualified reference and coupling limitations remain unchanged.

## Two-stage release

The first pull request leaves `gallery/anatomy-release-lock.json` at the existing
working release. Public PR jobs qualify the candidate. After review and merge,
the bounded main-only publisher creates `anatomy-display-r257-v4` once and
verifies anonymous exact readback. A subsequent small lock change activates that
already-present immutable pack. Concurrent navigation/runtime work is retained;
this change does not edit anatomy HTML or viewer JavaScript.
