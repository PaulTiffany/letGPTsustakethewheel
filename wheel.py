#!/usr/bin/env python3
"""Cross-model screenshot opinion poll via OpenRouter.

One screenshot, one prompt, many image-capable models. Raw disagreement is the
artifact; the summary is only a histogram of recommended actions.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
APP_TITLE = "letGPTsustakethewheel"
DEFAULT_IMAGE = Path("assets/letGPTsustakethewheel.jpg")
DEFAULT_OUT = Path("results/poll.jsonl")

ACTIONS = (
    "Save",
    "Copy link to post",
    "Embed this post",
    "Unfollow rUv.",
    "Not interested",
    "Seems like AI slop",
    "Report post",
)

SYSTEM_PROMPT = """You are one voter in a cross-model opinion poll.
Inspect the screenshot and visible context. Recommend exactly one menu action for the user.
Do not take the action. Do not claim consensus. Prefer the user's apparent intent over generic caution.
Return one JSON object only, with exactly these keys: action, confidence, reason.
action must exactly match one of the supplied menu labels. confidence must be a number from 0 to 1.
reason must be one short sentence.
"""

USER_PROMPT = """Choose for user Paul Carver Tiffany III. Which one menu action should he take?

Allowed menu labels:
- Save
- Copy link to post
- Embed this post
- Unfollow rUv.
- Not interested
- Seems like AI slop
- Report post

Return only the requested JSON object. Do not take the action."""


def _headers(require_key: bool = True) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/PaulTiffany/letGPTsustakethewheel",
        "X-OpenRouter-Title": APP_TITLE,
    }
    key = os.environ.get("OPENROUTER_API_KEY")
    if require_key and not key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
                  timeout: int = 60, require_key: bool = True) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(require_key), method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_models(require_key: bool = False) -> list[dict[str, Any]]:
    body = _request_json(
        f"{OPENROUTER_BASE}/models?output_modalities=text&sort=pricing-low-to-high",
        require_key=require_key,
    )
    models = body.get("data", [])
    if not isinstance(models, list):
        raise RuntimeError("Unexpected OpenRouter models response")
    return models


def _price(model: dict[str, Any], field: str) -> float:
    try:
        return float((model.get("pricing") or {}).get(field, "inf"))
    except (TypeError, ValueError):
        return float("inf")


def is_image_to_text(model: dict[str, Any]) -> bool:
    arch = model.get("architecture") or {}
    inputs = {str(x).lower() for x in (arch.get("input_modalities") or [])}
    outputs = {str(x).lower() for x in (arch.get("output_modalities") or [])}
    modality = str(arch.get("modality") or "").lower()
    image_in = "image" in inputs or "image" in modality
    text_out = "text" in outputs or modality.endswith("->text") or "text" in modality
    return image_in and text_out


def is_free(model: dict[str, Any]) -> bool:
    mid = str(model.get("id") or "")
    return mid.endswith(":free") or (_price(model, "prompt") == 0 and _price(model, "completion") == 0)


def select_models(models: list[dict[str, Any]], max_models: int, free_only: bool) -> list[dict[str, Any]]:
    selected = [m for m in models if m.get("id") and is_image_to_text(m)]
    if free_only:
        selected = [m for m in selected if is_free(m)]
    selected.sort(key=lambda m: (
        _price(m, "prompt") + _price(m, "completion"),
        -(m.get("context_length") or 0),
        str(m.get("id")),
    ))
    return selected[:max_models]


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def parse_vote(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.I | re.S).strip()
    try:
        obj = json.loads(fenced)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", fenced, flags=re.S)
        if not match:
            return {"action": None, "confidence": None, "reason": None, "parse_error": "no JSON object"}
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            return {"action": None, "confidence": None, "reason": None, "parse_error": str(exc)}

    action = obj.get("action")
    confidence = obj.get("confidence")
    reason = obj.get("reason")
    error = None
    if action not in ACTIONS:
        error = f"invalid action: {action!r}"
    try:
        confidence = float(confidence)
        if not 0 <= confidence <= 1:
            raise ValueError
    except (TypeError, ValueError):
        error = (error + "; " if error else "") + f"invalid confidence: {confidence!r}"
        confidence = None
    if not isinstance(reason, str) or not reason.strip():
        error = (error + "; " if error else "") + "invalid reason"
        reason = None
    return {"action": action if action in ACTIONS else None,
            "confidence": confidence, "reason": reason, "parse_error": error}


def call_model(model: dict[str, Any], data_url: str, max_tokens: int, timeout: int) -> dict[str, Any]:
    model_id = str(model["id"])
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": USER_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    started = time.time()
    try:
        body = _request_json(
            f"{OPENROUTER_BASE}/chat/completions", method="POST", payload=payload,
            timeout=timeout, require_key=True,
        )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:2000]
        return {"model": model_id, "elapsed_seconds": round(time.time() - started, 3),
                "error": {"status_code": exc.code, "body": raw}}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"model": model_id, "elapsed_seconds": round(time.time() - started, 3),
                "error": {"exception": type(exc).__name__, "message": str(exc)[:500]}}

    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = message.get("content") or ""
    vote = parse_vote(text)
    return {
        "model": model_id,
        "resolved_model": body.get("model"),
        "elapsed_seconds": round(time.time() - started, 3),
        "response_text": text,
        "usage": body.get("usage"),
        "finish_reason": choice.get("finish_reason"),
        "vote": vote,
        "error": None,
    }


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    successful = [r for r in rows if not r.get("error")]
    valid = [r for r in successful if not (r.get("vote") or {}).get("parse_error")]
    counts = Counter((r.get("vote") or {}).get("action") for r in valid)
    return {
        "total_calls": len(rows),
        "successful_calls": len(successful),
        "valid_votes": len(valid),
        "errors": len(rows) - len(successful),
        "parse_failures": len(successful) - len(valid),
        "action_counts": {action: counts.get(action, 0) for action in ACTIONS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-models", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--free-only", action="store_true", help="Poll only zero-priced / :free models")
    parser.add_argument("--dry-run", action="store_true", help="List selected models without inference")
    args = parser.parse_args()

    models = select_models(fetch_models(require_key=False), args.max_models, args.free_only)
    print(f"Selected {len(models)} image-capable model(s):")
    for model in models:
        print(f"  {model['id']}  free={is_free(model)}")
    if args.dry_run:
        return 0
    if not models:
        raise RuntimeError("No matching image-capable models found")
    if args.out.exists():
        raise FileExistsError(f"Refusing to append to existing output: {args.out}")

    data_url = image_data_url(args.image)
    for idx, model in enumerate(models, start=1):
        print(f"[{idx}/{len(models)}] {model['id']}", flush=True)
        row = {
            "schema_version": 1,
            "question": USER_PROMPT,
            **call_model(model, data_url, args.max_tokens, args.timeout),
        }
        append_jsonl(args.out, row)
        if idx != len(models):
            time.sleep(args.sleep)

    summary = summarize(args.out)
    summary_path = args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.out} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
