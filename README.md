# Oneirifact

**Dreams Made Digital**

Oneirifact is a procedural 3D creation and exploration project. Its goal is to make editable, reusable designs accessible through a browser and richer local applications.

## Release status

The interactive browser preview is in preparation and is not yet available. This repository currently contains the public project showcase and its delivery checks, not the procedural engine. No product binaries or engine source are distributed at this stage.

Verified releases will include supported features, limitations, build and test instructions, and applicable licensing notices.

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
