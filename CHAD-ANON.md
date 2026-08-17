# Anon Chad

A cross-model art jam for [`AlphaClaw/PHILOSOPHY.md`](https://github.com/PaulTiffany/AlphaClaw/blob/main/PHILOSOPHY.md).

The joke is simple: instead of copying a canonical Chad image, many models independently invent a new visual character for different lines of Chad Philosophy.

> **annoned by `model-id`**

No reference image is supplied. The models are explicitly instructed not to reproduce or closely imitate existing Chad/Wojak/GigaChad imagery, celebrities, logos, trademarked characters, or named artists' styles.

## Why SVG?

OpenRouter currently has free text models, but its dedicated image-generation catalog is not currently free. Text models can still draw vector art by emitting SVG source, so this experiment uses the same zero-price cross-model mechanics already used by the wheel and asks the models to draw with text.

The result is:

```text
philosophy line
      |
      v
free text model
      |
      v
original SVG source
      |
      v
mechanical sanitizer
      |
      +----> raw response + hashes + model receipt
      |
      v
sanitized SVG + caption
```

## Safety boundary

Generated SVG is untrusted model output until sanitized.

`anon_chad.py` rejects or strips active/external SVG features including scripts, links, external images, embedded raster data, event handlers, CSS, `foreignObject`, and unsupported tags/attributes. Only a small allowlist of basic vector geometry, paths, gradients, and text survives into the gallery.

Raw model responses are preserved separately and are **not** intended for direct browser embedding.

## Provenance

Every candidate records:

- philosophy section, line, and interpretation brief;
- requested and resolved model identity;
- prompt SHA-256;
- raw response SHA-256;
- sanitized SVG SHA-256 when sanitation succeeds;
- usage/error metadata;
- raw response and sanitized SVG filenames.

The generated `gallery.md` captions each surviving work as:

> *annoned by `model-id` via OpenRouter — original sanitized SVG, no reference image supplied.*

"annoned" is provenance, not a claim that the model is a legal person or copyright author.

## Rights boundary

Generation provenance and publication rights are separate questions.

OpenRouter's Terms of Service state that ownership rights in model outputs are governed by the applicable **Model Terms** for each model. Therefore the exact model identity is retained and a generated candidate should not be promoted into AlphaClaw merely because it passed SVG sanitation.

Current OpenRouter terms:

https://openrouter.ai/terms

For example, NVIDIA's current Nemotron/Open Model terms state that NVIDIA does not claim ownership of outputs generated using covered models. That is useful evidence for Nemotron candidates, but it is not generalized here to every model in the free pool.

NVIDIA Nemotron Open Model License:

https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-nemotron-open-model-license/

Before a candidate becomes published AlphaClaw art:

1. inspect the artwork;
2. verify its exact model's then-current output terms;
3. preserve the model attribution and generation receipt;
4. publish only the sanitized SVG;
5. do not claim exclusive human authorship merely because the repository contains the file.

## Run

Dry run: discover the free artists and show which line each gets, with no inference.

```bash
python3 anon_chad.py --dry-run --max-models 8
```

Live run:

```bash
OPENROUTER_API_KEY=... python3 anon_chad.py --max-models 8 --out-dir results/chad-anon
```

Or use **Actions → Anon Chad → Run workflow**. The workflow reuses the existing protected `inference` environment and `WHEEL_OPENROUTER_API_KEY` secret.

The result artifact contains `gallery.md`, `provenance.jsonl`, sanitized `svg/`, and raw `raw/` responses.
