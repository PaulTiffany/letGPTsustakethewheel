#!/usr/bin/env python3
"""Let many free text models draw original Chad philosophy art as safe SVG.

No source image is supplied. Each selected model gets one philosophy line and invents
its own character/composition from the concept alone. Raw outputs are preserved; only
mechanically sanitized SVG is promoted into the generated gallery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import wheel

LINES_PATH = Path("chad_lines.json")
DEFAULT_OUT = Path("results/chad-anon")
MAX_MODELS = 12

ALLOWED_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
    "polygon", "text", "tspan", "defs", "linearGradient", "radialGradient",
    "stop", "clipPath", "title", "desc",
}
ALLOWED_ATTRS = {
    "viewBox", "width", "height", "x", "y", "x1", "y1", "x2", "y2",
    "cx", "cy", "r", "rx", "ry", "d", "points", "fill", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity", "transform",
    "font-size", "font-family", "font-weight", "text-anchor", "dominant-baseline",
    "offset", "stop-color", "stop-opacity", "gradientUnits", "gradientTransform",
    "id", "fill-rule", "clip-rule",
}

SYSTEM_PROMPT = """You are one anonymous illustrator in a cross-model art jam.
Draw one ORIGINAL archetypal character embodying a line from a philosophy jokingly called
"Chad Philosophy": calm confidence, reality over reputation, willingness to be corrected,
and freedom from needless status-defensiveness.

IMPORTANT ORIGINALITY RULES:
- Invent the character and composition from the concept alone.
- Do NOT reproduce, trace, closely imitate, or reference any existing Chad meme image,
  Wojak, Nordic/Yes Chad, Virgin-vs-Chad drawing, GigaChad photograph, celebrity, logo,
  trademarked character, or named artist's style.
- No source/reference image has been supplied; do not ask for one.
- Visual metaphor is encouraged. Humor is encouraged. Dominance, cruelty, or macho posturing
  are not required; the point is epistemic composure.

OUTPUT CONTRACT:
Return exactly one standalone SVG document and nothing else.
Use viewBox="0 0 800 800". No scripts, CSS, foreignObject, image tags, links, external assets,
base64/data URIs, event handlers, animations, or embedded raster content. Use only basic SVG
geometry, paths, gradients, and optional text. Keep it under 45,000 characters.
"""


def fetch_free_text_models() -> list[dict[str, Any]]:
    body = wheel._request_json(
        f"{wheel.OPENROUTER_BASE}/models?input_modalities=text&output_modalities=text&sort=pricing-low-to-high",
        require_key=False,
    )
    models = body.get("data", [])
    if not isinstance(models, list):
        raise RuntimeError("Unexpected OpenRouter models response")
    eligible = []
    for model in models:
        mid = str(model.get("id") or "")
        arch = model.get("architecture") or {}
        inputs = {str(x).lower() for x in (arch.get("input_modalities") or [])}
        outputs = {str(x).lower() for x in (arch.get("output_modalities") or [])}
        if not mid.endswith(":free"):
            continue
        if "text" not in inputs or "text" not in outputs:
            continue
        if wheel.is_dynamic_router(model) or wheel.is_specialized(model):
            continue
        if not wheel.is_free(model):
            continue
        eligible.append(model)
    return eligible


def select_diverse(models: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Prefer one model per author prefix before filling remaining slots."""
    ordered = sorted(models, key=lambda m: (-(m.get("context_length") or 0), str(m.get("id"))))
    chosen: list[dict[str, Any]] = []
    seen_authors: set[str] = set()
    leftovers: list[dict[str, Any]] = []
    for model in ordered:
        mid = str(model["id"])
        author = mid.split("/", 1)[0]
        if author not in seen_authors and len(chosen) < limit:
            chosen.append(model)
            seen_authors.add(author)
        else:
            leftovers.append(model)
    for model in leftovers:
        if len(chosen) >= limit:
            break
        chosen.append(model)
    return chosen[:limit]


def strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:svg|xml)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_svg(text: str) -> str:
    text = strip_code_fence(text)
    start = text.find("<svg")
    end = text.rfind("</svg>")
    if start < 0 or end < 0 or end < start:
        raise ValueError("no complete SVG document found")
    svg = text[start : end + len("</svg>")]
    if len(svg) > 45_000:
        raise ValueError(f"SVG too large: {len(svg)} characters")
    return svg


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def safe_attr_value(name: str, value: str) -> bool:
    low = value.lower().strip()
    if "javascript:" in low or "data:" in low or "http://" in low or "https://" in low:
        return False
    if "url(" in low and not re.fullmatch(r"url\(#[A-Za-z_][\w:.-]*\)", value.strip()):
        return False
    if name == "font-family" and len(value) > 120:
        return False
    return len(value) <= 20_000


def sanitize_svg(raw_svg: str) -> str:
    banned_markers = ("<script", "<foreignobject", "<image", "<a ", "<use", "<!entity", "<!doctype")
    low = raw_svg.lower()
    if any(marker in low for marker in banned_markers):
        raise ValueError("SVG contains a banned element or declaration")

    try:
        root = ET.fromstring(raw_svg)
    except ET.ParseError as exc:
        raise ValueError(f"invalid XML: {exc}") from exc
    if local_name(root.tag) != "svg":
        raise ValueError("root element is not svg")

    count = 0
    for elem in root.iter():
        count += 1
        if count > 450:
            raise ValueError("SVG contains too many elements")
        tag = local_name(elem.tag)
        if tag not in ALLOWED_TAGS:
            raise ValueError(f"disallowed SVG tag: {tag}")
        elem.tag = tag
        clean: dict[str, str] = {}
        for key, value in elem.attrib.items():
            name = local_name(key)
            if name.lower().startswith("on") or name in {"href", "xlink:href", "style", "class"}:
                continue
            if name in ALLOWED_ATTRS and safe_attr_value(name, value):
                clean[name] = value
        elem.attrib.clear()
        elem.attrib.update(clean)

    root.set("xmlns", "http://www.w3.org/2000/svg")
    root.set("viewBox", "0 0 800 800")
    root.set("width", "800")
    root.set("height", "800")
    return ET.tostring(root, encoding="unicode") + "\n"


def call_artist(model: dict[str, Any], line: dict[str, str], max_tokens: int, timeout: int) -> dict[str, Any]:
    mid = str(model["id"])
    prompt = (
        f"PHILOSOPHY SECTION: {line['section']}\n"
        f"LINE TO ILLUSTRATE: {line['line']}\n"
        f"MEANING: {line['brief']}\n\n"
        "Create a visually distinct original interpretation. Let the scene carry the idea; "
        "embedded words are optional and should be minimal. Return only the SVG."
    )
    payload = {
        "model": mid,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "max_tokens": max_tokens,
    }
    started = time.time()
    try:
        body = wheel._request_json(
            f"{wheel.OPENROUTER_BASE}/chat/completions",
            method="POST",
            payload=payload,
            timeout=timeout,
            require_key=True,
        )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:2000]
        return {"model": mid, "prompt": prompt, "elapsed_seconds": round(time.time() - started, 3),
                "error": {"status_code": exc.code, "body": raw}}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"model": mid, "prompt": prompt, "elapsed_seconds": round(time.time() - started, 3),
                "error": {"exception": type(exc).__name__, "message": str(exc)[:500]}}

    choice = (body.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    return {
        "model": mid,
        "resolved_model": body.get("model"),
        "prompt": prompt,
        "elapsed_seconds": round(time.time() - started, 3),
        "usage": body.get("usage"),
        "finish_reason": choice.get("finish_reason"),
        "response_text": text,
        "error": None,
    }


def safe_slug(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model_id).strip("-")[:100]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_gallery(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Chad Art Swarm",
        "",
        "Each piece below was independently drawn as SVG by a different free text model from a text-only philosophy brief.",
        "No canonical Chad image or other visual reference was supplied to any model.",
        "",
    ]
    for row in rows:
        philosophy = row["philosophy"]
        lines += [f"## {philosophy['line']}", ""]
        if row.get("svg_file"):
            lines += [
                f'<img src="{row["svg_file"]}" alt="Original model-generated illustration for {philosophy["line"]}" width="560">',
                "",
                f'*annoned by `{row["model"]}` via OpenRouter — original sanitized SVG, no reference image supplied.*',
            ]
        else:
            lines += [f"*No publishable SVG from `{row['model']}` in this run.*"]
        lines += [""]
    (out_dir / "gallery.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=Path, default=LINES_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-models", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=5000)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.max_models <= MAX_MODELS:
        raise ValueError(f"--max-models must be between 1 and {MAX_MODELS}")
    philosophy_lines = json.loads(args.lines.read_text(encoding="utf-8"))
    if len(philosophy_lines) < args.max_models:
        raise ValueError("not enough philosophy lines for requested model count")

    models = select_diverse(fetch_free_text_models(), args.max_models)
    if not models:
        raise RuntimeError("No concrete free text models found")
    pairs = list(zip(models, philosophy_lines[: len(models)], strict=True))

    print(f"Selected {len(pairs)} free artist model(s):")
    for model, line in pairs:
        print(f"  {model['id']}  ->  {line['id']}: {line['line']}")
    if args.dry_run:
        return 0

    if args.out_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {args.out_dir}")
    args.out_dir.mkdir(parents=True)
    raw_dir = args.out_dir / "raw"
    svg_dir = args.out_dir / "svg"
    raw_dir.mkdir()
    svg_dir.mkdir()

    rows: list[dict[str, Any]] = []
    for idx, (model, line) in enumerate(pairs, start=1):
        print(f"[{idx}/{len(pairs)}] {model['id']} -> {line['id']}", flush=True)
        result = call_artist(model, line, args.max_tokens, args.timeout)
        row: dict[str, Any] = {
            "schema_version": 1,
            "philosophy": line,
            "model": str(model["id"]),
            "resolved_model": result.get("resolved_model"),
            "prompt_sha256": sha256_text(result.get("prompt", "")),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "usage": result.get("usage"),
            "finish_reason": result.get("finish_reason"),
            "error": result.get("error"),
            "svg_file": None,
            "svg_sha256": None,
            "sanitize_error": None,
        }
        response_text = result.get("response_text") or ""
        raw_name = f"{idx:02d}-{line['id']}--{safe_slug(str(model['id']))}.txt"
        (raw_dir / raw_name).write_text(response_text, encoding="utf-8")
        row["raw_response_file"] = f"raw/{raw_name}"
        row["raw_response_sha256"] = sha256_text(response_text)
        if not row["error"]:
            try:
                clean_svg = sanitize_svg(extract_svg(response_text))
                svg_name = f"{idx:02d}-{line['id']}--{safe_slug(str(model['id']))}.svg"
                (svg_dir / svg_name).write_text(clean_svg, encoding="utf-8")
                row["svg_file"] = f"svg/{svg_name}"
                row["svg_sha256"] = sha256_text(clean_svg)
            except ValueError as exc:
                row["sanitize_error"] = str(exc)
        rows.append(row)
        if idx != len(pairs):
            time.sleep(args.sleep)

    with (args.out_dir / "provenance.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_gallery(args.out_dir, rows)
    ok = sum(bool(row.get("svg_file")) for row in rows)
    print(f"Sanitized {ok}/{len(rows)} SVG artworks")
    print(f"Wrote {args.out_dir / 'gallery.md'} and provenance.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
