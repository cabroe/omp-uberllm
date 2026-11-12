#!/usr/bin/env python3
"""Write the UberLLM provider artifacts from the gateway's public /v1/models catalog.

Two files come out of one catalog read, so they cannot drift:

* ``models.yml`` — the config-only provider, for runs without extensions.
* ``src/catalog.generated.ts`` — the same rows bundled into the extension as its static fallback.

    python3 scripts/generate.py                    # rewrite both
    python3 scripts/generate.py --check            # exit 1 when either file is stale
    python3 scripts/generate.py --source cat.json  # read a saved catalog instead of the network

The catalog is public; no key is needed. Output is sorted by id, so a regeneration that changes
nothing produces no diff. Row selection and price conversion mirror ``src/catalog.ts``.
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
MODELS_YML = ROOT / "models.yml"
CATALOG_TS = ROOT / "src" / "catalog.generated.ts"


def keep(row: dict) -> bool:
    """Rows omp can run as a coding model: text out, tools, and no effort-variant suffix."""
    return (
        row.get("available") is not False
        and "text" in (row.get("output_modalities") or [])
        and ":" not in row["id"]
        and bool(row.get("supports_tools"))
    )


def rate(row: dict, per_token: str, per_million: str) -> float:
    """Billed USD per 1M tokens. The per-token fields are authoritative; two rows leaked their
    per-token rate into the ``*_usd`` field, so that only serves as a fallback."""
    pricing = row.get("pricing") or {}
    if pricing.get(per_token) not in (None, ""):
        return round(float(pricing[per_token]) * 1_000_000, 6)
    if pricing.get(per_million) not in (None, ""):
        return round(float(pricing[per_million]), 6)
    return 0.0


def normalize(row: dict) -> dict | None:
    """Catalog row to the shape both artifacts carry, or None when it lacks omp's required limits."""
    context = row.get("context_length") or 0
    max_tokens = row.get("max_output_tokens") or 0
    if context <= 0 or max_tokens <= 0:
        return None
    return {
        "id": row["id"],
        "name": row.get("display_name") or row["id"],
        "reasoning": bool(row.get("supports_reasoning")),
        "input": ["text", *(["image"] if row.get("supports_vision") else [])],
        "contextWindow": int(context),
        "maxTokens": int(max_tokens),
        "cost": {
            "input": rate(row, "prompt", "input_usd"),
            "output": rate(row, "completion", "output_usd"),
            "cacheRead": rate(row, "input_cache_read", "cache_read_usd"),
            "cacheWrite": rate(row, "input_cache_write", "cache_write_usd"),
        },
    }


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
    kept = [normalize(row) for row in rows if keep(row)]
    return sorted((row for row in kept if row is not None), key=lambda row: row["id"])


def render_yaml(models: list[dict]) -> str:
    lines = [
        "# UberLLM gateway (https://api.uberllm.dev/v1), generated from the public /v1/models catalog.",
        "# One row per chat model that advertises tool support, with the catalog's own limits and the",
        "# billed prices per 1M tokens (prompt/completion/input_cache_* x 1e6, not the list prices).",
        "# Regenerate with `python3 scripts/generate.py`; the extension bundles the same rows from",
        "# src/catalog.generated.ts. Models without tool support and ids with a ':variant' suffix are",
        "# left out on purpose (see README).",
        "providers:",
        "   uberllm:",
        f"      baseUrl: {BASE_URL}",
        "      api: openai-completions",
        "      apiKey: UBERLLM_API_KEY",
        "      models:",
    ]
    for model in models:
        lines += [
            f"         - id: {json.dumps(model['id'])}",
            f"           name: {json.dumps(model['name'])}",
            f"           reasoning: {'true' if model['reasoning'] else 'false'}",
            f"           input: [{', '.join(model['input'])}]",
            f"           contextWindow: {model['contextWindow']}",
            f"           maxTokens: {model['maxTokens']}",
            "           cost:",
            f"              input: {model['cost']['input']}",
            f"              output: {model['cost']['output']}",
            f"              cacheRead: {model['cost']['cacheRead']}",
            f"              cacheWrite: {model['cost']['cacheWrite']}",
        ]
    return "\n".join(lines) + "\n"


def render_ts(models: list[dict]) -> str:
    lines = [
        "// Generated by scripts/generate.py from https://api.uberllm.dev/v1/models — do not edit.",
        'import type { UberllmModel } from "./catalog";',
        "",
        "export const CATALOG: UberllmModel[] = [",
    ]
    for model in models:
        cost = model["cost"]
        lines.append(
            f'\t{{ id: {json.dumps(model["id"])}, name: {json.dumps(model["name"])}, '
            f'reasoning: {"true" if model["reasoning"] else "false"}, '
            f'input: [{", ".join(json.dumps(kind) for kind in model["input"])}], '
            f'contextWindow: {model["contextWindow"]}, maxTokens: {model["maxTokens"]}, '
            f'cost: {{ input: {cost["input"]}, output: {cost["output"]}, '
            f'cacheRead: {cost["cacheRead"]}, cacheWrite: {cost["cacheWrite"]} }} }},'
        )
    lines.append("];")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=MODELS_YML, help="models.yml target")
    parser.add_argument("--ts-out", type=Path, default=CATALOG_TS, help="bundled catalog target")
    parser.add_argument("--source", type=Path, help="saved catalog JSON instead of the network")
    parser.add_argument("--check", action="store_true", help="compare instead of writing (exit 1 when stale)")
    args = parser.parse_args(argv)

    models = load_catalog(args.source)
    artifacts = {args.out: render_yaml(models), args.ts_out: render_ts(models)}

    if args.check:
        stale = [path for path, text in artifacts.items()
                 if not path.exists() or path.read_text(encoding="utf-8") != text]
        if not stale:
            print(f"{len(models)} models; {', '.join(str(path.relative_to(ROOT)) for path in artifacts)} are current")
            return 0
        for path in stale:
            print(f"{path.relative_to(ROOT)} is stale", file=sys.stderr)
        print("run: python3 scripts/generate.py", file=sys.stderr)
        return 1

    for path, text in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({len(models)} models)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
