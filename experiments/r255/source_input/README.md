# Exact R255 source inputs

`pack.py` verifies upstream public artifact `15266855834` against SHA256 `e694ab4d06bae33bf829e624d03a2bd81bb28d8b8059c42ae83e36819f33dd68`, checks its CRC, producer identity and every selected source file, and preserves the original bytes for `male155flat`, `female155flat` and `female185flat`.

The package contains all 54 original files for those cases, including the original `bound-source.glb`, case and compiler fixture JSON, negative fixtures, source notices and images. It also retains the exact upstream receipt and adds a separate per-file source-input manifest. It does not reconstruct a source bind by modifying an animated display model.

The deterministic stored ZIP has 56 entries, 14,386,343 bytes and SHA256 `e369da7f5e2f10de8b0117ea8e8cbc4b700a00dfad0a784f713afba5df496e4f`. Fixed timestamps and file modes plus `ZIP_STORED` avoid dependence on compression-library versions. The bounded public publication workflow rebuilds, verifies and publishes this exact archive, then downloads the published asset and checks its bytes again. An existing versioned asset is verified; it is never overwritten.

Publication is a separate prerequisite. A subsequent replay integration pins the observed public release URL and digest. This source-input package is not loaded by the browser display packs, and this prerequisite does not activate a site change or alter existing products.
