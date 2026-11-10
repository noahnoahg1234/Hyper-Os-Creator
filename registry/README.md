# Hyper OS Creator registry

This folder is the community resource registry. Hyper OS Creator reads
`index.json` from here (over GitHub) and also uses this folder as an offline
starter pack.

To add a resource:

1. Make a `.hyperpkg` in the app (Resources → Publish → "Just download the package")
   or with `hyperos resources create` / `hyperos resources pack`.
2. Copy it into `packages/`.
3. Run `python tools/build_registry.py` to update `index.json`.
4. Open a pull request.
