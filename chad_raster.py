#!/usr/bin/env python3
"""Paid, bounded, cross-model raster art swarm for Chad Philosophy."""
from __future__ import annotations

import argparse, base64, hashlib, json, os, time, urllib.error, urllib.request
from pathlib import Path
from typing import Any

BASE = "https://openrouter.ai/api/v1"
DEFAULT_LINES = Path("chad_lines.json")
DEFAULT_OUT = Path("results/chad-raster")
EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

PUBLISHED_MODELS = {
    "bytedance-seed/seedream-4.5",
    "qwen/qwen-image-3",
    "x-ai/grok-imagine-image-2.0",
    "black-forest-labs/flux.2-pro",
    "bytedance-seed/seedream-5-0-pro",
    "qwen/qwen-image-3-pro",
    "recraft/recraft-v4",
    "black-forest-labs/flux.2-flex",
    "x-ai/grok-imagine-image-quality",
    "recraft/recraft-v4.1-utility",
    "recraft/recraft-v4-pro",
    "recraft/recraft-v4.1-pro",
    "recraft/recraft-v4.1-utility-pro",
    "openai/gpt-image-1-mini",
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image",
    "openai/gpt-image-2",
    "bytedance-seed/seedream-5-0-lite",
    "recraft/recraft-v4.1",
    "recraft/recraft-v3",
    "krea/krea-2-medium-turbo",
    "openai/gpt-5-image-mini",
    "google/gemini-3.1-flash-image-preview",
    "microsoft/mai-image-2.5",
    "krea/krea-2-medium",
    "krea/krea-2-large",
    "microsoft/mai-image-2.5-pro",
    "google/gemini-3-pro-image-preview",
    "openai/gpt-5.4-image-2",
    "openai/gpt-5-image",
    "black-forest-labs/flux.2-klein-4b",
}
HARD_BLOCKED_MODELS = {
    "sourceful/riverflow-v2-fast",
    "recraft/recraft-v4-vector",
}
REROLL_MODELS = {
    "black-forest-labs/flux.2-klein-4b",
    "recraft/recraft-v3",
    "bytedance-seed/seedream-5-0-lite",
    "black-forest-labs/flux.2-max",
    "recraft/recraft-v4.1",
}
EXCLUDED_MODELS = (PUBLISHED_MODELS - REROLL_MODELS) | HARD_BLOCKED_MODELS
EXCLUDED_AUTHORS = {"sourceful"}

# Conservative one-image planning ceilings for token-billed dedicated image
# endpoints. Requests use ~1K output where available and medium quality for
# OpenAI models. Actual provider-reported cost is recorded separately.
TOKEN_MODEL_ESTIMATES = {
    "google/gemini-2.5-flash-image": 0.06,
    "google/gemini-3.1-flash-lite-image": 0.06,
    "openai/gpt-image-1-mini": 0.08,
    "google/gemini-3.1-flash-image": 0.12,
    "openai/gpt-image-2": 0.18,
    "google/gemini-3-pro-image": 0.20,
    "openai/gpt-image-1": 0.22,
}


def headers() -> dict[str, str]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/PaulTiffany/letGPTsustakethewheel",
        "X-OpenRouter-Title": "Chad Philosophy Raster Swarm",
    }


def request(url: str, payload: dict[str, Any] | None = None, timeout: int = 240) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers(), method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def enum_values(params: dict[str, Any], key: str) -> list[str]:
    d = params.get(key) or {}
    return [str(v) for v in d.get("values", [])] if d.get("type") == "enum" else []


def desired_resolution(model_id: str, params: dict[str, Any]) -> str | None:
    resolutions = enum_values(params, "resolution")
    if "seedream" in model_id.lower():
        return "2K" if "2K" in resolutions else None
    return "1K" if "1K" in resolutions else None


def estimate_basis(endpoint: dict[str, Any], model_id: str) -> str | None:
    lines = [p for p in endpoint.get("pricing", []) if p.get("billable") == "output_image"]
    if any(p.get("unit") in {"image", "megapixel"} for p in lines):
        return "provider-image-pricing"
    if any(p.get("unit") == "token" for p in lines) and model_id in TOKEN_MODEL_ESTIMATES:
        return "manual-token-ceiling"
    return None


def cost_estimate(endpoint: dict[str, Any], model_id: str) -> float | None:
    """Conservative one-image planning estimate; actual usage is recorded later."""
    lines = [p for p in endpoint.get("pricing", []) if p.get("billable") == "output_image"]
    if not lines:
        return None

    fixed = [p for p in lines if p.get("unit") in {"image", "megapixel"}]
    if not fixed:
        if any(p.get("unit") == "token" for p in lines):
            return TOKEN_MODEL_ESTIMATES.get(model_id)
        return None

    params = endpoint.get("supported_parameters", {})
    target_res = desired_resolution(model_id, params)
    relevant = []
    for unit in ("image", "megapixel"):
        unit_lines = [p for p in fixed if p.get("unit") == unit]
        if not unit_lines:
            continue
        chosen = None
        if target_res:
            matches = [p for p in unit_lines if target_res.lower() in str(p.get("variant", "")).lower()]
            if matches:
                chosen = max(matches, key=lambda p: float(p.get("cost_usd", 0)))
        if chosen is None:
            plain = [p for p in unit_lines if not p.get("variant")]
            chosen = (
                max(plain, key=lambda p: float(p.get("cost_usd", 0)))
                if plain
                else min(unit_lines, key=lambda p: float(p.get("cost_usd", 0)))
            )
        amount = float(chosen.get("cost_usd", 0))
        if unit == "megapixel":
            amount *= 4.0 if target_res == "2K" else 1.25 if target_res == "1K" else 4.0
        relevant.append(amount)
    return sum(relevant) if relevant else None


def discover(max_per_image: float) -> list[dict[str, Any]]:
    try:
        ranked = request(f"{BASE}/models?output_modalities=image&sort=design-arena-elo-high-to-low").get("data", [])
    except Exception as e:
        print(f"census-rank-unavailable: {type(e).__name__}: {e}")
        ranked = []
    rank_map = {m.get("id"): i for i, m in enumerate(ranked, 1) if m.get("id")}

    # This catalog contains dedicated image-generation models. Per-endpoint
    # capability/pricing lives at /images/models/{model-id}/endpoints.
    catalog = [m for m in request(f"{BASE}/images/models").get("data", []) if m.get("id")]

    found = []
    skipped = 0
    for entry in catalog:
        mid = entry["id"]
        if mid in EXCLUDED_MODELS:
            continue
        author = mid.split("/", 1)[0]
        if author in EXCLUDED_AUTHORS or "vector" in mid.lower():
            continue

        eps_url = f"{BASE}/images/models/{mid}/endpoints"
        try:
            endpoint_rows = request(eps_url).get("endpoints", [])
        except Exception as e:
            print(f"census-skip {mid}: endpoint lookup {type(e).__name__}: {e}")
            skipped += 1
            continue

        best = None
        for ep in endpoint_rows:
            try:
                est = cost_estimate(ep, mid)
            except Exception as e:
                print(f"census-skip {mid}: pricing parse {type(e).__name__}: {e}")
                continue
            if not ep.get("provider_tag") or est is None or est <= 0 or est > max_per_image:
                continue
            if best is None or est < best[0]:
                best = (est, ep)

        if best:
            est, ep = best
            found.append({
                "model": mid,
                "name": entry.get("name", mid),
                "rank": rank_map.get(mid, 9999),
                "author": author,
                "provider_tag": ep["provider_tag"],
                "provider_name": ep.get("provider_name", ep["provider_tag"]),
                "params": ep.get("supported_parameters") or entry.get("supported_parameters", {}),
                "pricing": ep.get("pricing", []),
                "estimated_cost_usd": est,
                "estimate_basis": estimate_basis(ep, mid),
                "selection_kind": "reroll" if mid in REROLL_MODELS else "new",
            })

    found.sort(key=lambda c: (c["estimated_cost_usd"], c["rank"], c["model"]))
    print(f"census_candidates={len(found)} census_skipped={skipped}")
    return found


def choose_for_lines(
    candidates: list[dict[str, Any]],
    lines: list[dict[str, str]],
    count: int,
    budget: float,
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    """Prefer fresh model authors, then fresh repeats, then rerolls."""
    targets = lines[:count]
    by_model = {c["model"]: c for c in candidates}
    assigned: dict[int, dict[str, Any]] = {}
    used_models: set[str] = set()
    used_authors: set[str] = set()
    planned = 0.0

    for i, line in enumerate(targets):
        mid = line.get("preferred_model")
        c = by_model.get(mid) if mid else None
        if not c or c["model"] in used_models or planned + c["estimated_cost_usd"] > budget:
            continue
        assigned[i] = c
        used_models.add(c["model"])
        used_authors.add(c["author"])
        planned += c["estimated_cost_usd"]

    def fill(pool: list[dict[str, Any]], unique_author: bool) -> None:
        nonlocal planned
        for i in range(len(targets)):
            if i in assigned:
                continue
            for c in pool:
                if c["model"] in used_models:
                    continue
                if unique_author and c["author"] in used_authors:
                    continue
                if planned + c["estimated_cost_usd"] > budget:
                    continue
                assigned[i] = c
                used_models.add(c["model"])
                used_authors.add(c["author"])
                planned += c["estimated_cost_usd"]
                break

    fresh = [c for c in candidates if c["selection_kind"] == "new"]
    rerolls = [c for c in candidates if c["selection_kind"] == "reroll"]
    fill(fresh, True)
    fill(fresh, False)
    fill(rerolls, True)
    fill(rerolls, False)
    return [(targets[i], assigned[i]) for i in range(len(targets)) if i in assigned]


def art_prompt(line: dict[str, str]) -> str:
    prompt = (
        "Original raster art for Chad Philosophy. Focal character: handsome square-jawed adult man, strong neck and shoulders, "
        "relaxed posture, calm amused expression, completely unbothered; confident, never angry or domineering. "
        "Polished editorial cartoon, bold silhouette, portrait composition. Invent a new face, clothes, pose, and scene. "
        "Do not copy Chad/Wojak/GigaChad, a celebrity, copyrighted character, logo, or named artist style. No reference image. "
        "NO VISIBLE TEXT: no words, letters, numbers, captions, labels, signs, logos, or watermarks. "
        "Use one concrete physical metaphor, not an infographic. "
        f"Line: {line['line']} Scene: {line['brief']} "
        "Show the idea through action and composition."
    )
    if len(prompt) > 995:
        raise ValueError(f"art prompt unexpectedly too long: {len(prompt)}")
    return prompt


def payload_for(c: dict[str, Any], prompt: str) -> dict[str, Any]:
    p: dict[str, Any] = {
        "model": c["model"],
        "prompt": prompt,
        "n": 1,
        "provider": {"only": [c["provider_tag"]], "allow_fallbacks": False},
    }
    resolution = desired_resolution(c["model"], c["params"])
    if resolution:
        p["resolution"] = resolution

    ratios = enum_values(c["params"], "aspect_ratio")
    for ratio in ("4:5", "3:4", "2:3", "1:1"):
        if ratio in ratios:
            p["aspect_ratio"] = ratio
            break

    formats = [v.lower() for v in enum_values(c["params"], "output_format")]
    if "png" in formats:
        p["output_format"] = "png"

    qualities = [v.lower() for v in enum_values(c["params"], "quality")]
    if c["model"].startswith("openai/") and "medium" in qualities:
        p["quality"] = "medium"
    return p


def slug(s: str) -> str:
    return "-".join("".join(ch if ch.isalnum() else " " for ch in s.lower()).split())[:70]


def generate(c: dict[str, Any], prompt: str, timeout: int) -> dict[str, Any]:
    started = time.time()
    try:
        body = request(f"{BASE}/images", payload_for(c, prompt), timeout)
    except urllib.error.HTTPError as e:
        return {"error": {"status_code": e.code, "body": e.read().decode(errors="replace")[:2000]}}
    except Exception as e:
        return {"error": {"exception": type(e).__name__, "message": str(e)[:1000]}}
    data = body.get("data", [])
    if not data:
        return {"error": {"message": "no image data"}, "usage": body.get("usage")}
    media = data[0].get("media_type", "")
    if media not in EXT:
        return {"error": {"message": f"unsupported/non-raster media type {media!r}"}, "usage": body.get("usage")}
    try:
        raw = base64.b64decode(data[0]["b64_json"], validate=True)
    except Exception as e:
        return {"error": {"message": f"bad base64: {e}"}, "usage": body.get("usage")}
    if len(raw) < 10000:
        return {"error": {"message": f"suspiciously small image: {len(raw)} bytes"}, "usage": body.get("usage")}
    return {
        "error": None,
        "usage": body.get("usage"),
        "media_type": media,
        "bytes": raw,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=Path, default=DEFAULT_LINES)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-artists", type=int, default=12)
    ap.add_argument("--max-spend-usd", type=float, default=5.0)
    ap.add_argument("--max-per-image-usd", type=float, default=.5)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not 1 <= a.max_artists <= 12:
        raise ValueError("max artists must be 1..12")
    if not 0 < a.max_per_image_usd <= a.max_spend_usd:
        raise ValueError("invalid spend caps")

    lines = json.loads(a.lines.read_text())
    candidates = discover(a.max_per_image_usd)
    assignments = choose_for_lines(candidates, lines, min(a.max_artists, len(lines)), a.max_spend_usd)
    planned = sum(c["estimated_cost_usd"] for _, c in assignments)

    print(
        f"published_models={len(PUBLISHED_MODELS)} reroll_models={len(REROLL_MODELS)} "
        f"hard_blocked_models={len(HARD_BLOCKED_MODELS)} excluded_authors={sorted(EXCLUDED_AUTHORS)}"
    )
    print(f"targets={len(lines)} selected={len(assignments)} planned=${planned:.4f} total_cap=${a.max_spend_usd:.2f}")
    for i, (line, c) in enumerate(assignments, 1):
        resolution = desired_resolution(c["model"], c["params"]) or "provider-default"
        preferred = line.get("preferred_model") == c["model"]
        tag = "pinned-reroll" if preferred else c["selection_kind"]
        print(
            f"{i}. rank={c['rank']} kind={tag} {c['model']} via {c['provider_tag']} "
            f"res={resolution} est=${c['estimated_cost_usd']:.4f} basis={c['estimate_basis']} -> {line['line']}"
        )
    if a.dry_run:
        return 0
    if not assignments:
        raise RuntimeError("no image models fit predictable-cost caps")

    imgdir = a.out_dir / "images"
    imgdir.mkdir(parents=True, exist_ok=True)
    prov = a.out_dir / "provenance.jsonl"
    if prov.exists():
        raise FileExistsError(prov)

    rows, actual_total = [], 0.0
    for i, (line, c) in enumerate(assignments, 1):
        prompt = art_prompt(line)
        print(f"[{i}/{len(assignments)}] {c['model']} -> {line['id']}", flush=True)
        result = generate(c, prompt, a.timeout)
        usage = result.get("usage") or {}
        try:
            actual = float(usage["cost"]) if usage.get("cost") is not None else None
        except (TypeError, ValueError):
            actual = None
        if actual is not None:
            actual_total += actual

        row = {
            "schema_version": 4,
            "philosophy": line,
            **{k: c[k] for k in (
                "model", "name", "rank", "author", "provider_tag",
                "provider_name", "pricing", "estimated_cost_usd", "estimate_basis", "selection_kind"
            )},
            "preferred_model_matched": line.get("preferred_model") == c["model"],
            "requested_resolution": desired_resolution(c["model"], c["params"]),
            "actual_cost_usd": actual,
            "actual_cumulative_cost_usd": actual_total,
            "prompt": prompt,
            "prompt_chars": len(prompt),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "usage": usage,
            "reference_image_supplied": False,
            "visible_text_forbidden": True,
            "error": result.get("error"),
            "image_file": None,
            "image_sha256": None,
            "media_type": result.get("media_type"),
        }

        if not row["error"]:
            raw = result["bytes"]
            ext = EXT[result["media_type"]]
            name = f"{i:02d}-{slug(line['id'])}--{slug(c['model'])}{ext}"
            (imgdir / name).write_bytes(raw)
            row["image_file"] = name
            row["image_sha256"] = hashlib.sha256(raw).hexdigest()
            row["image_bytes"] = len(raw)

        with prov.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        rows.append(row)

        if actual_total >= a.max_spend_usd:
            print(f"reported cost reached ${actual_total:.4f}; stopping")
            break

    gallery = ["# Chad Philosophy — raster swarm", "", "Original generations; no reference image was supplied.", ""]
    for r in rows:
        if r["error"] or not r["image_file"]:
            continue
        line = r["philosophy"]
        gallery += [
            f"## {line['line']}", "",
            f"![{line['line']}](images/{r['image_file']})", "",
            f"*annoned by `{r['model']}` via `{r['provider_tag']}` — {r['selection_kind']} raster generation, no reference image supplied.*",
            "",
        ]
    (a.out_dir / "gallery.md").write_text("\n".join(gallery) + "\n")

    summary = {
        "selected": len(assignments),
        "attempted": len(rows),
        "successful": sum(not r["error"] and bool(r["image_file"]) for r in rows),
        "planned_estimated_cost_usd": planned,
        "reported_actual_cost_usd": actual_total,
        "max_spend_usd": a.max_spend_usd,
        "max_per_image_usd": a.max_per_image_usd,
        "rerolls_attempted": sum(r["selection_kind"] == "reroll" for r in rows),
        "fresh_models_attempted": sum(r["selection_kind"] == "new" for r in rows),
    }
    (a.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())