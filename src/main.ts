/**
 * UberLLM as an omp provider.
 *
 * One wire API covers the catalog: every `/v1/models` row lists `/v1/chat/completions`, Claude
 * included, so `openai-completions` serves all of them. UberLLM also exposes `/v1/messages`, but
 * that would only buy Anthropic prompt-cache semantics, and an extension registration cannot force
 * API-key shaping for it.
 *
 * `models` is the generated snapshot (a fallback when the network is down); `fetchDynamicModels`
 * refreshes the roster from the catalog, and explicit `models.yml` rows still win over both.
 */

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { BASE_URL, KEY_ENV, PROVIDER, modelsFromCatalog } from "./catalog";
import { CATALOG } from "./catalog.generated";
import { uberllmUsageProvider } from "./usage";

export default function uberllm(pi: ExtensionAPI): void {
	pi.registerProvider(PROVIDER, {
		baseUrl: BASE_URL,
		apiKey: KEY_ENV,
		api: "openai-completions",
		models: CATALOG,
		usage: uberllmUsageProvider,
		async fetchDynamicModels(apiKey) {
			const headers = apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined;
			try {
				const response = await fetch(`${BASE_URL}/models`, { headers });
				if (!response.ok) {
					pi.logger.warn(`uberllm: catalog returned ${response.status} ${response.statusText}`.trim());
					return [];
				}
				return modelsFromCatalog(await response.json());
			} catch (error) {
				// The static rows stay selectable; a dead catalog must not remove the provider.
				pi.logger.warn("uberllm: catalog fetch failed", { error: String(error) });
				return [];
			}
		},
	});
}
