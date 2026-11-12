# omp-uberllm

[UberLLM](https://uberllm.dev) as a model provider for [omp](https://github.com/can1357/oh-my-pi),
shipped as an omp extension (`src/`). It registers provider `uberllm` with the live `/v1/models`
roster, the billed prices and the prepaid balance in `/usage`.

## Install

`omp plugin install` takes the repository as a git source; the ref is optional.

| Source | Command | Installs to |
| --- | --- | --- |
| Git shorthand, optionally pinned | `omp plugin install 'github:cabroe/omp-uberllm#v0.2.0'` | user plugin directory (`~/.omp/plugins`) |
| Full Git URL | `omp plugin install 'https://github.com/cabroe/omp-uberllm.git#v0.2.0'` | user plugin directory (`~/.omp/plugins`) |

The `#v0.2.0` ref pins that tag; any tag, branch or commit id works, and leaving it off installs
the default branch:

```sh
omp plugin install github:cabroe/omp-uberllm
```

bun fetches a GitHub source as a tarball from the forge, without git's credentials, so a private
fork cannot be installed this way (upstream: [bun#19618](https://github.com/oven-sh/bun/issues/19618)).
For one, install the local checkout: `omp plugin install ./path/to/checkout`.

Provider `uberllm` is an API-key provider, so `omp login` does not list it — that command covers OAuth
providers only. The extension reads its key from `UBERLLM_API_KEY`, taken from the shell or from
`~/.omp/agent/.env`, which omp loads; a non-empty shell variable outranks the file:

```sh
printf 'UBERLLM_API_KEY=%s\n' "$KEY" >> ~/.omp/agent/.env
```

The registration bundles the generated roster as its static fallback and refreshes it from the
catalog at session start; `fetchDynamicModels` runs under omp's 15-second bound, so the bundled rows
stay selectable if the catalog is down.

## Use

```sh
omp --model uberllm/deepseek/deepseek-v4.1-flash-1017
omp --model uberllm/anthropic/claude-sonnet-5.5
omp config set modelRoles.default uberllm/deepseek/deepseek-v4.1-flash-1017
```

Inside a session, `/model uberllm` opens the provider's list and `/usage` shows the prepaid balance
(`GET /v1/balance`, account-wide, marked `shared` so two keys of one account are not summed).

## Wire

One API covers the catalog: every `/v1/models` row lists `/v1/chat/completions`, Claude included, so
`api: openai-completions` serves all of them. UberLLM also exposes `/v1/messages`, but an extension
registration cannot force API-key shaping for `anthropic-messages`, and the gateway's own caching
does not need it — the plugin would only lose tools if it switched.

## What is left out, and why

| Rows | Example | Reason |
| --- | --- | --- |
| tool-free models (11) | `google/gemma-3-27b-it`, `venice/uncensored` | omp always sends tools. Such a model does not refuse: `google/gemma-3-27b-it` answered "completed successfully by using the bash tool" without a single call. |
| `:variant` ids (5) | `anthropic/claude-haiku-5.5:batch`, `z-ai/glm-5:web` | omp reads `model:effort` as a thinking-level variant (`deepseek-v4-flash:high`), so a colon inside an id would shadow the real row. |
| `decisions`-output models (3) | `typesafe/jev-1.14` | Output modality is not text. |
| `available: false` rows | — | The gateway refuses them. |
| rows without limits (3) | — | omp requires a positive `contextWindow` and `maxTokens`. |

## Regenerate

```sh
python3 scripts/generate.py            # rewrite models.yml and src/catalog.generated.ts
python3 scripts/generate.py --check    # exit 1 when either file is stale
```

The catalog is public, no key needed. `--source catalog.json` reads a saved copy. Both artifacts are
sorted by id, so a regeneration that changes nothing produces no diff. `src/catalog.ts` carries the
same filter and price conversion for live discovery — change both when the catalog schema moves.

## Costs

`cost` is the **billed** rate per 1M tokens (`prompt`/`completion`/`input_cache_read`/
`input_cache_write` × 1e6), not `list_*_usd`. Two catalog rows leak their per-token rate into
`*_usd`, so both the script and the extension prefer the per-token fields. omp's schema requires all
four values; a partial `cost` block disables every custom provider with a schema error.

## Verify

```sh
python3 scripts/generate.py --check
omp plugin doctor omp-uberllm
omp -p --no-session --model uberllm/deepseek/deepseek-v4.1-flash-1017 "Reply with exactly: ok"
```

## License

MIT — see [LICENSE](LICENSE).
