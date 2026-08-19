# Options Analytics Workstation

I built this project as a local application for researching option chains and multi-leg strategies. It combines a FastAPI backend with a Next.js interface, European Black-Scholes analytics, implied-volatility solving, exact expiry-payoff calculations, scenario analysis and local SQLite storage.

The main supported mode uses deterministic synthetic market data, so the full application can be run without an IBKR account, credentials or paid data. The application does not place orders.

![Volatility analytics](docs/images/analytics-overview.png)

![Multi-leg strategy payoff](docs/images/strategy-payoff.png)

## What it does

- Displays synthetic option chains for SPY, AAPL, NVDA, TSLA and QQQ.
- Prices European calls and puts and calculates Delta, Gamma, Theta, Vega and Rho.
- Solves implied volatility subject to theoretical option-price bounds.
- Builds single-leg and multi-leg strategies.
- Calculates exact expiry payoffs, breakevens, maximum profit and maximum loss.
- Runs spot, volatility and time-to-expiry scenarios.
- Saves and reloads strategies locally.
- Keeps broker quotes, broker model values and local calculations separate.
- Identifies delayed, stale, incomplete, crossed or unavailable market data.

## Quantitative scope

The local model is European Black-Scholes with continuous dividend yield and continuously compounded interest rates. The implementation covers expiry, zero-volatility limits, negative interest rates, option-price bounds and implied-volatility convergence checks.

Many listed US equity and ETF options are American-style. Early exercise and discrete dividends are not fully represented, so local values can differ from broker values and market prices.

Expiry-payoff calculations are exact for the represented option cash flows, but they exclude commissions, taxes, margin, borrow costs, assignment and exercise mechanics.

The full modelling and market-data limits are documented in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Run locally

Requirements:

- Python 3.12 or later
- Node.js 20.9 or later; Node 22 is recommended

Use two terminals from the repository root.

### Backend

~~~powershell
Set-Location backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:MODELLATOR_DATA_MODE="mock"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
~~~

### Frontend

~~~powershell
Set-Location frontend
npm ci
npm run dev
~~~

Open `http://localhost:3000`.

The main workflow is:

~~~text
symbol search → option chain → contract inspection → strategy construction
→ payoff analysis → scenario analysis → save and reload
~~~

The synthetic data uses a fixed valuation clock and seeded inputs, so repeated runs produce the same demo values.

## Project structure

- `backend/app/quant`: pricing, Greeks, implied volatility and payoff calculations.
- `backend/app/services`: market-data adapters, normalization, caching and persistence.
- `backend/app/models`: typed financial and API models.
- `frontend/`: interface, strategy construction and charts.
- `docs/`: architecture and IBKR validation notes.

More detail is available in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## IBKR status

The IBKR adapter is experimental, disabled by default and limited to read-only contract and market-data research. It does not submit orders or access accounts, portfolios, positions, margin or executions.

TWS Paper connectivity and live EUR/USD callbacks have been tested with the official IBKR Python client. Validation with subscribed US equity and options data remains incomplete.

The current validation boundary is documented in [docs/IBKR_MANUAL_VALIDATION.md](docs/IBKR_MANUAL_VALIDATION.md).

## Testing

The automated tests cover:

- Black-Scholes boundary cases, parity, Greeks and implied volatility;
- exact single-leg and multi-leg payoff calculations;
- API validation and local persistence;
- deterministic synthetic market data;
- adapter errors and connection lifecycle;
- the main frontend workflow.

GitHub Actions run separate backend and frontend checks.

## License

Released under the MIT License.

This project is for research and educational use. It is not investment advice, production trading software or a guarantee of market-data accuracy.
