import type {
  ChainSnapshot,
  RecentChainView,
  SavedStrategyRecord,
  ScenarioGridResult,
  ScenarioInput,
  StrategyDefinition,
  StrategyValuation,
  UnderlyingQuote,
  UnderlyingSearchResult,
  UserSettings,
  VolSurfacePoint,
  TermStructurePoint,
  WatchlistItem,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const inFlightJsonRequests = new Map<string, Promise<unknown>>();

export type ApiErrorKind = "validation" | "permission" | "not_found" | "unavailable" | "transport" | "server";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly kind: ApiErrorKind,
    public readonly status?: number,
    public readonly retryable = false
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function responseErrorKind(status: number): ApiErrorKind {
  if (status === 422 || status === 400) return "validation";
  if (status === 401 || status === 403) return "permission";
  if (status === 404) return "not_found";
  if (status === 408 || status === 429 || status === 502 || status === 503 || status === 504) return "unavailable";
  return "server";
}

function responseErrorMessage(status: number, body: string) {
  if (!body) return `API request failed with status ${status}.`;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      const messages = parsed.detail
        .map((item) => {
          if (!item || typeof item !== "object") return undefined;
          const error = item as { loc?: unknown[]; msg?: unknown };
          const location = Array.isArray(error.loc) ? error.loc.filter((part) => part !== "body").join(".") : "request";
          return typeof error.msg === "string" ? `${location || "request"}: ${error.msg}` : undefined;
        })
        .filter(Boolean);
      if (messages.length) return messages.join(" ");
    }
  } catch {
    // Do not surface arbitrary HTML or server output in the workstation.
  }
  return `API request failed with status ${status}.`;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? `Cannot reach the local API: ${error.message}` : "Cannot reach the local API.",
      "transport",
      undefined,
      true
    );
  }

  if (!response.ok) {
    const detail = await response.text();
    const kind = responseErrorKind(response.status);
    throw new ApiError(
      responseErrorMessage(response.status, detail),
      kind,
      response.status,
      kind === "transport" || kind === "unavailable" || kind === "server"
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("The local API returned malformed JSON.", "server", response.status, true);
  }
}

export function apiErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

export function apiErrorLabel(error: unknown) {
  if (!(error instanceof ApiError)) return "Unavailable";
  const labels: Record<ApiErrorKind, string> = {
    validation: "Validation failed",
    permission: "Permission or subscription required",
    not_found: "Not found",
    unavailable: "Service unavailable",
    transport: "Connection unavailable",
    server: "Server error",
  };
  return labels[error.kind];
}

export function isRetryableApiError(error: unknown) {
  return error instanceof ApiError && error.retryable;
}

function dedupedJsonRequest<T>(path: string, init: RequestInit & { body: string }) {
  const method = init.method ?? "GET";
  const requestKey = `${method} ${path} ${init.body}`;
  const inFlight = inFlightJsonRequests.get(requestKey);
  if (inFlight) {
    return inFlight as Promise<T>;
  }

  const request = apiFetch<T>(path, init).finally(() => {
    if (inFlightJsonRequests.get(requestKey) === request) {
      inFlightJsonRequests.delete(requestKey);
    }
  });
  inFlightJsonRequests.set(requestKey, request);
  return request;
}

export function __resetApiInflightRequestsForTests() {
  inFlightJsonRequests.clear();
}

export const api = {
  searchUnderlyings(query: string) {
    return apiFetch<UnderlyingSearchResult[]>(`/underlyings/search?q=${encodeURIComponent(query)}`);
  },
  getUnderlyingSummary(symbol: string) {
    return apiFetch<UnderlyingQuote>(`/underlyings/${encodeURIComponent(symbol)}/summary`);
  },
  getChain(symbol: string, expiration?: string) {
    const params = expiration ? `?expiration=${encodeURIComponent(expiration)}` : "";
    return apiFetch<ChainSnapshot>(`/underlyings/${encodeURIComponent(symbol)}/chains${params}`);
  },
  getVolSkew(symbol: string, expiration?: string) {
    const params = new URLSearchParams({ symbol });
    if (expiration) {
      params.set("expiration", expiration);
    }
    return apiFetch<VolSurfacePoint[]>(`/volatility/skew?${params.toString()}`);
  },
  getTermStructure(symbol: string) {
    return apiFetch<TermStructurePoint[]>(`/volatility/term-structure?symbol=${encodeURIComponent(symbol)}`);
  },
  getWatchlist() {
    return apiFetch<WatchlistItem[]>("/watchlist");
  },
  addWatchlist(symbol: string, note?: string) {
    return apiFetch<WatchlistItem>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ symbol, note }),
    });
  },
  getRecentChains() {
    return apiFetch<RecentChainView[]>("/workspace/recent-chains");
  },
  getUserSettings() {
    return apiFetch<UserSettings>("/workspace/settings");
  },
  saveUserSettings(settings: UserSettings) {
    return apiFetch<UserSettings>("/workspace/settings", {
      method: "PUT",
      body: JSON.stringify({ settings }),
    });
  },
  getSavedStrategies() {
    return apiFetch<SavedStrategyRecord[]>("/workspace/strategies");
  },
  saveStrategyDefinition(strategy: StrategyDefinition, name: string, strategyId?: string) {
    return apiFetch<SavedStrategyRecord>("/workspace/strategies", {
      method: "POST",
      body: JSON.stringify({ strategy_id: strategyId, name, strategy }),
    });
  },
  deleteSavedStrategy(strategyId: string) {
    return apiFetch<{ deleted: boolean }>(`/workspace/strategies/${encodeURIComponent(strategyId)}`, {
      method: "DELETE",
    });
  },
  priceStrategy(strategy: StrategyDefinition, assumptions: object) {
    const body = JSON.stringify({ strategy, assumptions });
    return dedupedJsonRequest<StrategyValuation>("/strategies/price", {
      method: "POST",
      body,
    });
  },
  scenarioGrid(strategy: StrategyDefinition, scenario: ScenarioInput) {
    const body = JSON.stringify({ strategy, scenario });
    return dedupedJsonRequest<ScenarioGridResult>("/strategies/scenario-grid", {
      method: "POST",
      body,
    });
  },
};

export function websocketUrl(path: string) {
  const base = new URL(API_BASE_URL);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  return new URL(path, `${protocol}//${base.host}`).toString();
}
