#!/usr/bin/env python3
"""Cross-model visual grounding poll for Chad Philosophy.

Reuses the free, concrete image-to-text model selection mechanics from wheel.py.
Models score semantic grounding only. Rights/provenance are recorded separately
and are never decided by model vote.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

import wheel

DEFAULT_CANDIDATES = Path("chad_candidates.json")
DEFAULT_OUT = Path("results/chad-grounding.jsonl")
MIN_IMAGE_BYTES = 10_000

SYSTEM_PROMPT = """You are one voter in a cross-model visual-grounding poll.
You are evaluating ONE candidate image for a public Markdown document called "Chad Philosophy."
Do not decide copyright, licensing, fair use, attribution, or legal risk. Those are audited separately.
Judge only how well the image grounds the cultural concept for a reader who may never have seen the meme.
Return one JSON object only with exactly these keys:
semantic_fit, newcomer_clarity, meme_recognizability, confidence, reason.
The first four values must be numbers from 0 to 100.
reason must be one short sentence.
"""

PHILOSOPHY_BRIDGE = """The document teaches this idea:
"Chad" is an internet joke about a person who can hear a potentially embarrassing predicate,
accept it if it is true, refuse the unnecessary shame payload, test uncertain claims, and continue.
Its compact operator is: True? Yes. False? Show me. Unsure? Test it.
The image should help a 77-year-old newcomer understand why the joke is funny and why the philosophy
uses the character as a grounding symbol.
"""


def load_candidates(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Candidate manifest must be a non-empty JSON list")
    required = {"id", "label", "image_url", "provenance_url"}
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for raw in data:
        if not isinstance(raw, dict) or not required.issubset(raw):
            raise ValueError(f"Candidate missing required fields: {raw!r}")
        item = {str(k): str(v) for k, v in raw.items()}
        if item["id"] in seen:
            raise ValueError(f"Duplicate candidate id: {item['id']}")
        seen.add(item["id"])
        out.append(item)
    return out


def fetch_image(url: str, timeout: int = 30) -> tuple[bytes, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 ChadGrounding/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()

    if len(data) < MIN_IMAGE_BYTES:
        raise ValueError(f"Image suspiciously small: {len(data)} bytes")

    if data.startswith(b"\xff\xd8\xff"):
        magic = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        magic = "image/png"
    else:
        raise ValueError("Candidate must resolve to JPEG or PNG bytes")

    if content_type and content_type not in {magic, "application/octet-stream"}:
        raise ValueError(f"HTTP Content-Type {content_type!r} disagrees with bytes {magic!r}")
    return data, magic


def parse_score(text: str) -> dict[str, Any]:
    import re

    stripped = text.strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.I | re.S).strip()
    try:
        obj = json.loads(fenced)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", fenced, flags=re.S)
        if not match:
            return {"parse_error": "no JSON object"}
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            return {"parse_error": str(exc)}

    fields = ("semantic_fit", "newcomer_clarity", "meme_recognizability", "confidence")
    parsed: dict[str, Any] = {}
    errors: list[str] = []
    for field in fields:
        try:
            value = float(obj.get(field))
            if not 0 <= value <= 100:
                raise ValueError
            parsed[field] = value
        except (TypeError, ValueError):
            errors.append(f"invalid {field}: {obj.get(field)!r}")
            parsed[field] = None

    reason = obj.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append("invalid reason")
        reason = None
    parsed["reason"] = reason
    parsed["parse_error"] = "; ".join(errors) if errors else None

    if not errors:
        parsed["grounding_score"] = round(
            (
                parsed["semantic_fit"]
                + parsed["newcomer_clarity"]
                + parsed["meme_recognizability"]
            )
            / 3,
            3,
        )
    else:
        parsed["grounding_score"] = None
    return parsed


def call_model(
    model: dict[str, Any],
    candidate: dict[str, str],
    data_url: str,
    *,
    max_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    model_id = str(model["id"])
    user_prompt = (
        PHILOSOPHY_BRIDGE
        + "\n\nCandidate label: "
        + candidate["label"]
        + "\nScore this candidate only. Return only the requested JSON object."
    )
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0,
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
    return {
        "model": model_id,
        "resolved_model": body.get("model"),
        "elapsed_seconds": round(time.time() - started, 3),
        "response_text": text,
        "usage": body.get("usage"),
        "finish_reason": choice.get("finish_reason"),
        "score": parse_score(text),
        "error": None,
    }


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(path: Path, candidates: list[dict[str, str]], model_count: int) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("error"):
            continue
        score = row.get("score") or {}
        if score.get("parse_error"):
            continue
        grouped[str(row["candidate"]["id"])].append(score)

    summaries: list[dict[str, Any]] = []
    by_id = {c["id"]: c for c in candidates}
    for cid, candidate in by_id.items():
        scores = grouped.get(cid, [])
        valid = len(scores)
        coverage = valid / model_count if model_count else 0.0
        summary: dict[str, Any] = {
            "candidate": candidate,
            "valid_votes": valid,
            "model_count": model_count,
            "coverage": round(coverage, 3),
            "eligible_for_ranking": coverage >= 0.5,
        }
        for field in (
            "semantic_fit",
            "newcomer_clarity",
            "meme_recognizability",
            "grounding_score",
        ):
            values = [float(s[field]) for s in scores if s.get(field) is not None]
            summary[f"median_{field}"] = (
                round(statistics.median(values), 3) if values else None
            )
            summary[f"mean_{field}"] = (
                round(statistics.fmean(values), 3) if values else None
            )
        summaries.append(summary)

    ranked = sorted(
        (s for s in summaries if s["eligible_for_ranking"] and s["median_grounding_score"] is not None),
        key=lambda s: (-float(s["median_grounding_score"]), str(s["candidate"]["id"])),
    )
    return {
        "schema_version": 1,
        "purpose": "semantic grounding only; rights/provenance are not decided by model vote",
        "model_count": model_count,
        "total_calls": len(rows),
        "candidate_summaries": summaries,
        "ranked_candidate_ids": [s["candidate"]["id"] for s in ranked],
        "winner": ranked[0]["candidate"] if ranked else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-models", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=180)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.max_models not in {4, 8, 12}:
        raise ValueError("--max-models must be 4, 8, or 12")
    if not 1 <= args.max_tokens <= 512:
        raise ValueError("--max-tokens must be between 1 and 512")

    candidates = load_candidates(args.candidates)
    if len(candidates) * args.max_models > 48:
        raise ValueError("Poll is capped at 48 model-image calls")

    prepared: list[tuple[dict[str, str], str]] = []
    print("Candidate preflight:")
    for candidate in candidates:
        data, mime = fetch_image(candidate["image_url"])
        print(
            f"  {candidate['id']}: bytes={len(data)} mime={mime} "
            f"source={candidate['provenance_url']}"
        )
        prepared.append((candidate, wheel.image_data_url(data, mime)))

    models = wheel.select_models(
        wheel.fetch_models(require_key=False),
        args.max_models,
        allow_paid=False,
        include_specialized=False,
    )
    print(f"Selected {len(models)} concrete zero-priced image-to-text model(s):")
    for model in models:
        print(f"  {model['id']}")

    if args.dry_run:
        return 0
    if not models:
        raise RuntimeError("No matching free concrete image-capable models found")
    if args.out.exists():
        raise FileExistsError(f"Refusing to append to existing output: {args.out}")

    call_n = 0
    total = len(models) * len(prepared)
    for model in models:
        for candidate, data_url in prepared:
            call_n += 1
            print(f"[{call_n}/{total}] {model['id']} -> {candidate['id']}", flush=True)
            row = {
                "schema_version": 1,
                "question": PHILOSOPHY_BRIDGE,
                "candidate": candidate,
                "selection": {
                    "free": wheel.is_free(model),
                    "specialized": wheel.is_specialized(model),
                },
                **call_model(
                    model,
                    candidate,
                    data_url,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                ),
            }
            append_jsonl(args.out, row)
            if call_n != total:
                time.sleep(args.sleep)

    summary = summarize(args.out, candidates, len(models))
    summary_path = args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.out} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
