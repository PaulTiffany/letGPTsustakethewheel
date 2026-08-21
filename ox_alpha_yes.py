#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, re, urllib.request
from pathlib import Path

MODEL = "stealth/ox-alpha"
BASE = "https://openrouter.ai/api/v1/chat/completions"
OUT = Path("results/ox-alpha-yes")
PROMPT = '''Create ONE original self-contained SVG illustration for the final beat of Chad Philosophy.

Context, exactly:
Someone says: “This whole philosophy came from a stupid internet meme.”
Answer: Yes.

Visual meaning: relaxed acceptance of an embarrassing origin without defensiveness; truth and usefulness do not depend on prestige. The image should feel like a final affirmative full stop after a long philosophy about epistemic humility, tests, provenance, bounded authority, independent stop paths, play, and knowing when to stop.

Composition: portrait 4:5, viewBox 0 0 1024 1280. A handsome square-jawed adult man, strong neck and shoulders, relaxed posture, calm amused expression, confident but never domineering. Invent the face, clothes, pose, and scene. Do NOT copy Chad/Wojak/GigaChad, any celebrity, copyrighted character, logo, or named artist style.

This terminal image is the ONE exception to the document's usual no-text rule: the single visible word YES may appear, and no other visible words, letters, numbers, logos, signatures, or watermarks may appear. Make YES integral to the composition rather than a caption.

Return ONLY the complete SVG document beginning with <svg and ending with </svg>. No markdown fence, explanation, external images, external fonts, scripts, links, data URLs, CSS imports, or foreignObject. Use only SVG vector primitives, paths, gradients, masks, clipPaths, and the single text element YES.'''

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def call() -> dict:
    key = os.environ["OPENROUTER_API_KEY"]
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role":"user","content":PROMPT}],
        "temperature": 1.0,
        "max_tokens": 12000,
        "provider": {"allow_fallbacks": False},
    }).encode()
    req = urllib.request.Request(BASE, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type":"application/json",
        "HTTP-Referer":"https://github.com/PaulTiffany/letGPTsustakethewheel",
        "X-OpenRouter-Title":"Ox Alpha YES",
    })
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())

def collect_text(value) -> list[str]:
    out=[]
    if isinstance(value, str):
        if value.strip(): out.append(value)
    elif isinstance(value, list):
        for part in value:
            if isinstance(part, str):
                if part.strip(): out.append(part)
            elif isinstance(part, dict):
                for key in ("text", "content", "reasoning", "reasoning_text"):
                    out.extend(collect_text(part.get(key)))
    elif isinstance(value, dict):
        for key in ("text", "content", "reasoning", "reasoning_text"):
            out.extend(collect_text(value.get(key)))
    return out

def response_text(raw: dict) -> str:
    choices = raw.get("choices") or []
    if not choices:
        raise ValueError(f"no choices in response; keys={sorted(raw.keys())}")
    choice = choices[0] or {}
    msg = choice.get("message") or {}
    pieces=[]
    for key in ("content", "reasoning", "reasoning_content", "reasoning_details"):
        pieces.extend(collect_text(msg.get(key)))
    pieces.extend(collect_text(choice.get("text")))
    if not pieces:
        diag = {
            "finish_reason": choice.get("finish_reason"),
            "choice_keys": sorted(choice.keys()),
            "message_keys": sorted(msg.keys()),
            "usage": raw.get("usage"),
        }
        raise ValueError("no textual payload found: " + json.dumps(diag, sort_keys=True))
    return "\n".join(pieces)

def extract_svg(text: str) -> str:
    m = re.search(r"<svg\b[\s\S]*?</svg>", text, re.I)
    if not m: raise ValueError("no complete SVG in extracted response text")
    svg = m.group(0)
    low = svg.lower()
    forbidden = ["<script", "<foreignobject", "<image", "href=", "xlink:", "url(", "@import", "data:", "http://", "https://"]
    for x in forbidden:
        if x in low: raise ValueError(f"forbidden SVG construct: {x}")
    if not re.search(r'<svg\b[^>]*viewBox=["\']0 0 1024 1280["\']', svg, re.I):
        raise ValueError("SVG must use viewBox 0 0 1024 1280")
    visible_text = re.findall(r"<text\b[^>]*>([\s\S]*?)</text>", svg, re.I)
    flattened = [re.sub(r"<[^>]+>", "", t).strip() for t in visible_text]
    if flattened != ["YES"]:
        raise ValueError(f"only one text element containing YES is allowed, got {flattened!r}")
    return svg

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows=[]
    for i in range(1,5):
        raw = call()
        raw_path=OUT/f"{i:02d}-response.json"
        raw_path.write_text(json.dumps(raw, indent=2)+"\n")
        try:
            text = response_text(raw)
            svg = extract_svg(text)
        except Exception as e:
            (OUT/f"{i:02d}-error.txt").write_text(f"{type(e).__name__}: {e}\n")
            raise
        svg_b = svg.encode()
        name=f"{i:02d}-ox-alpha-yes.svg"
        (OUT/name).write_bytes(svg_b)
        rows.append({
            "variant":i, "model":MODEL, "prompt":PROMPT,
            "prompt_sha256":sha(PROMPT.encode()), "svg_file":name,
            "svg_sha256":sha(svg_b), "usage":raw.get("usage"),
            "transform_note":"Ox Alpha authored SVG source; PNG rasterization is a deterministic mechanical render performed by CairoSVG in the workflow."
        })
    (OUT/"provenance.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    return 0

if __name__ == "__main__": raise SystemExit(main())
