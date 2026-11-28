# R249 native quaternion continuity audit

An observed aquatic development regression showed that adjacent stored `q` and
`-q` keys can agree at sampled frames yet disagree badly with sign-aligned GLB
interpolation between them. The approximately 0.65 m trigger measurement was a
local Blender 4.3.2 finding; this workcell measures the actual older public
aquatic artifacts independently on pinned Blender 5.2.4.

The bounded input set contains 15 existing ground/captured-motion products plus
two old aquatic negative controls: nine R245, two R248, four R247, and the two
controls. Three standard public CPU jobs download Blender once per group and do
no rendering. The middle group includes R248 and both controls.

`inputs.json` pins each artifact ID, ZIP size/SHA, producer head, native/GLB file
names and time mapping. Intake verifies ZIP SHA/CRC and every producer receipt
entry, then extracts only the native scene, GLB and original receipt for the
ephemeral audit. The output contains findings and custody records, not duplicate
product archives. The frozen R247 producer parent is
`025437f2a671ef37fec4b921ccc1d738ddb4fd34`; no producer branch is edited.

## Measurement

The actual saved 163-bone source-skin rig's actions are inspected. Quaternion
FCurves are grouped by bone/data path and all four component key times must
agree. Every negative adjacent dot retains the action, rig, bone, key frames,
raw WXYZ endpoint values, norms, normalized/raw dots and interpolation modes.
Captured-source armature actions are scanned separately as well.

A negative dot nominates an interval; it does not alone establish a geometry
defect. For each target interval inside the exported clip, the audit evaluates
the original saved skin at both endpoint keys and the exact midpoint. It then
imports the matching GLB animation independently, selects its exact NLA
track/action/slot, and evaluates the same times. Original mesh-position and
triangle-index hashes must agree before comparing all 13,380 corresponding
vertices. A confirmed defect requires both endpoints within the existing 50 µm
transport tolerance and a midpoint outside it. Endpoint mismatches are retained
as unresolved transport discrepancies instead of being attributed to signs.

R245/R248/aquatic native time is `frame = 1 + 24*t`. R247 native time is
`frame = 2 + t/0.0083333`; its publisher reference is outside the exported
capture. GLB evaluation uses the observed first action frame plus `fps*t`, with
`fps_base = 1` and 24 or 120 fps. Track matching is exact, so `walking` cannot
accidentally select `walking_brush`.

Captured-source actions have no exported source-skeleton GLB counterpart in
these artifacts. Their sign changes are preserved and explicitly marked as
unresolved in this audit; no counterpart comparison is invented. Reference-only
transitions outside the exported capture are also distinguished.

## Results and limits

The two older public aquatic inputs must reproduce an actual midpoint defect for
their negative-control checks to pass. A green job means the audit completed and
retained its findings, including negative results. Inputs with confirmed defects
remain held. An input with no sign changes gets only the bounded conclusion
`PASS_NO_ADJACENT_QUATERNION_SIGN_FLIPS_IN_SCANNED_NATIVE_ACTIONS`.
An R247 reference-only sign change before the published frame-2 start is retained
with its negative time and a distinct bounded pass for the published interval;
it is not silently counted as a captured-motion midpoint defect.

No native file is saved, repaired, retimed or overwritten. Before/after hashes
prove the selected scene and GLB bytes remain unchanged. Where needed, the next
minimal candidate is per-action/per-bone native quaternion hemisphere alignment
with all original key times and endpoint orientations preserved, followed by
the same adaptive midpoint comparisons. That repair is not performed here.

This audit does not establish general animation, contact, collision, physical
realism, anatomy or physiological acceptance.
