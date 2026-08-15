# Options Analytics Workstation backend

Typed FastAPI service for deterministic mock market data, normalized experimental IBKR market data, European option analytics, exact expiry payoff analysis, scenarios, and local SQLite persistence.

## Run in supported mock mode

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:MODELLATOR_DATA_MODE="mock"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the generated API schema. The default database is local user data at `data/modellator.db` and is excluded from Git.

Mock mode and the normal deterministic test suite do not require TWS or `ibapi`. The base project intentionally has no `ibapi` dependency.

## Install the official IBKR client for experimental mode

IBKR mode requires a separately installed official TWS API Python client with a compatible modern callback interface. The minimum supported version is `10.45.1`; the obsolete PyPI client `9.81.1.post1` must not be installed for Modellator.

From this directory on Windows:

```powershell
.\scripts\install_official_ibkr_api.ps1 `
  -SourcePath "C:\TWS API\source\pythonclient" `
  -PythonPath ".\.venv\Scripts\python.exe"

.\.venv\Scripts\python.exe -c "import ibapi; print(ibapi.__version__)"
```

If the official source is elsewhere, pass `-SourcePath` or set `MODELLATOR_IBKR_API_SOURCE`. The helper verifies the local source, installs from a disposable copy with the selected interpreter, checks the installed version and callback interface, never downloads `ibapi` from PyPI, and does not modify the official TWS API source directory.

Selecting `MODELLATOR_DATA_MODE=ibkr` without a compatible client fails immediately with actionable guidance. It never silently switches to mock data.

## Validation

```powershell
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m ruff format --check --no-cache .
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe scripts\verify_wheel.py <wheel-path>
```

The real-IBKR test is opt-in and skipped by default. The adapter is market-data-only and experimental. TWS Paper, official `ibapi 10.45.1`, and live EUR/USD callbacks have been verified manually; a SPY request was classified delayed but delivered no price callbacks. Subscribed US-equity/options validation is still pending. See [`../docs/IBKR_MANUAL_VALIDATION.md`](../docs/IBKR_MANUAL_VALIDATION.md).

## Model boundary

Local prices and Greeks use European Black–Scholes with continuous dividend yield. Exact expiry payoff summaries are piecewise-linear over non-negative spot. American exercise, discrete dividends, fees, margin, and execution are not modeled. See [`../KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md).
