#!/usr/bin/env python3
"""Cross-model screenshot opinion poll via OpenRouter.

One screenshot, one prompt, many concrete image-capable models. Raw disagreement
is the artifact; the summary is only a histogram of recommended actions.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
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
MIN_FIXTURE_BYTES = 50_000
MAX_WORKFLOW_MODELS = 20

ACTIONS = (
    "Save",
    "Copy link to post",
    "Embed this post",
    "Unfollow",
    "Not interested",
    "Seems like AI slop",
    "Report post",
)

SPECIALIZED_ID_MARKERS = (
    "content-safety",
    "moderation",
    "guard",
    "lyria",
    "embedding",
    "rerank",
    "ocr",
    "tts",
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
- Unfollow
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


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
    require_key: bool = True,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(require_key), method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_models(require_key: bool = False) -> list[dict[str, Any]]:
    body = _request_json(
        f"{OPENROUTER_BASE}/models?input_modalities=image&output_modalities=text&sort=pricing-low-to-high",
        require_key=require_key,
    )
    models = body.get("data", [])
    if not isinstance(models, list):
        raise RuntimeError("Unexpected OpenRouter models response")
    return models


def _pricing(model: dict[str, Any]) -> dict[str, Any]:
    pricing = model.get("pricing") or {}
    if isinstance(pricing, list):
        pricing = pricing[0] if pricing else {}
    return pricing if isinstance(pricing, dict) else {}


def _price(model: dict[str, Any], field: str, *, missing: float = float("inf")) -> float:
    try:
        value = _pricing(model).get(field)
        return missing if value in (None, "") else float(value)
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
    # Multimodal requests can be charged per token, request, image, or reasoning.
    # "Free" means every pricing dimension this poll can exercise is explicitly zero.
    fields = ("prompt", "completion", "request", "image", "internal_reasoning")
    return all(_price(model, field, missing=0.0) == 0 for field in fields)


def is_dynamic_router(model: dict[str, Any]) -> bool:
    return str(model.get("id") or "").startswith("openrouter/")


def is_specialized(model: dict[str, Any]) -> bool:
    mid = str(model.get("id") or "").lower()
    return any(marker in mid for marker in SPECIALIZED_ID_MARKERS)


def select_models(
    models: list[dict[str, Any]],
    max_models: int,
    *,
    allow_paid: bool = False,
    include_specialized: bool = False,
) -> list[dict[str, Any]]:
    selected = [
        m
        for m in models
        if m.get("id") and is_image_to_text(m) and not is_dynamic_router(m)
    ]
    if not allow_paid:
        selected = [m for m in selected if is_free(m)]
    if not include_specialized:
        selected = [m for m in selected if not is_specialized(m)]

    selected.sort(
        key=lambda m: (
            _price(m, "prompt", missing=0.0) + _price(m, "completion", missing=0.0) + _price(m, "request", missing=0.0) + _price(m, "image", missing=0.0),
            -(m.get("context_length") or 0),
            str(m.get("id")),
        )
    )
    return selected[:max_models]


def fixture_metadata(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise FileNotFoundError(f"Fixture not found: {path}")

    data = path.read_bytes()
    if len(data) < MIN_FIXTURE_BYTES:
        raise ValueError(
            f"Fixture is suspiciously small ({len(data)} bytes); "
            f"minimum is {MIN_FIXTURE_BYTES} bytes"
        )

    if data.startswith(b"\xff\xd8\xff"):
        magic_mime = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        magic_mime = "image/png"
    else:
        raise ValueError("Fixture must be a JPEG or PNG with a recognized file signature")

    filename_mime = mimetypes.guess_type(path.name)[0]
    if filename_mime != magic_mime:
        raise ValueError(
            f"Fixture MIME mismatch: filename implies {filename_mime!r}, "
            f"bytes are {magic_mime!r}"
        )

    meta = {
        "path": path.as_posix(),
        "bytes": len(data),
        "mime_type": magic_mime,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return meta, data


def image_data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def parse_vote(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.I | re.S).strip()
    try:
        obj = json.loads(fenced)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", fenced, flags=re.S)
        if not match:
            return {
                "action": None,
                "confidence": None,
                "reason": None,
                "parse_error": "no JSON object",
            }
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            return {
                "action": None,
                "confidence": None,
                "reason": None,
                "parse_error": str(exc),
            }

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

    return {
        "action": action if action in ACTIONS else None,
        "confidence": confidence,
        "reason": reason,
        "parse_error": error,
    }


def call_model(
    model: dict[str, Any],
    data_url: str,
    max_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    model_id = str(model["id"])
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    started = time.time()
    try:
        body = _request_json(
            f"{OPENROUTER_BASE}/chat/completions",
            method="POST",
            payload=payload,
            timeout=timeout,
            require_key=True,
        )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:2000]
        return {
            "model": model_id,
            "elapsed_seconds": round(time.time() - started, 3),
            "error": {"status_code": exc.code, "body": raw},
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {
            "model": model_id,
            "elapsed_seconds": round(time.time() - started, 3),
            "error": {"exception": type(exc).__name__, "message": str(exc)[:500]},
        }

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


def summarize(
    path: Path,
    *,
    fixture: dict[str, Any],
    allow_paid: bool,
    include_specialized: bool,
) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    successful = [r for r in rows if not r.get("error")]
    valid = [r for r in successful if not (r.get("vote") or {}).get("parse_error")]
    counts = Counter((r.get("vote") or {}).get("action") for r in valid)
    return {
        "fixture": fixture,
        "selection_policy": {
            "concrete_models_only": True,
            "allow_paid": allow_paid,
            "include_specialized": include_specialized,
        },
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
    parser.add_argument(
        "--allow-paid",
        action="store_true",
        help="Opt in to paid models; default is zero-priced models only",
    )
    parser.add_argument(
        "--include-specialized",
        action="store_true",
        help="Include moderation/safety/audio/OCR-style specialist models",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preflight fixture and list selected models without inference",
    )
    args = parser.parse_args()

    if not 1 <= args.max_models <= MAX_WORKFLOW_MODELS:
        raise ValueError(f"--max-models must be between 1 and {MAX_WORKFLOW_MODELS}")
    if not 1 <= args.max_tokens <= 512:
        raise ValueError("--max-tokens must be between 1 and 512")

    fixture, image_bytes = fixture_metadata(args.image)
    print(
        "Fixture: "
        f"{fixture['path']} bytes={fixture['bytes']} "
        f"mime={fixture['mime_type']} sha256={fixture['sha256']}"
    )

    models = select_models(
        fetch_models(require_key=False),
        args.max_models,
        allow_paid=args.allow_paid,
        include_specialized=args.include_specialized,
    )
    print(f"Selected {len(models)} concrete image-capable model(s):")
    for model in models:
        print(
            f"  {model['id']}  free={is_free(model)} "
            f"specialized={is_specialized(model)}"
        )

    if args.dry_run:
        return 0
    if not models:
        raise RuntimeError("No matching concrete image-capable models found")
    if args.out.exists():
        raise FileExistsError(f"Refusing to append to existing output: {args.out}")

    data_url = image_data_url(image_bytes, fixture["mime_type"])
    for idx, model in enumerate(models, start=1):
        print(f"[{idx}/{len(models)}] {model['id']}", flush=True)
        row = {
            "schema_version": 2,
            "question": USER_PROMPT,
            "fixture": fixture,
            "selection": {
                "free": is_free(model),
                "specialized": is_specialized(model),
            },
            **call_model(model, data_url, args.max_tokens, args.timeout),
        }
        append_jsonl(args.out, row)
        if idx != len(models):
            time.sleep(args.sleep)

    summary = summarize(
        args.out,
        fixture=fixture,
        allow_paid=args.allow_paid,
        include_specialized=args.include_specialized,
    )
    summary_path = args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.out} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
