# Original parametric lantern production study

An original standalone native-Blender product-design study, not a release of the Oneirifact Foundry engine. No third-party models, textures, private source, or CPE. Two closed double-wall ribbed shade geometries, a shared product assembly and studio, three actual Cycles CPU views, editable native scenes and selected-object GLB exports. See designs.json for the controlled parameters. The verification checks image bytes, pixels, model container structure, part names and source/receipt hashes. It does not certify manufacturing or visual quality.

Run with official Blender 5.2.4 on a supported host:

```sh
blender --background --factory-startup --disable-autoexec --python-exit-code 1 -t 2 --python experiments/lantern/render.py -- /tmp/lantern-output
python3 -m pip install Pillow==11.3.0
python3 experiments/lantern/verify.py /tmp/lantern-output
```

Outputs are retained as a GitHub Actions artifact, separate from the released site.
