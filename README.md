# letGPTsustakethewheel

![The screenshot being polled](assets/letGPTsustakethewheel.jpg)

A tiny cross-model opinion poll.

> **This is not an oracle. It is a variance machine.**

Same screenshot. Same question. Many image-capable OpenRouter models. Preserve the disagreement instead of laundering it into fake consensus.

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

## Run it

Set an OpenRouter key locally:

```bash
export OPENROUTER_API_KEY='...'
```

Inspect which free image-capable models would be selected without spending inference:

```bash
python wheel.py --free-only --max-models 12 --dry-run
```

Run the poll:

```bash
python wheel.py --free-only --max-models 12 --out results/free-poll.jsonl
```

`wheel.py` uses only the Python standard library. No package install is required.

### GitHub Actions

The **Poll image models** workflow is `workflow_dispatch` only: pushes cannot spend inference. It defaults to free models, 12 calls maximum, one call per model, no retries, and a 160-token output cap per model.

Add one repository Actions secret named `OPENROUTER_API_KEY`, then run the workflow manually from the Actions tab.

## Output

The raw JSONL preserves, per model:

- requested and resolved model identity;
- latency and usage reported by OpenRouter;
- the complete model response;
- parsed `action`, `confidence`, and `reason`;
- HTTP or parse failures without silently dropping them.

A sibling `.summary.json` contains only mechanical counts by action plus error/parse counts.

The histogram is descriptive. It is not a vote that gets to actuate the UI.

## Provenance

This is a visual sibling of [`levbench-openrouter`](https://github.com/PaulTiffany/levbench-openrouter), the earlier longevity consistency-mirror demo. The experiment is intentionally small: change the question, not the epistemic contract.
