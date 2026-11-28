# R248 dense daily and fitness activity products

This two-case public CPU child extends the frozen R245 consumer at
`7fc8141fef8e2133ecceb2474005e82da4da69ad`. It retains the same original authored
activity definitions and full-weight 163-bone source adapters. No main merge or
native Oneirifact integration is implied.

## Actual work

- Evaluate every authored 24 fps frame for all twelve ground activity/composition
  entries, including previously sparse sitting, crouching, jogging, running,
  showering and eating-ice-cream prototypes.
- Compare native evaluation, reopened Blender actions and reimported GLB, with
  two fractional replay probes for each entry and rigid bone-parented footwear.
- Produce six short actual CPU-rendered videos per case: sit-to-stand, crouching,
  jogging, running, showering and ice-cream cone. Cases are `female155flat` and the
  actual nonuniform donor `maleolderflat`.
- Add original native/render-only cone and shower context geometry. The cone is
  wrist-parented with an explicit authored fixed wrist orientation; its evaluated
  scoop-tip-to-mouth-proxy distance is measured. The shower uses a measured scene
  head position and fixed thin context lines. Those lines are not simulated water.
- Use the exact imageio-ffmpeg 0.6.0 wheel and encoder binary already qualified in
  R245 media recovery; independently decode all video frames, compare counts and
  duration, and check first/middle/last lossy image samples against source PNGs.

## Interpretation and reuse

The source `.blend` retains twelve named source-rig actions; select the source
armature and an action in the Action Editor to replay. Props have activity-specific
visibility set by the authoring/render helper; when switching actions manually,
show the matching named prop and hide irrelevant props. The packed GLB preserves
the source body, full weights, bones and shoe attachments, with named animation
clips. Per-activity prop visibility is intentionally native/render-only and is
not encoded in GLB.

The editable definition/instance remains the frozen R245 API. Regenerate measured
morphology/bind inputs before compiling after shape changes. This child adds
sampling and presentation evidence; it does not expand the definition's semantic
scope or admit arbitrary contact-aware transitions.

Actual observations feed the independent R245 critic. Report its failures
separately from transport/video success. Full 24 fps sampling strengthens coverage
but does not prove behavior at every continuous time, physiological joint ranges,
balance, dynamics, collision, realistic motion, oral contact, finger grip, food
deformation or water mechanics. All those acceptance states remain unqualified.

The user asked for realistic reusable daily/fitness motion. These products are
intermediate inspectable authored prototypes; measured-motion work remains a
separate evidence lane.
