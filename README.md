# Oneirifact

**Dreams Made Digital**

Oneirifact is a procedural 3D creation and exploration project. Its goal is to make editable, reusable designs accessible through a browser and richer local applications.

## Release status

The read-only [Anatomy Explorer](https://sempersupra.github.io/oneirifact/anatomy/) reference preview and renderer showcase are available online. A separate adult morphology designer generates generic adult male and female exterior geometry locally from editable parameters. The native procedural editor is not yet released. This repository contains the public showcase and its delivery checks, not the procedural engine. No product binaries or engine source are distributed at this stage.

Verified releases will include supported features, limitations, build and test instructions, and applicable licensing notices.

## Reproduce the gallery

The gallery contains original standalone procedural studies, not private Oneirifact engine outputs. On a machine with Blender 5.2.4 LTS, run `python3 gallery/build_gallery.py /path/to/blender` from the repository root before serving the site. It produces six actual 720×480 CPU Cycles renders, matching editable Blender scenes, GLB mesh exports, and JSON receipts; verifies model hashes and mesh names and reopens the Blender files. The output directory must not already exist. The public qualification workflow builds and retains the gallery and publishes it with the static site. GLB omits the evaluation ground, lights and cameras; the Blender scene retains them. The two mechanical bearing variants are conceptual assembly studies, not validated engineering designs. No additional license grant is made by these studies.

## Run the project showcase locally

From a checkout of this repository, with Python 3.10 or newer:

```sh
python3 -m unittest discover -s tests -v
python3 -m http.server 8000 --directory site
```

Open http://localhost:8000/ in a browser. To exercise a real browser against a disposable local HTTP server, install Chromium or Google Chrome and run `python3 tests/smoke_site.py`. The smoke check exits nonzero if no supported browser is installed.

The public workflow checks the site and real browser navigation on a standard GitHub-hosted Linux runner. After successful qualification on the default branch, the workflow uploads the static site for GitHub Pages and attempts deployment when Pages is configured. The live-delivery verifier checks the expected asset bytes, origin and browser-relevant media types, including JavaScript modules and WebAssembly when those assets are present. No backend, account, or model service is required for this showcase.

## Feedback

Questions are welcome through the [issue tracker](https://github.com/SemperSupra/oneirifact/issues). Please do not include credentials, personal information, or confidential project files.

## Anatomy Explorer

Open `anatomy/` from the published site. The responsive read-only web tier uses the existing local Model Viewer dependency. It includes separate R222 reference layers, R223 female CT registration candidate, R225 pineal recovery, R226 identity and registration receipts, and separate historical female pelvic and grouped CT digit references. The grouped meshes remain unsegmented; they are not individual phalanx reconstructions. The 53 display models span seven datasets, including 16 individually selectable female mammary reference structures. Default image mode avoids a 3D transfer until requested. Browser meshes are explicitly reduced display derivatives where needed; never substitute them for full reference or native editable source. Attribution and source archive digests are carried with the catalog. No medical, complete anatomy or native rig claim.

For an exact display rebuild with Python 3.12+ and curl, run `python3 gallery/restore_anatomy_release.py` (fresh output directory). It retrieves the versioned public release locked by `gallery/anatomy-release-lock.json`, verifies the SHA-256 and every asset before restoring. An offline previously obtained exact pack can be supplied with `--source PATH`. CI uses this same restore path and browser tests; it no longer needs expiring upstream Actions artifacts for the anatomy display corpus. Raw reference generation is separate: `gallery/build_anatomy.py` with the six original pinned inputs and NumPy 2.3.5, trimesh 4.6.8, fast-simplification 0.1.13. No credentials are required by the browser.

## Adult morphology designer

Open [the browser designer](https://sempersupra.github.io/oneirifact/morph/) from the showcase or Anatomy Explorer. It includes male and female athletic presets, eleven shared regional controls, optional binary-only and advanced configuration, adult age-design, stature, mass-shape, muscularity, torso and spine flexion controls. Gender and presentation do not infer the selected internal anatomical configuration. All geometry generation is local to the browser. The age and mass controls are not clinical estimates. The exterior is not registered to or coupled to the internal atlas. Rebuild the exact qualified browser package using `python3 gallery/restore_adult_design_release.py`; the archive and every allowlisted file are verified before restoration. Source asset license is included.

## Motion Studio

Open [Motion Studio](https://sempersupra.github.io/oneirifact/motion/) for 30 actual motion products, 45 rendered previews and 153 named clip instances. The library includes stature/footwear cases, dense daily activities, aquatic prototypes, captured donor baselines and 13 authored studies of falls, support events, exercise, dance, acrobatics and paired combat movements. Image mode is the default; video and the original GLB load only when requested. The 3D player supports named clips, play/pause, exact time seeking, speed, optional looping, camera orbit and optional camera following. Original root motion is preserved.

The original bounded WebGL2 consumer retains all three `JOINTS_n`/`WEIGHTS_n` sets and all nine positive source influences. Qualification compares actual GPU transform-feedback positions against an independent Python double-precision evaluator for every skin and rigid-prop vertex at arbitrary times spanning every named clip, including both actors in paired scenes. Controlled omission of the ninth-influence buffer and corruption of an animated rigid support transform must fail. Actual browser video decoding, mobile layouts, keyboard controls, reduced-motion behavior and no-preload behavior have separate checks. This establishes replay within the measured envelope, not natural movement, contact, physical dynamics, clinical validity or organ coupling. Captured retarget quality remains held. Scene context omitted from each GLB is listed in the interface; the original `.blend` files remain available.

R255 contact dispositions remain literal in the browser: slip is `FAIL_DIAGNOSTIC`, all other new contact screens are `HOLD_GEOMETRIC_PROXIMITY_ONLY`, realism is `HOLD_AUTHORED_KINEMATICS`, and physics is `NOT_SIMULATED`. The interface shows measured endpoint errors, minimum skin height, fitting offsets and root speeds, with original observations and fitting/contact records downloadable. A successful replay cannot promote those held or failed scientific states. These movements are research studies, not validated exercise or martial-arts instruction.

Restore exact public assets with `python3 gallery/restore_motion_release.py`; it uses versioned release entries, whole ZIP hashes and per-file hashes, with optional `--source` for offline restore. Hosting-platform immutability is not assumed. Rebuild the independent numerical witness with the pinned `tests/motion-reference-requirements.txt`, then run `python3 tests/motion_reference.py site PATH` and `node tests/smoke_motion.mjs PATH`. Extension packs use `gallery/motion-schema.md` and independent release entries. No expiring Actions URL or account is required by the live page.
