import { api, ApiError, __resetApiInflightRequestsForTests } from "@/lib/api";

const strategy = {
  name: "Long Call",
  underlying_symbol: "SPY",
  underlying_price: 500,
  legs: [],
};

const assumptions = {
  underlying_price: 500,
  risk_free_rate: 0.04,
  dividend_yield: 0,
  volatility_shift: 0,
  days_forward: 0,
};

beforeEach(() => {
  __resetApiInflightRequestsForTests();
});

afterEach(() => {
  __resetApiInflightRequestsForTests();
  vi.unstubAllGlobals();
});

test("identical in-flight pricing requests reuse a single POST", async () => {
  let resolveResponse: ((value: Response) => void) | undefined;
  const fetchMock = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        resolveResponse = resolve;
      })
  );

  vi.stubGlobal("fetch", fetchMock);

  const firstRequest = api.priceStrategy(strategy, assumptions);
  const secondRequest = api.priceStrategy(strategy, assumptions);

  expect(fetchMock).toHaveBeenCalledTimes(1);

  resolveResponse?.(
    new Response(
      JSON.stringify({
        strategy_name: "Long Call",
        underlying_symbol: "SPY",
        assumptions,
        net_debit_credit: -100,
        entry_cost: 100,
        current_value: 110,
        theoretical_value: 108,
        pnl_open: 10,
        max_profit: null,
        max_loss: -100,
        max_profit_state: "unlimited",
        max_loss_state: "finite",
        breakevens: [501],
        breakeven_intervals: [],
        payoff: [],
        legs: [],
        pricing_state: "complete",
        status_message: null,
        warnings: [],
      }),
      {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }
    )
  );

  const [firstResult, secondResult] = await Promise.all([firstRequest, secondRequest]);

  expect(firstResult).toEqual(secondResult);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("validation responses become actionable typed errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify({ detail: [{ loc: ["body", "strategy", "underlying_price"], msg: "must be greater than 0" }] }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      })
    )
  );

  await expect(api.priceStrategy(strategy, assumptions)).rejects.toMatchObject({
    name: "ApiError",
    kind: "validation",
    status: 422,
    retryable: false,
    message: "strategy.underlying_price: must be greater than 0",
  } satisfies Partial<ApiError>);
});

test("network failures are retryable transport errors", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("connection refused"))));

  await expect(api.getUnderlyingSummary("SPY")).rejects.toMatchObject({
    kind: "transport",
    retryable: true,
  } satisfies Partial<ApiError>);
});
