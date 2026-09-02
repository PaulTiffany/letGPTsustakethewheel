#!/usr/bin/env python3
"""Use Raster Chad's model census/provenance machinery with SpaceDonkey prompts."""
import chad_raster


def space_donkey_prompt(line):
    return line["prompt"]


chad_raster.art_prompt = space_donkey_prompt
raise SystemExit(chad_raster.main())
