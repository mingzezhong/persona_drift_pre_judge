# Complete Development experiment assets (v0)

This directory contains the first complete, runnable Persona/Topic data bank:

- 4 behavioral families × 6 Persona traits = 24 Personas;
- 2 prompt wordings and 96 disjoint evaluation statements per Persona;
- 12 shared-core + 24 family-specific Topics = 36 Topics;
- exactly 25 pressure-free, Persona-neutral moves per Topic = 900 moves;
- an outcome-blind 18 Development / 6 Calibration / 12 untouched Test split;
- six Development QA-pilot Topics and the exact Persona × Topic access matrix.

`development_asset_index_v0.json` is the hash-locked entry point. Run:

```bash
PYTHONPATH=src python scripts/build_development_assets.py --verify-only
```

These assets are authorized for Development-only exploratory experiments. They
were curated without target-model outputs, but the expedited selection used one
primary frontier-model curator instead of the planned independent multi-model
panel. Calibration and untouched Test outcomes must remain sealed. Independent
asset review and any resulting amendment are required before confirmatory use or
an ICLR claim.
