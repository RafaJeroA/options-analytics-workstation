# Known limitations

This document defines the scope of the v0.1 research beta. Options Analytics Workstation is not production trading software.

## Models and analytics

- Local theoretical values use European Black–Scholes with a constant volatility input, continuous risk-free compounding, and continuous dividend yield.
- Many listed US equity and ETF options are American-style. Early exercise, assignment behavior, hard-to-borrow effects, and optimal exercise are not represented by the local European model.
- Discrete dividend dates and amounts are not modeled. A continuous yield is only an approximation and can be materially inadequate around ex-dividend dates.
- Volatility is treated as an input per scenario point; the engine does not implement a dynamic volatility surface, stochastic volatility, jumps, or path dependence.
- Local Greeks are analytical Black–Scholes sensitivities, not broker risk, exchange risk arrays, or portfolio Greeks.
- Expiry payoff metrics intentionally exclude commissions, fees, taxes, slippage, borrow costs, margin, assignment, and exercise mechanics.
- The scenario grid is deterministic and illustrative. It is not a probability forecast, backtest, or investment-performance estimate.
- Mixed-expiration scenarios use a static-shock convention: every already-expired option settles to intrinsic value at the scenario spot, then the settled cash is carried to the horizon at the configured continuously compounded risk-free rate. The engine does not simulate the path or historical settlement spot between leg expirations.

## Market data

- Mock data is synthetic and reproducible. Prices, IV, volume, and open interest do not describe an actual market and must not be used for investment decisions.
- Mock timestamps use an injected fixed valuation clock for repeatability rather than the current wall clock.
- Partial, stale, crossed, and unavailable mock fixtures exist to exercise error states; not every fixture is reachable through every normal UI path.
- A usable automatic option mark requires a valid non-crossed bid/ask pair. A lone last trade is retained but is not promoted to a valid mark.
- Delayed, frozen, and delayed-frozen bid/ask pairs are reference valuation inputs for this research workstation, not claims of a current executable NBBO. Their provenance remains visible and testable.
- Staleness uses an available exchange/market timestamp, never the local receipt clock as a substitute. If IBKR omits a market timestamp, age remains unknown while receipt time is retained separately.
- Modern IBKR size callbacks use decimal values. Integral volume/open-interest values are retained; non-integral values remain unavailable rather than being silently truncated into the workstation's integer liquidity fields.

## Experimental IBKR adapter

- The adapter is covered by deterministic fakes, fixtures, normalized-output tests, ambiguity tests, and lifecycle tests.
- TWS Paper socket connectivity and the API handshake have been validated manually with the official `ibapi 10.45.1` client. A direct read-only EUR/USD CASH IDEALPRO request received live bid, ask, last, high, low, close, price, and size callbacks. This does not validate US-equity or options market data.
- A direct read-only SPY SMART request asked for type `4`; TWS selected type `3` (delayed), but no price callbacks arrived during the observation interval and no fatal connection error was reported. This is retained as delayed provenance with `no_price_callbacks`, not relabelled delayed-frozen and not treated as proof of a subscription error without an actual supporting IBKR error.
- The complete subscribed-data matrix has **not** been validated. Contract tests and the EUR/USD result cannot prove US-equity/options entitlements, field timing, callback ordering, exchange behavior, or production reliability. Delayed SPY data is not guaranteed to be available.
- The official TWS API Python client is an external installation with its own IBKR license. The repository neither vendors it nor installs the obsolete PyPI `ibapi==9.81.1.post1`; base/mock installations therefore cannot validate the official-client decoder path unless the official client is installed separately.
- TWS/IB Gateway versions, API pacing, contract metadata, subscriptions, regional permissions, and market hours can change observed results.
- With delayed mode enabled, the adapter requests type `4`; it then preserves the actual callback state as live, frozen, delayed, or delayed-frozen. Callback-less data remains unconfirmed/unavailable rather than being guessed.
- The smoke helper improves sanitized diagnostics, but its output is not proof of quote freshness, executable liquidity, entitlement completeness, or production reliability.
- The adapter is market-data-only. It must not access accounts, portfolios, positions, margins, orders, executions, or order routing.

## Application and persistence

- The application is local-first and single-user. SQLite writes are not designed for concurrent multi-process use or remote synchronization.
- The primary mock analytics workflow has a deterministic Playwright suite at 1280×800, 1440×900, and 1920×1080. It is a focused desktop workflow, not exhaustive cross-browser, mobile, accessibility, or visual-regression coverage.
- The UI is desktop-workstation oriented and has not received a complete mobile or accessibility certification.
- Backend and frontend are separate local processes. The default CORS configuration expects `http://localhost:3000`.
- GitHub Actions run the backend and frontend validation suites on pushes and pull requests.

## Safety and use

The software is for educational and research use. It does not provide investment advice, recommendations, execution, or assurances about market data or model accuracy. Independently verify all values before making financial decisions.
