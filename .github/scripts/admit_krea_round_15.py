#!/usr/bin/env python3
from pathlib import Path
import re

p = Path('chad_raster.py')
s = p.read_text()

s = s.replace('TOKEN_MODEL_ESTIMATES', 'MANUAL_MODEL_ESTIMATES')

needle = '''    "microsoft/mai-image-2.5": 0.15,
    "microsoft/mai-image-2.5-pro": 0.18,
'''
replacement = '''    "microsoft/mai-image-2.5": 0.15,
    "microsoft/mai-image-2.5-pro": 0.18,
    # OpenRouter currently advertises Krea per-image prices; retain a manual
    # fallback because some endpoint pricing records are not parsed by the
    # generic output_image billable filter.
    "krea/krea-2-medium-turbo": 0.02,
    "krea/krea-2-medium": 0.04,
    "krea/krea-2-large": 0.07,
'''
if needle not in s:
    raise SystemExit('manual estimate insertion point not found')
s = s.replace(needle, replacement, 1)

old_basis = '''def estimate_basis(endpoint: dict[str, Any], model_id: str) -> str | None:
    lines = [p for p in endpoint.get("pricing", []) if p.get("billable") == "output_image"]
    if any(p.get("unit") in {"image", "megapixel"} for p in lines):
        return "provider-image-pricing"
    if any(p.get("unit") == "token" for p in lines) and model_id in MANUAL_MODEL_ESTIMATES:
        return "manual-token-ceiling"
    return None
'''
new_basis = '''def estimate_basis(endpoint: dict[str, Any], model_id: str) -> str | None:
    lines = [p for p in endpoint.get("pricing", []) if p.get("billable") == "output_image"]
    if any(p.get("unit") in {"image", "megapixel"} for p in lines):
        return "provider-image-pricing"
    if any(p.get("unit") == "token" for p in lines) and model_id in MANUAL_MODEL_ESTIMATES:
        return "manual-token-ceiling"
    if model_id in MANUAL_MODEL_ESTIMATES:
        return "manual-model-ceiling"
    return None
'''
if old_basis not in s:
    raise SystemExit('estimate_basis block not found')
s = s.replace(old_basis, new_basis, 1)

old_cost = '''    lines = [p for p in endpoint.get("pricing", []) if p.get("billable") == "output_image"]
    if not lines:
        return None

    fixed = [p for p in lines if p.get("unit") in {"image", "megapixel"}]
    if not fixed:
        if any(p.get("unit") == "token" for p in lines):
            return MANUAL_MODEL_ESTIMATES.get(model_id)
        return None
'''
new_cost = '''    lines = [p for p in endpoint.get("pricing", []) if p.get("billable") == "output_image"]
    if not lines:
        return MANUAL_MODEL_ESTIMATES.get(model_id)

    fixed = [p for p in lines if p.get("unit") in {"image", "megapixel"}]
    if not fixed:
        return MANUAL_MODEL_ESTIMATES.get(model_id)
'''
if old_cost not in s:
    raise SystemExit('cost_estimate prelude not found')
s = s.replace(old_cost, new_cost, 1)

p.write_text(s)
