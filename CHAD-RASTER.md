# Raster Chad

The SVG experiment proved the distribution idea but missed the visual mode.

This is the replacement: **actual image-generation models independently create original Chad-like raster art for different lines of `AlphaClaw/PHILOSOPHY.md`.**

> *annoned by `model-id`*

No source image is supplied. Each image model receives only the philosophy line, a scene brief, and a textual description of the broad cultural archetype: absurdly handsome, square-jawed, relaxed, self-possessed, slightly amused, and impossible to embarrass.

The prompt explicitly requires a new face, hair, clothes, pose, composition, and visual language, and forbids close reproduction of specific Yes Chad / Nordic Gamer / Wojak / Virgin-vs-Chad drawings, GigaChad photography, celebrities, copyrighted characters, logos, or named artists' styles.

## Why real image generation

Text models drawing SVG were mechanically interesting but too far from the visual mode we were trying to ground. The active experiment therefore uses OpenRouter's dedicated Image API and accepts only raster outputs (PNG, JPEG, or WebP).

OpenRouter Image API documentation:

https://openrouter.ai/docs/guides/overview/multimodal/image-generation

## Selection contract

The runner does **not** simply choose the cheapest image models.

It asks OpenRouter for current image-output models sorted by **Design Arena ELO**, then:

1. intersects that ranking with the dedicated image-generation catalog;
2. inspects live provider endpoint pricing;
3. excludes token-billed image outputs whose cost cannot be bounded predictably by this runner;
4. rejects any endpoint above the requested per-image ceiling;
5. prefers one model from each image-model author/lab before taking a second model from the same author;
6. refuses a planned set whose conservative estimated cost exceeds the whole-run ceiling.

The model list is therefore allowed to drift as the image field changes. The exact selected model, provider, price quote, rank, prompt, image hash, and reported generation cost are preserved for every attempt.

## Default budget

The workflow defaults to:

- 6 model-artists;
- $1.00 maximum planned spend for the run;
- $0.15 maximum predictable cost for any one generated image;
- one image per artist;
- 1K output when the chosen endpoint supports that normalized tier;
- 4:5 portrait composition when supported, otherwise 1:1 when available.

A dry run performs discovery and prints the selected artists and planned spend without generating art.

Failed image generations are recorded as failures. The runner does not silently replace their model identity with a fallback provider.

## Output

A successful run uploads `chad-raster-art`, containing:

```text
results/chad-raster/
├── gallery.md
├── provenance.jsonl
├── summary.json
└── images/
    ├── 01-...png
    ├── 02-...webp
    └── ...
```

Every gallery caption names the exact model and serving provider:

> *annoned by `model-id` via `provider-tag` — original raster generation, no reference image supplied.*

## Provenance and rights

Generation provenance and publication rights remain separate questions.

The runner proves which model/provider produced which bytes from which prompt, and records that no reference image was supplied. Before a generated work is promoted into AlphaClaw, its exact model's then-current output terms should still be checked and the model caption retained.

The images are not represented as human-drawn merely because a human curated or published them.

## Run

Use **Actions → Raster Chad → Run workflow**.

A good first real run is:

- `dry_run`: **false**
- `max_artists`: **6**
- `max_spend_usd`: **1.00**
- `max_per_image_usd`: **0.15**

If the model discovery selects fewer than six artists, raise the per-image ceiling before raising the whole-run ceiling. If the art is visually weak, increase the per-image ceiling so higher-ranked image models become eligible rather than merely increasing the number of cheap images.
