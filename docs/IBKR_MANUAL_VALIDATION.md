# IBKR manual market-data validation

Status for v0.1: **in progress**. The adapter is experimental and covered by deterministic contract and lifecycle tests. TWS Paper socket connectivity, the API handshake, official `ibapi 10.45.1`, and live EUR/USD market-data callbacks have been validated manually. A SPY request reached TWS and was classified delayed, but delivered no price callbacks. The subscribed US-equity/options matrix is not validated.

This is a read-only validation plan for a period with subscribed market data. It must never request account, portfolio, position, margin, order, or execution data.

## Preconditions

1. Use a current supported TWS or IB Gateway build in paper mode where possible.
2. Install a compatible official TWS API Python client separately. Modellator supports the modern interface from official `ibapi 10.45.1` onward and does not install the obsolete PyPI client.
3. Enable the socket API and restrict it to localhost.
4. Use a dedicated non-conflicting client ID; do not record an account identifier. Keep the application client ID and smoke client ID distinct.
5. Confirm the required market-data packages and delayed-data behavior in the IBKR UI.
6. Start with `MODELLATOR_DATA_MODE=ibkr`; keep the default demo in mock mode.
7. Set `MODELLATOR_IBKR_READONLY_SMOKE=I_UNDERSTAND_READ_ONLY` only for the manual helper run.
8. Create a private evidence directory outside Git or under an ignored `evidence/private/` path.
9. When `MODELLATOR_IBKR_USE_DELAYED=true`, expect the adapter to request type `4`. Treat the latest `marketDataType` callback as authoritative; never infer the state from local market hours or force a second mode because prices did not arrive.

Install the official client from the conventional Windows source location:

```powershell
Set-Location backend
.\scripts\install_official_ibkr_api.ps1 `
  -SourcePath "C:\TWS API\source\pythonclient" `
  -PythonPath ".\.venv\Scripts\python.exe"
.\.venv\Scripts\python.exe -c "import ibapi; print(ibapi.__version__)"
```

`MODELLATOR_IBKR_API_SOURCE` may identify a different official source directory. The helper never downloads `ibapi` from PyPI and does not modify the official source tree.

## Test matrix

| ID | Check | Window | Expected output | Pass criteria | Sanitized evidence |
|---|---|---|---|---|---|
| C01 | Gateway connection and health | Any | Lifecycle reaches connected; health identifies the experimental adapter | Connects within the bounded attempts; shutdown releases the socket/thread | Health JSON and lifecycle log without host username, client ID, or account data |
| C02 | Underlying quote: SPY | Open market | Positive bid/ask/last where entitled, explicit mode, exchange and receipt times | Symbol/contract identity correct; non-crossed usable quote or clearly flagged partial quote | Cropped inspector and sanitized normalized JSON |
| C03 | Underlying quotes: AAPL, QQQ, IWM | Open market | Separate identities and plausible quotes for each symbol | No cache/identity crossover; currency/exchange/conId remain attached to the correct symbol | One compact sanitized table |
| C04 | Option-chain definitions | Any | Available exchanges, trading class, multiplier, expirations, and strikes | At least one unambiguous standard 100-multiplier chain for SPY; ambiguity fails explicitly | Sanitized parameter counts and selected trading class; conId may be hashed |
| C05 | Expiration selection | Any | Requested listed expiration remains selected | Exact requested date returned; unavailable date produces typed not-found/unavailable behavior, never silent substitution except the documented volatility fallback | Request/response pair |
| C06 | Strike selection and contract identity | Any | Ordered strikes around spot; option conId/local symbol/trading class preserved | Calls and puts match requested strike/right/expiration and do not collide | Two sanitized contract records |
| Q01 | Bid, ask, and last | Open market | Each available field remains distinct | A valid pair produces a research midpoint; absent/crossed pairs do not promote last into a mark. Only a live callback is eligible to be described as current, and no quote is guaranteed executable | Screenshot plus normalized quote JSON |
| Q02 | Volume and open interest | Open market, preferably after first hour | Optional statistics appear where subscribed | Call/put tick mapping is correct; missing values remain missing, not zero | Two contracts with side and field names |
| Q03 | Broker implied volatility | Open market | Broker IV retained separately from locally solved IV | Positive finite IV within a plausible range or explicit missing-broker-model flag | Contract inspector with source labels |
| Q04 | Broker Greeks/model price | Open market | Model tick has priority over bid/ask/last computation ticks | No mixed tick-source Greek set; partial Greeks trigger explicit local fallback label | Sanitized broker/local comparison |
| Q05 | Live/delayed/frozen modes | Open market and after market close | Requested type is `4`; displayed mode exactly reflects the callback | Values 1/2/3/4 map to live/frozen/delayed/delayed-frozen; delayed flag only for 3/4; transitions and transition-back remain visible | Mode callback log and UI badge |
| E01 | Missing subscription | Any | Typed partial/unavailable quote with subscription flag | No crash, fabricated mark, or false 404; API response is usable partial data or 503 as appropriate | Sanitized error code/message and UI state |
| E02 | Outside-market-hours behavior | Closed market | Any actual live/frozen/delayed/delayed-frozen callback or no-data result is explicit | The requested type remains `4`; the callback type, if any, is preserved exactly. Type `3` with no prices remains delayed plus `no_price_callbacks`; no mode is forced and no frozen value is called live/current or an executable NBBO | Timestamped screenshot without desktop/account chrome |
| E03 | Disconnect and reconnect | Any | Pending requests cancel; lifecycle retries once and recovers or fails boundedly | No hanging request/thread; recovery refreshes data; failure yields 503 | Sanitized lifecycle timestamps and health snapshots |
| E04 | Partial chain | Open market | Contracts with missing fields remain present and flagged | Complete contracts remain usable; partial contracts do not poison the full chain | Counts by complete/partial reason |
| E05 | Invalid symbol | Any | Genuine unknown symbol | 404 with actionable message; no 500 and no adapter-unavailable misclassification | Request/response pair |
| E06 | Ambiguous contract | Any | Explicit ambiguity response | 409 or typed adapter ambiguity; no arbitrary first-contract selection | Sanitized candidate count and response |
| E07 | Stale/crossed market | Open market if observable; otherwise deterministic replay | Quality flags and unavailable mark | Exchange time drives stale flag; crossed bid/ask never becomes a usable mark | Normalized quote and UI badge |
| S01 | Read-only smoke helper | Any | Sanitized counts plus handshake, request mode, callbacks, errors, price availability, provenance, and timeout stage | Exit 0 after C01–C06/Q checks; output contains no account, portfolio, order, execution, credentials, or absolute private paths | Captured JSON after manual review |

“Any” means the contract-definition/error check can run outside regular hours, subject to TWS availability. Delayed-frozen reference data can support a closed-session smoke pass, but quote freshness, executable bid/ask, volume, open interest, broker IV, and broker Greeks still require an open and reasonably active market for a meaningful pass.

## Execution sequence

1. Run C01 and C04–C06 outside market hours to validate connectivity and definitions.
2. During an open market, run C02–C03 and Q01–Q05 on SPY, AAPL, QQQ, and IWM.
3. Exercise E01 with an intentionally unsubscribed venue/product only if doing so does not alter entitlements.
4. Exercise E03 by manually stopping/restarting the local gateway; do not alter network or account settings beyond this finite test.
5. Run closed-market E02 after the same contracts have been observed during open hours.
6. Run the opt-in helper once, inspect its JSON, then unset `MODELLATOR_IBKR_READONLY_SMOKE`.
7. Mark each matrix row pass/fail with date, TWS/Gateway version, API version, market window, and a short deviation note.

## Immediate modern-client retest

After all automated gates pass, first reproduce the known-good EUR/USD path while TWS Paper is available. The smoke client ID `9002` remains distinct from the application default `9001`:

```powershell
Set-Location backend

$env:MODELLATOR_DATA_MODE="ibkr"
$env:MODELLATOR_IBKR_HOST="127.0.0.1"
$env:MODELLATOR_IBKR_PORT="7497"
$env:MODELLATOR_IBKR_CLIENT_ID="9002"
$env:MODELLATOR_IBKR_USE_DELAYED="true"
$env:MODELLATOR_IBKR_CHAIN_QUOTE_WAIT_SECONDS="8"

$env:MODELLATOR_IBKR_READONLY_SMOKE="I_UNDERSTAND_READ_ONLY"
$env:MODELLATOR_IBKR_SMOKE_INSTRUMENT="EURUSD"

.\.venv\Scripts\python.exe scripts\ibkr_readonly_smoke.py
```

Then run the SPY diagnostic without changing provenance or inventing an entitlement error:

```powershell
$env:MODELLATOR_IBKR_SMOKE_INSTRUMENT="SPY"
$env:MODELLATOR_IBKR_SMOKE_SYMBOL="SPY"

.\.venv\Scripts\python.exe scripts\ibkr_readonly_smoke.py
```

The helper records handshake success, client package version, TWS server version when available, requested type, actual callback sequence, request errors, informational farm-status messages, bid/ask/last callback and unavailable status, elapsed duration, usability, reason code, and provenance. A `live`, `delayed`, `frozen`, `delayed_frozen`, or `unconfirmed` result must be retained exactly as returned. If TWS selects delayed and emits no prices, the expected classification is `no_price_callbacks` with delayed provenance unless an actual IBKR error supports a stronger classification.

The already observed evidence is:

- EUR/USD CASH IDEALPRO: handshake succeeded; `marketDataType=1`; live bid, ask, last, high, low, close, price, and size ticks arrived repeatedly.
- SPY STK SMART after requesting type `4`: handshake succeeded; TWS selected `marketDataType=3`; no price callbacks arrived during the observation interval; no fatal TWS connection error was received.

The SPY observation does not establish universal delayed-data availability, a subscription failure, or US-options readiness. Subscribed US-equity/options validation remains pending.

## Evidence sanitization

- Capture only the application pane or normalized JSON fields needed for the row.
- Remove account numbers, usernames, machine names, client IDs, login dialogs, portfolio values, notification banners, and filesystem paths.
- Hash contract conIds consistently if cross-image correlation is needed; do not alter symbol/right/strike/expiration evidence.
- Search evidence for account-like identifiers and private paths before moving any file into public documentation.
- Never publish raw TWS logs. Extract the minimum callback/error lines and replace unrelated identifiers with `[redacted]`.
- Store originals privately; publish only reviewed derivatives.

## Exit decision

The adapter may be described as “manually validated with subscribed market data” only when every blocker row (C01–C06, Q01, Q03–Q05, E01–E06, S01) passes on the recorded versions. A failure keeps the adapter experimental and does not block mock-mode v0.1.
