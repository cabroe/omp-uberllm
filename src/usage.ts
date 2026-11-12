/**
 * UberLLM's prepaid balance as an omp usage report: `GET /v1/balance` answers
 * `{available_usd, balance_usd, held_usd, saved_24h_usd}` for the key's account.
 *
 * The balance is account-wide, not per key, so the limit is marked `scope.shared`: two keys of one
 * account report the same pool, and consumers collapse it instead of summing.
 */

import type { UsageFetchContext, UsageFetchParams, UsageLimit, UsageProvider, UsageReport } from "@oh-my-pi/pi-ai";
import { BASE_URL, PROVIDER } from "./catalog";

const BALANCE_PATH = "/balance";

function usd(value: unknown): number | undefined {
	return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

async function fetchUberllmUsage(params: UsageFetchParams, ctx: UsageFetchContext): Promise<UsageReport | null> {
	if (params.provider !== PROVIDER) return null;
	const credential = params.credential;
	if (credential.type !== "api_key" || !credential.apiKey) return null;
	const url = `${(params.baseUrl ?? BASE_URL).replace(/\/+$/, "")}${BALANCE_PATH}`;

	let payload: unknown;
	try {
		const response = await ctx.fetch(url, {
			headers: { Authorization: `Bearer ${credential.apiKey}`, Accept: "application/json" },
			signal: params.signal,
		});
		if (!response.ok) {
			// A rejected key must invalidate a cached balance instead of serving it again; `null` is
			// the transient path. 401/403 reads as a credential failure to the auth layer.
			ctx.logger?.warn(`UberLLM balance returned ${response.status} ${response.statusText}`.trim());
			return null;
		}
		payload = await response.json();
	} catch (error) {
		ctx.logger?.warn("UberLLM balance fetch failed", { error: String(error) });
		return null;
	}

	if (typeof payload !== "object" || payload === null) return null;
	const available = "available_usd" in payload ? usd(payload.available_usd) : undefined;
	if (available === undefined) return null;
	const total = "balance_usd" in payload ? usd(payload.balance_usd) : undefined;
	const held = "held_usd" in payload ? usd(payload.held_usd) : undefined;
	const saved = "saved_24h_usd" in payload ? usd(payload.saved_24h_usd) : undefined;

	// Remaining-only, like the API states it: synthesizing a total would misreport every top-up.
	const limit: UsageLimit = {
		id: "uberllm:balance",
		label: "UberLLM balance",
		scope: { provider: params.provider, windowId: "balance", shared: true },
		amount: { remaining: available, unit: "usd" },
		notes: [
			...(total === undefined ? [] : [`Account total $${total.toFixed(2)}`]),
			...(held === undefined || held === 0 ? [] : [`Held $${held.toFixed(2)}`]),
			...(saved === undefined || saved === 0 ? [] : [`Saved $${saved.toFixed(2)} against list prices in 24 h`]),
		],
	};

	return {
		provider: params.provider,
		fetchedAt: Date.now(),
		limits: [limit],
		metadata: { endpoint: url },
		raw: payload,
	};
}

export const uberllmUsageProvider: UsageProvider = {
	id: PROVIDER,
	// Own shape, own cache: a process without this extension must never serve these reports.
	cacheVersion: 1,
	supports: params => params.provider === PROVIDER && params.credential.type === "api_key",
	validatesCredentials: true,
	fetchUsage: fetchUberllmUsage,
};
