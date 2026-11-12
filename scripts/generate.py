#!/usr/bin/env python3
"""Write models.yml for the UberLLM gateway from its public /v1/models catalog.

omp reads custom providers from the agent directory's models.yml (``~/.omp/agent/models.yml``). This
emits one ``uberllm`` provider with a row per chat model: the catalog's own context window, output
cap, modalities and reasoning flag, plus the billed prices per 1M tokens.

    python3 scripts/generate.py               # rewrite models.yml
    python3 scripts/generate.py --check       # exit 1 when the committed file is stale
    python3 scripts/generate.py --source cat.json   # read a saved catalog instead of the network

The catalog is public; no key is needed. Output is deterministic (models sorted by id).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

CATALOG_URL = "https://api.uberllm.dev/v1/models"
BASE_URL = "https://api.uberllm.dev/v1"
ROOT = Path(__file__).resolve().parents[1]

HEADER = [
    "# UberLLM gateway (https://api.uberllm.dev/v1), generated from the public /v1/models catalog.",
    "# One row per chat model that advertises tool support, with the catalog's own limits and the",
    "# billed prices per 1M tokens (prompt/completion/input_cache_* x 1e6, not the list prices).",
    "# Regenerate with `python3 scripts/generate.py`; models whose id carries a ':variant' suffix and",
    "# models without tool support are left out on purpose (see README).",
    "providers:",
    "   uberllm:",
    f"      baseUrl: {BASE_URL}",
    "      api: openai-completions",
    "      apiKey: UBERLLM_API_KEY",
    "      models:",
]


def keep(model: dict) -> bool:
    """Rows omp can run as a coding model: text out, tools, and no effort-variant suffix."""
    return (
        model.get("available") is not False
        and "text" in (model.get("output_modalities") or [])
        and ":" not in model["id"]
        and bool(model.get("supports_tools"))
    )


def rate(model: dict, per_token: str, per_million: str) -> float:
    """Billed USD per 1M tokens. The catalog's per-token fields are authoritative; two rows leaked
    their per-token rate into the ``*_usd`` field, so that only serves as a fallback."""
    pricing = model.get("pricing") or {}
    if pricing.get(per_token) not in (None, ""):
        return round(float(pricing[per_token]) * 1_000_000, 6)
    if pricing.get(per_million) not in (None, ""):
        return round(float(pricing[per_million]), 6)
    return 0.0


def render(models: list[dict]) -> str:
    lines = list(HEADER)
    for model in models:
        image = ["image"] if model.get("supports_vision") else []
        lines += [
            f"         - id: {json.dumps(model['id'])}",
            f"           name: {json.dumps(model.get('display_name') or model['id'])}",
            f"           reasoning: {'true' if model.get('supports_reasoning') else 'false'}",
            f"           input: [{', '.join(['text', *image])}]",
        ]
        if (model.get("context_length") or 0) > 0:
            lines.append(f"           contextWindow: {int(model['context_length'])}")
        if (model.get("max_output_tokens") or 0) > 0:
            lines.append(f"           maxTokens: {int(model['max_output_tokens'])}")
        lines += [
            "           cost:",
            f"              input: {rate(model, 'prompt', 'input_usd')}",
            f"              output: {rate(model, 'completion', 'output_usd')}",
            f"              cacheRead: {rate(model, 'input_cache_read', 'cache_read_usd')}",
            f"              cacheWrite: {rate(model, 'input_cache_write', 'cache_write_usd')}",
        ]
    return "\n".join(lines) + "\n"


def load_catalog(source: Path | None) -> list[dict]:
    if source is not None:
        payload = json.loads(source.read_text(encoding="utf-8"))
    else:
        request = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "omp-uberllm-generate"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"no models in {source or CATALOG_URL}")
    return [row for row in rows if keep(row)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "models.yml", help="target file")
    parser.add_argument("--source", type=Path, help="saved catalog JSON instead of the network")
    parser.add_argument("--check", action="store_true", help="compare instead of writing (exit 1 when stale)")
    args = parser.parse_args(argv)

    models = sorted(load_catalog(args.source), key=lambda m: m["id"])
    text = render(models)

    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current == text:
            print(f"{args.out} is current ({len(models)} models)")
            return 0
        print(f"{args.out} is stale: catalog has {len(models)} models, file has "
              f"{current.count('         - id:')}", file=sys.stderr)
        print("run: python3 scripts/generate.py", file=sys.stderr)
        return 1

    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(models)} models)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
