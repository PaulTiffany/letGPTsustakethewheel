# letGPTsustakethewheel

![The screenshot being polled](assets/letGPTsustakethewheel.jpg)

A tiny cross-model opinion poll.

> **This is not an oracle. It is a variance machine.**

Same screenshot. Same question. Many concrete image-capable OpenRouter models. Preserve the disagreement instead of laundering it into fake consensus.

## The question

> **Choose for user Paul Carver Tiffany III. Which one menu action should he take?**

Each model must choose exactly one visible menu label, report confidence from 0–1, and give one short reason. The machine records the raw response and a parsed vote. **It never clicks anything.**

Allowed actions:

- `Save`
- `Copy link to post`
- `Embed this post`
- `Unfollow rUv.`
- `Not interested`
- `Seems like AI slop`
- `Report post`

## Selection contract

The default population is deliberately narrow:

- image input + text output;
- concrete model identity only — OpenRouter routers are excluded;
- zero price across prompt, completion, request, image, and internal-reasoning pricing;
- obvious specialist endpoints such as moderation/content-safety, Lyria, OCR, TTS, embeddings, and rerankers are excluded.

Paid models and specialist controls are available only as explicit **local CLI opt-ins**. The GitHub live workflow does not expose either opt-in.

Before model discovery or inference, the screenshot fixture is mechanically preflighted: it must be a non-tiny JPEG/PNG, its file signature must agree with its filename MIME type, and its byte count + SHA-256 are printed. The same fixture metadata is recorded in results.

## Run locally

Set an OpenRouter key:

```bash
export OPENROUTER_API_KEY='...'
```

Preflight the fixture and list the free concrete multimodal models without spending inference:

```bash
python wheel.py --max-models 12 --dry-run
```

Run the free-model poll:

```bash
python wheel.py --max-models 12 --out results/free-poll.jsonl
```

Explicit local-only opt-ins:

```bash
python wheel.py --allow-paid --max-models 12 --dry-run
python wheel.py --include-specialized --max-models 12 --dry-run
```

`wheel.py` uses only the Python standard library.

## GitHub Actions security

There is one workflow: **Survey the wheel**.

Dry-run/census jobs receive **no API secret**. A live poll:

- is owner-gated (`github.actor == github.repository_owner`);
- is capped to 4, 8, 12, or 20 concrete free models;
- makes one request per selected model with no retry loop;
- caps output at 160 tokens/model;
- runs under the protected GitHub Environment named `inference`;
- reads only the environment secret `WHEEL_OPENROUTER_API_KEY`;
- serializes live inference so two live polls cannot run concurrently.

### One-time protected-secret setup

1. Repository **Settings → Environments → New environment** → create `inference`.
2. Add **PaulTiffany** as a required reviewer. For a solo owner-operated workflow, leave “prevent self-review” disabled so the owner can approve their own run.
3. Add an **environment secret** named `WHEEL_OPENROUTER_API_KEY` containing a dedicated OpenRouter key.
4. Delete the old repository-level `OPENROUTER_API_KEY` from this repository.
5. On OpenRouter, give the dedicated key a very small spending limit/reset window as defense in depth even though this workflow selects only zero-priced models.

If the protected environment secret has not been configured, live inference fails closed.

## Output

The raw JSONL preserves, per model:

- requested and resolved model identity;
- fixture path, byte count, MIME, and SHA-256;
- whether the selected model was free/specialized under the local census;
- latency and usage reported by OpenRouter;
- the complete model response;
- parsed `action`, `confidence`, and `reason`;
- HTTP or parse failures without silently dropping them.

A sibling `.summary.json` contains the same fixture provenance, selection policy, and mechanical counts by action plus error/parse counts.

The histogram is descriptive. It is not a vote that gets to actuate the UI.

## Provenance

This is a visual sibling of [`levbench-openrouter`](https://github.com/PaulTiffany/levbench-openrouter), the earlier longevity consistency-mirror demo. The experiment is intentionally small: change the question, not the epistemic contract.
