#!/usr/bin/env python3
"""Paid, bounded, cross-model raster art swarm for Chad Philosophy."""
from __future__ import annotations

import argparse, base64, hashlib, json, os, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

BASE = "https://openrouter.ai/api/v1"
ORIGIN = "https://openrouter.ai"
DEFAULT_LINES = Path("chad_lines.json")
DEFAULT_OUT = Path("results/chad-raster")
EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def headers() -> dict[str, str]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/PaulTiffany/letGPTsustakethewheel",
            "X-OpenRouter-Title": "Chad Philosophy Raster Swarm"}


def request(url: str, payload: dict[str, Any] | None = None, timeout: int = 240) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers(), method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def enum_values(params: dict[str, Any], key: str) -> list[str]:
    d = params.get(key) or {}
    return [str(v) for v in d.get("values", [])] if d.get("type") == "enum" else []


def cost_estimate(endpoint: dict[str, Any]) -> float | None:
    """Conservative 1K one-image estimate; skip token-billed outputs."""
    lines = [p for p in endpoint.get("pricing", []) if p.get("billable") == "output_image"]
    if not lines or any(p.get("unit") == "token" for p in lines):
        return None
    relevant = []
    for unit in ("image", "megapixel"):
        u = [p for p in lines if p.get("unit") == unit]
        if not u:
            continue
        one_k = [p for p in u if "1k" in str(p.get("variant", "")).lower()]
        chosen = max(one_k or [p for p in u if not p.get("variant")] or u,
                     key=lambda p: float(p.get("cost_usd", 0)))
        amount = float(chosen.get("cost_usd", 0))
        if unit == "megapixel":
            amount *= 1.25 if "1K" in enum_values(endpoint.get("supported_parameters", {}), "resolution") else 4.0
        relevant.append(amount)
    return sum(relevant) if relevant else None


def discover(max_per_image: float) -> list[dict[str, Any]]:
    ranked = request(f"{BASE}/models?output_modalities=image&sort=design-arena-elo-high-to-low").get("data", [])
    catalog = {m["id"]: m for m in request(f"{BASE}/images/models").get("data", []) if m.get("id")}
    found = []
    for rank, model in enumerate(ranked[:80], 1):
        mid = model.get("id")
        entry = catalog.get(mid)
        if not entry:
            continue
        arch = entry.get("architecture", {})
        if "text" not in arch.get("input_modalities", []) or "image" not in arch.get("output_modalities", []):
            continue
        eps_url = urllib.parse.urljoin(ORIGIN, entry.get("endpoints", ""))
        best = None
        for ep in request(eps_url).get("endpoints", []):
            est = cost_estimate(ep)
            if not ep.get("provider_tag") or est is None or est <= 0 or est > max_per_image:
                continue
            if best is None or est < best[0]:
                best = (est, ep)
        if best:
            est, ep = best
            found.append({"model": mid, "name": model.get("name", mid), "rank": rank,
                          "author": mid.split("/", 1)[0], "provider_tag": ep["provider_tag"],
                          "provider_name": ep.get("provider_name", ep["provider_tag"]),
                          "params": ep.get("supported_parameters", {}),
                          "pricing": ep.get("pricing", []), "estimated_cost_usd": est})
    return found


def choose(candidates: list[dict[str, Any]], count: int, budget: float) -> list[dict[str, Any]]:
    picked, authors, planned = [], set(), 0.0
    for unique_only in (True, False):
        for c in candidates:
            if len(picked) >= count:
                return picked
            if c in picked or (unique_only and c["author"] in authors):
                continue
            if planned + c["estimated_cost_usd"] > budget:
                continue
            picked.append(c); authors.add(c["author"]); planned += c["estimated_cost_usd"]
    return picked


def art_prompt(line: dict[str, str]) -> str:
    return f"""Create ONE original raster illustration for a public document called Chad Philosophy.

The broad internet-culture archetype should read immediately as a "Chad": an absurdly handsome, square-jawed, self-possessed adult man with a strong neck and shoulders, clean contemporary hair, relaxed posture, and a calm, slightly amused, completely unbothered expression. Confident, not angry or domineering. The humor is his impossible composure.

ORIGINALITY: Invent a NEW face, hair, clothing, pose, composition, and visual language. Do NOT reproduce or closely imitate a specific Yes Chad / Nordic Gamer / Wojak / Virgin-vs-Chad drawing, GigaChad photograph, celebrity, copyrighted character, logo, or named artist style. No reference image is supplied. No words, captions, labels, logos, or watermarks inside the image.

TARGET: iconic internet-meme readability; polished editorial/cartoon illustration rather than glamour photography; bold silhouette; expressive facial geometry; portrait-oriented composition; unmistakably in the broad Chad-archetype distribution while remaining a new design.

SECTION: {line['section']}
LINE: {line['line']}
SCENE BRIEF: {line['brief']}

Make the scene embody that line while keeping the original Chad-like figure as the clear focal character."""


def payload_for(c: dict[str, Any], prompt: str) -> dict[str, Any]:
    p: dict[str, Any] = {"model": c["model"], "prompt": prompt, "n": 1,
                         "provider": {"only": [c["provider_tag"]], "allow_fallbacks": False}}
    if "1K" in enum_values(c["params"], "resolution"):
        p["resolution"] = "1K"
    ratios = enum_values(c["params"], "aspect_ratio")
    if "4:5" in ratios: p["aspect_ratio"] = "4:5"
    elif "1:1" in ratios: p["aspect_ratio"] = "1:1"
    if "png" in [v.lower() for v in enum_values(c["params"], "output_format")]:
        p["output_format"] = "png"
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
    return {"error": None, "usage": body.get("usage"), "media_type": media, "bytes": raw,
            "elapsed_seconds": round(time.time() - started, 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=Path, default=DEFAULT_LINES)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-artists", type=int, default=6)
    ap.add_argument("--max-spend-usd", type=float, default=1.0)
    ap.add_argument("--max-per-image-usd", type=float, default=.15)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not 1 <= a.max_artists <= 12: raise ValueError("max artists must be 1..12")
    if not 0 < a.max_per_image_usd <= a.max_spend_usd: raise ValueError("invalid spend caps")
    lines = json.loads(a.lines.read_text())
    candidates = discover(a.max_per_image_usd)
    selected = choose(candidates, min(a.max_artists, len(lines)), a.max_spend_usd)
    planned = sum(c["estimated_cost_usd"] for c in selected)
    print(f"selected={len(selected)} planned=${planned:.4f} total_cap=${a.max_spend_usd:.2f}")
    for i, c in enumerate(selected):
        line = lines[i]
        print(f"{i+1}. rank={c['rank']} {c['model']} via {c['provider_tag']} est=${c['estimated_cost_usd']:.4f} -> {line['line']}")
    if a.dry_run: return 0
    if not selected: raise RuntimeError("no image models fit predictable-cost caps")

    imgdir = a.out_dir / "images"; imgdir.mkdir(parents=True, exist_ok=True)
    prov = a.out_dir / "provenance.jsonl"
    if prov.exists(): raise FileExistsError(prov)
    rows, actual_total = [], 0.0
    for i, c in enumerate(selected):
        line, prompt = lines[i], art_prompt(lines[i])
        print(f"[{i+1}/{len(selected)}] {c['model']} -> {line['id']}", flush=True)
        result = generate(c, prompt, a.timeout)
        usage = result.get("usage") or {}
        try: actual = float(usage["cost"]) if usage.get("cost") is not None else None
        except (TypeError, ValueError): actual = None
        if actual is not None: actual_total += actual
        row = {"schema_version": 1, "philosophy": line, **{k: c[k] for k in
               ("model","name","rank","author","provider_tag","provider_name","pricing","estimated_cost_usd")},
               "actual_cost_usd": actual, "actual_cumulative_cost_usd": actual_total,
               "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "usage": usage, "reference_image_supplied": False, "error": result.get("error"),
               "image_file": None, "image_sha256": None, "media_type": result.get("media_type")}
        if not row["error"]:
            raw = result["bytes"]; ext = EXT[result["media_type"]]
            name = f"{i+1:02d}-{slug(line['id'])}--{slug(c['model'])}{ext}"
            (imgdir / name).write_bytes(raw); row["image_file"] = name
            row["image_sha256"] = hashlib.sha256(raw).hexdigest(); row["image_bytes"] = len(raw)
        with prov.open("a", encoding="utf-8") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
        rows.append(row)
        if actual_total >= a.max_spend_usd:
            print(f"reported cost reached ${actual_total:.4f}; stopping")
            break

    gallery = ["# Chad Philosophy — raster swarm", "", "Original generations; no reference image was supplied.", ""]
    for r in rows:
        if r["error"] or not r["image_file"]: continue
        line = r["philosophy"]
        gallery += [f"## {line['line']}", "", f"![{line['line']}](images/{r['image_file']})", "",
                    f"*annoned by `{r['model']}` via `{r['provider_tag']}` — original raster generation, no reference image supplied.*", ""]
    (a.out_dir / "gallery.md").write_text("\n".join(gallery) + "\n")
    summary = {"selected": len(selected), "attempted": len(rows),
               "successful": sum(not r["error"] and bool(r["image_file"]) for r in rows),
               "planned_estimated_cost_usd": planned, "reported_actual_cost_usd": actual_total,
               "max_spend_usd": a.max_spend_usd, "max_per_image_usd": a.max_per_image_usd}
    (a.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
