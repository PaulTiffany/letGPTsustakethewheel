#!/usr/bin/env python3
from pathlib import Path
import json, re

p = Path('chad_raster.py')
s = p.read_text()

ledger = '''PUBLISHED_MODELS = {
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
}
HARD_BLOCKED_MODELS = {
    "sourceful/riverflow-v2-fast",
    "recraft/recraft-v4-vector",
}
# Attempted but not yet publication-grade: semantic miss, text/symbol leakage,
# or provider failure. These are fallback rerolls only after untouched models.
REROLL_MODELS = {
    "google/gemini-2.5-flash-image",
    "google/gemini-3-pro-image",
    "openai/gpt-image-1",
    "black-forest-labs/flux.2-klein-4b",
    "black-forest-labs/flux.2-max",
}
EXCLUDED_MODELS = (PUBLISHED_MODELS - REROLL_MODELS) | HARD_BLOCKED_MODELS
EXCLUDED_AUTHORS = {"sourceful"}
'''

s, n = re.subn(
    r'PUBLISHED_MODELS = \{.*?EXCLUDED_AUTHORS = \{"sourceful"\}\n',
    ledger,
    s,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit(f'ledger replacement count={n}; refusing blind patch')

estimates = '''TOKEN_MODEL_ESTIMATES = {
    # Previously attempted token-billed models retained for rerolls.
    "google/gemini-2.5-flash-image": 0.06,
    "google/gemini-3.1-flash-lite-image": 0.06,
    "openai/gpt-image-1-mini": 0.08,
    "google/gemini-3.1-flash-image": 0.12,
    "openai/gpt-image-2": 0.18,
    "google/gemini-3-pro-image": 0.20,
    "openai/gpt-image-1": 0.22,

    # Untouched frontier IDs: conservative one-image planning ceilings, not
    # claims about exact billing. Actual OpenRouter usage cost is recorded.
    "microsoft/mai-image-2.5": 0.15,
    "microsoft/mai-image-2.5-pro": 0.18,
    "openai/gpt-5-image-mini": 0.08,
    "openai/gpt-5-image": 0.30,
    "openai/gpt-5.4-image-2": 0.20,
    "google/gemini-3.1-flash-image-preview": 0.12,
    "google/gemini-3-pro-image-preview": 0.20,
}
'''

s, n = re.subn(
    r'TOKEN_MODEL_ESTIMATES = \{.*?\n\}\n\n\ndef headers',
    estimates + '\n\ndef headers',
    s,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit(f'estimate replacement count={n}; refusing blind patch')

p.write_text(s)

lines = [
  {
    "id": "capability-not-permission",
    "section": "Capability is not permission",
    "line": "Capability is not permission.",
    "brief": "A powerful autonomous machine reaches a heavy physical barrier whose lock and release mechanism sit outside its workspace in a calm human operator's hands; increased capability cannot move or control the gate."
  },
  {
    "id": "test-not-assurance",
    "section": "Reality gets the final vote",
    "line": "A test is better than an assurance.",
    "brief": "A confident presenter gestures beside a pristine component while Chad quietly places an identical component in a real load-testing rig; the physical test, not persuasion, determines what happens. No placards or printed words."
  },
  {
    "id": "change-mind",
    "section": "Reality gets the final vote",
    "line": "If the world proves you wrong, change your mind.",
    "brief": "Chad calmly sets aside a failed mechanical design after its real prototype breaks and immediately works from the visibly better successful configuration beside it; no shame, debate, or drama."
  },
  {
    "id": "mechanical-checks",
    "section": "Intelligence has a Jevons problem",
    "line": "Mechanical checks should become cheap wherever we can make them cheap.",
    "brief": "Many inexpensive identical go-no-go fixtures rapidly check a stream of physical parts before they proceed, while only unusual exceptions reach the calm human operator. No logos or instrument lettering."
  },
  {
    "id": "rest-delegation",
    "section": "Know when to stop",
    "line": "Rest, delegation, and asking for help are not failures of seriousness.",
    "brief": "Chad deliberately hands a tool and responsibility to a capable teammate, steps aside to drink water and recover, while shared work continues smoothly without heroic overextension."
  },
  {
    "id": "truth-not-winning",
    "section": "Reality gets the final vote",
    "line": "The point is not to win arguments. The point is to find out what is actually true.",
    "brief": "A debate podium and shiny trophy sit ignored in the background while Chad and another person calmly inspect the decisive physical result of a real experiment together."
  },
  {
    "id": "ideas-meet-reality",
    "section": "A good idea must be allowed to fail",
    "line": "Chad philosophy does not protect ideas from reality.",
    "brief": "Chad removes protective padding from his own prototype and places it into a real stress-testing machine, willingly exposing the idea to a test that can genuinely break it."
  },
  {
    "id": "recoverable-progress",
    "section": "Leave room to be wrong",
    "line": "Chad philosophy therefore prefers recoverable progress over heroic overextension.",
    "brief": "Chad advances a difficult build in stable supported stages with a safety line and spare capacity while an overloaded unsupported shortcut visibly collapses nearby; progress remains recoverable."
  },
  {
    "id": "authorized-gate",
    "section": "Capability is not permission",
    "line": "No high-consequence actuator without an independently authorized gate in its causal past that can still say no.",
    "brief": "A powerful industrial actuator is physically downstream of a separate locked mechanical gate controlled from outside its workspace; the gate can block motion even while the actuator remains fully capable."
  },
  {
    "id": "brake-engine-path",
    "section": "Keep the stop path outside the failure",
    "line": "Do not put the brake on the same failure path as the engine.",
    "brief": "An engine-side cable bundle is visibly failing and sparking while a completely separate simple mechanical brake linkage follows an isolated route to the calm operator and remains usable."
  },
  {
    "id": "strongest-criticism",
    "section": "Do not invent villains",
    "line": "When testing an idea, use the strongest reasonable criticism you can find.",
    "brief": "Chad tests his own bridge-like structure against the heaviest realistic load it should survive instead of a tiny harmless load, welcoming the strongest fair challenge rather than a straw target."
  },
  {
    "id": "comfortable-way-wrong",
    "section": "Build tools that can disagree with you",
    "line": "If everything around you is designed to agree with you, you have built a very comfortable way to become wrong.",
    "brief": "Several decorative flattering instruments all point reassuringly the same way while one plain independent calibrated physical gauge contradicts them; Chad trusts and investigates the dissenting measurement. No lettering."
  }
]
Path('chad_lines.json').write_text(json.dumps(lines, indent=2) + '\n')
