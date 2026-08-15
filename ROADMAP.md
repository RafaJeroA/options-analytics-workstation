# Options Analytics Workstation roadmap

The roadmap separates completed v0.1 work from planned improvements.

## v0.1 research beta

- [x] Typed FastAPI/Pydantic API with actionable financial validation.
- [x] European Black–Scholes pricing with continuous dividend yield, negative-rate support, Greeks, and bounded implied-volatility solving.
- [x] Exact piecewise-linear expiry payoff metrics with bounded/unbounded risk states and analytical breakevens.
- [x] Deterministic synthetic market data for multiple underlyings, five expirations, skew, term structure, liquidity fields, and partial/error fixtures.
- [x] Option-chain search, expiration selection, filtering, contract inspection, and explicit data-quality/provenance labels.
- [x] Multi-leg strategy construction, standard templates, payoff chart, and spot/volatility/time scenarios.
- [x] Local watchlist, settings, recent-chain, and saved-strategy persistence.
- [x] Saved-strategy save/list/load/delete workflow.
- [x] Deterministic IBKR adapter contract and lifecycle tests, with real-data tests skipped by default.
- [x] Clean backend wheel discovery/install smoke test and backend/frontend CI definitions.
- [x] Documented model assumptions, limitations, architecture, and validation procedures.

## Post-v0.1 validation and quality

- [ ] Complete the read-only IBKR validation matrix with subscribed market data.
- [ ] Publish sanitized evidence for live, delayed, frozen, permission-limited, and outside-hours behavior.
- [ ] Add a maintained automated browser regression for the deterministic mock workflow.
- [ ] Add accessibility and keyboard-navigation audits.
- [ ] Add portfolio-free strategy import/export using a documented local file format.
- [ ] Evaluate American-style and discrete-dividend pricing models as an explicitly separate model family.
- [ ] Expand representative index/ETF contract fixtures after verified broker observations.

## Explicit non-goals

- [ ] Order submission or routing — intentionally not planned for this research beta.
- [ ] Account, portfolio, position, margin, or execution access — intentionally out of scope.
- [ ] Claims of profitability, investment performance, execution quality, or superiority over broker software.
