# Oneirifact

**Dreams Made Digital**

Oneirifact is a procedural 3D creation and exploration project. Its goal is to make editable, reusable designs accessible through a browser and richer local applications.

## Release status

The interactive browser preview is in preparation and is not yet available. This repository currently contains the public project showcase and its delivery checks, not the procedural engine. No product binaries or engine source are distributed at this stage.

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

Open `anatomy/` from the published site. The responsive read-only web tier uses the existing local Model Viewer dependency. It includes separate R222 reference layers, R223 female CT registration candidate, R225 pineal recovery and R226 identity and registration receipts. Default image mode avoids a 3D transfer until requested. Browser meshes are explicitly reduced display derivatives where needed; never substitute them for full reference or native editable source. Attribution and source archive digests are carried with the catalog. No medical, complete anatomy or native rig claim.

Rebuild with Python 3.12, NumPy 2.3.5, trimesh 4.6.8 and fast-simplification 0.1.13. Supply the six pinned, rights-cleared ZIPs named male, female, regional, pineal, identity and registration (see gallery/build_anatomy.py) in an input directory, then run `python gallery/build_anatomy.py INPUT_DIRECTORY` and the existing gallery/inspector builds. CI retrieves these versioned artifacts by ID, checks the SHA-256 of every input, and fails closed if they expire or differ. Original source artifacts remain separate from the deployed viewer. No credentials are required by the browser.
