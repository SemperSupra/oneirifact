# R245 media packaging recovery

The actual public Blender production passed its native, saved-scene and GLB replay checks. Four selected video cases then exposed a runner dependency omission: `ubuntu-24.04` had no system `ffmpeg` executable. Their complete original render frames and numerical evidence were retained by always-upload artifact handling.

This small child batch consumes those exact SHA256-pinned artifact archives. It validates ZIP CRC and every inner file listed in the original consumer receipt, preserves that receipt verbatim, and records separate producer and packaging heads/run IDs. The source models, scenes, numerical observations and intent remain unchanged.

The encoder dependency is the Linux x86_64 binary wheel for `imageio-ffmpeg==0.6.0`, SHA256 `c7e46fcec401dd990405049d2e2f475e2b397779df2519b544b8aab515195282`. The wheel is verified before installation, and the resolved bundled executable version and SHA256 are recorded. Its [official PyPI release metadata](https://pypi.org/project/imageio-ffmpeg/0.6.0/) identifies the platform-specific wheel and checksum. No encoder binary is redistributed in the product archive.

Each MP4 is fully decoded. Its frame count must equal the original rendered PNG sequence, duration must agree with 8 fps within a one-frame rounding bound, and first/middle/last decoded frames are compared with their corresponding original PNGs. Mean absolute color error is bounded by 8/255 per channel for this lossy preview format. A source-frame hash manifest is retained; the source archive remains the complete raw-frame authority. The existing six-panel review board is assembled from original stills.

This qualifies packaging of actual rendered evidence only. It does not change the motion realism hold or any native consumer qualification boundary.
