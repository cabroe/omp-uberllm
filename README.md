# omp-uberllm

[UberLLM](https://uberllm.dev) as a model provider for [omp](https://github.com/can1357/oh-my-pi):
225 chat models behind one key, with the gateway's own context windows, output caps, modalities,
reasoning flags and billed prices.

## Install

```sh
mkdir -p ~/.omp/agent
cp models.yml ~/.omp/agent/models.yml
printf 'UBERLLM_API_KEY=ull_…\n' >> ~/.omp/agent/.env
chmod 600 ~/.omp/agent/.env
```

`apiKey: UBERLLM_API_KEY` is an environment-variable reference, not the key: omp resolves a value
that names an exact-case variable to that variable's value, so no secret is in this repo. omp loads
`~/.omp/agent/.env`, `~/.omp/.env`, `~/.env` and `<project>/.env`; a non-empty shell variable wins.

## Use

```sh
omp --model uberllm/deepseek/deepseek-v4.1-flash-1017
omp --model uberllm/anthropic/claude-sonnet-5.5
omp config set modelRoles.default uberllm/deepseek/deepseek-v4.1-flash-1017
```

Inside a session, `/model uberllm` opens the provider's list. Every model is selected as
`uberllm/<catalog id>`, so ids keep their vendor prefix.

## Regenerate

```sh
python3 scripts/generate.py            # rewrite models.yml from https://api.uberllm.dev/v1/models
python3 scripts/generate.py --check    # exit 1 when the committed file is stale
```

The catalog is public, no key needed. `--source catalog.json` reads a saved copy. Output is sorted by
id, so a regeneration that changes nothing produces no diff.

## What is left out, and why

| Rows | Example | Reason |
| --- | --- | --- |
| 11 tool-free models | `google/gemma-3-27b-it`, `venice/uncensored` | omp always sends tools. Such a model does not refuse: it replies as if it had called them — `google/gemma-3-27b-it` answered "completed successfully by using the bash tool" without a single call. |
| 5 `:variant` ids | `anthropic/claude-haiku-5.5:batch`, `z-ai/glm-5:web` | omp reads `model:effort` as a thinking-level variant (`deepseek-v4-flash:high`). A colon inside an id would shadow the real row. |
| 3 decisions-output models | `typesafe/jev-1.14` | Output modality is not text; omp would have to send them as chat. |
| `available: false` rows | — | The gateway refuses them. |

Discovery is deliberately not configured: `discovery: {type: openai-models-list, injectV1: false}`
does list 248 rows with correct limits, but it reports every price as zero and re-adds the `:variant`
ids. A committed list keeps prices and selection exact.

## Notes

- One wire API: every catalog row lists `/v1/chat/completions`, Claude included, so a single
  provider-level `api: openai-completions` covers all of them. UberLLM also serves
  `/v1/messages`; switching Claude to `anthropic-messages` would buy Anthropic prompt-cache
  semantics, not model access.
- `cost` is the **billed** rate per 1M tokens (`prompt`/`completion`/`input_cache_read`/
  `input_cache_write` × 1e6), not `list_*_usd`. Two catalog rows leak their per-token rate into
  `*_usd`, so the script prefers the per-token fields. omp's schema requires all four values;
  a partial `cost` block disables every custom provider with a schema error.
- Limits come from `context_length` / `max_output_tokens`; a row that has neither omits the field
  instead of guessing 128K.

## Verify

```sh
omp models uberllm          # 225 models, context/max-out/thinking/images per row
omp -p --no-session --model uberllm/deepseek/deepseek-v4.1-flash-1017 "Reply with exactly: ok"
```

## License

MIT — see [LICENSE](LICENSE).
