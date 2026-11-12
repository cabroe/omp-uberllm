/**
 * The UberLLM catalog mapping shared by the provider registration and its live discovery.
 *
 * `models.yml` is generated from the same rules by `scripts/generate.py`; that script carries the
 * same four-way filter and price conversion, so keep the two in step when the catalog schema moves.
 *
 * The `/v1/models` payload is remote input, so `parseRow` is the one boundary that turns a row into
 * a typed value — every field is narrowed there, and nothing downstream asserts a shape.
 */

export const PROVIDER = "uberllm";
export const BASE_URL = "https://api.uberllm.dev/v1";
export const KEY_ENV = "UBERLLM_API_KEY";

/** One chat model as omp wants it: limits from the catalog, billed prices per 1M tokens. */
export interface UberllmModel {
	id: string;
	name: string;
	reasoning: boolean;
	input: ("text" | "image")[];
	cost: { input: number; output: number; cacheRead: number; cacheWrite: number };
	contextWindow: number;
	maxTokens: number;
}

/** A catalog row after `parseRow` narrowed everything this plugin reads. */
export interface UberllmRow {
	id: string;
	name: string;
	available: boolean;
	outputs: string[];
	tools: boolean;
	reasoning: boolean;
	vision: boolean;
	contextWindow?: number;
	maxTokens?: number;
	pricing: Record<string, unknown>;
}

function amount(value: unknown): number | undefined {
	const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : Number.NaN;
	return Number.isFinite(n) && n > 0 ? n : undefined;
}

/** Narrow one `/v1/models` row, or `undefined` when it carries no usable id. */
export function parseRow(value: unknown): UberllmRow | undefined {
	if (typeof value !== "object" || value === null) return undefined;
	if (!("id" in value) || typeof value.id !== "string" || value.id.length === 0) return undefined;
	const outputs = "output_modalities" in value && Array.isArray(value.output_modalities)
		? value.output_modalities.filter((entry): entry is string => typeof entry === "string")
		: [];
	const pricing: Record<string, unknown> = {};
	if ("pricing" in value && typeof value.pricing === "object" && value.pricing !== null) {
		for (const [key, entry] of Object.entries(value.pricing)) pricing[key] = entry;
	}
	return {
		id: value.id,
		name: "display_name" in value && typeof value.display_name === "string" && value.display_name.length > 0
			? value.display_name
			: value.id,
		available: !("available" in value) || value.available !== false,
		outputs,
		tools: "supports_tools" in value && value.supports_tools === true,
		reasoning: "supports_reasoning" in value && value.supports_reasoning === true,
		vision: "supports_vision" in value && value.supports_vision === true,
		contextWindow: "context_length" in value ? amount(value.context_length) : undefined,
		maxTokens: "max_output_tokens" in value ? amount(value.max_output_tokens) : undefined,
		pricing,
	};
}

/**
 * Whether a row is a model a coding agent can run.
 *
 * Tool-free models are dropped: omp always sends tools, and such a model does not refuse — it
 * answers as if it had called them. Ids carrying a `:variant` suffix are dropped because omp reads
 * `model:effort` as a thinking-level variant, so the row would shadow the real one.
 */
export function keep(row: UberllmRow): boolean {
	return row.available && !row.id.includes(":") && row.outputs.includes("text") && row.tools;
}

/** Billed USD per 1M tokens: the catalog's per-token field x 1e6, its `*_usd` sibling as fallback. */
function rate(pricing: Record<string, unknown>, perToken: string, perMillion: string): number {
	const token = amount(pricing[perToken]);
	if (token !== undefined) return Math.round(token * 1e12) / 1e6;
	const million = amount(pricing[perMillion]);
	return million === undefined ? 0 : Math.round(million * 1e6) / 1e6;
}

/** Row to model, or `undefined` when the row cannot carry omp's required limits. */
export function fromRow(row: UberllmRow): UberllmModel | undefined {
	if (row.contextWindow === undefined || row.maxTokens === undefined) return undefined;
	return {
		id: row.id,
		name: row.name,
		reasoning: row.reasoning,
		input: row.vision ? ["text", "image"] : ["text"],
		contextWindow: row.contextWindow,
		maxTokens: row.maxTokens,
		cost: {
			input: rate(row.pricing, "prompt", "input_usd"),
			output: rate(row.pricing, "completion", "output_usd"),
			cacheRead: rate(row.pricing, "input_cache_read", "cache_read_usd"),
			cacheWrite: rate(row.pricing, "input_cache_write", "cache_write_usd"),
		},
	};
}

/** Every runnable chat model in a catalog payload (bare array or `{ data: [...] }`), sorted by id. */
export function modelsFromCatalog(payload: unknown): UberllmModel[] {
	const rows: unknown[] = Array.isArray(payload)
		? payload
		: typeof payload === "object" && payload !== null && "data" in payload && Array.isArray(payload.data)
			? payload.data
			: [];
	return rows
		.map(parseRow)
		.filter((row): row is UberllmRow => row !== undefined)
		.filter(keep)
		.map(fromRow)
		.filter((model): model is UberllmModel => model !== undefined)
		.sort((a, b) => a.id.localeCompare(b.id));
}
