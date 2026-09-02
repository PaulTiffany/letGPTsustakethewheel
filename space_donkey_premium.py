#!/usr/bin/env python3
"""Run SpaceDonkey prompts against explicitly pinned premium image models."""
import chad_raster


def space_donkey_prompt(line):
    return line["prompt"]


# This is a deliberate quality round, not the normal diversity rotation.
# Re-admit previously published models while preserving rights-review holds.
chad_raster.EXCLUDED_MODELS = set()
chad_raster.RECENTLY_ATTEMPTED_MODELS = set()
chad_raster.art_prompt = space_donkey_prompt
raise SystemExit(chad_raster.main())
