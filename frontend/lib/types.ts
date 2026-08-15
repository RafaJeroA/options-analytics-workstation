export type MarketDataMode =
  | "mock"
  | "unconfirmed"
  | "live"
  | "frozen"
  | "delayed"
  | "delayed_frozen";
export type QuoteSource = "broker" | "broker_model" | "local_model" | "mock";
export type PricingState = "complete" | "partial" | "unavailable";
export type PayoffMetricState = "finite" | "unlimited" | "unavailable";
export type DataQualityFlag =
  | "crossed_market"
  | "wide_spread"
  | "market_data_unavailable"
  | "subscription_missing"
  | "missing_bid"
  | "missing_ask"
  | "low_volume"
  | "low_open_interest"
  | "stale"
  | "unusable_mark"
  | "suspicious_mid"
  | "invalid_for_iv"
  | "delayed"
  | "frozen"
  | "reference_only"
  | "local_greeks"
  | "missing_broker_model";
export type OptionRight = "call" | "put";
export type InstrumentType = "option" | "stock";

export interface UnderlyingQuote {
  symbol: string;
  description: string;
  exchange: string;
  currency: string;
  con_id?: number | null;
  spot: number;
  previous_close: number;
  change: number;
  change_percent: number;
  timestamp: string;
  exchange_timestamp?: string | null;
  received_at?: string | null;
  market_data_mode: MarketDataMode;
  is_delayed: boolean;
  market_data_unavailable?: boolean;
  subscription_missing?: boolean;
}

export interface OptionContract {
  contract_id: string;
  con_id?: number | null;
  symbol: string;
  exchange: string;
  currency: string;
  expiration: string;
  strike: number;
  right: OptionRight;
  multiplier: number;
  local_symbol?: string | null;
  trading_class?: string | null;
}

export interface OptionGreeks {
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  rho: number | null;
  theoretical_price: number | null;
  source: QuoteSource;
}

export interface OptionQuote {
  contract: OptionContract;
  bid: number | null;
  ask: number | null;
  last: number | null;
  mark: number | null;
  model_price: number | null;
  volume: number | null;
  openInterest?: number | null;
  open_interest?: number | null;
  market_data_unavailable?: boolean;
  subscription_missing?: boolean;
  implied_vol: number | null;
  broker_implied_vol: number | null;
  greeks: OptionGreeks | null;
  intrinsic_value: number | null;
  extrinsic_value: number | null;
  data_flags: DataQualityFlag[];
  quote_source: QuoteSource;
  model_source: QuoteSource;
  market_data_mode: MarketDataMode;
  updated_at: string;
  exchange_timestamp?: string | null;
  received_at?: string | null;
  is_delayed: boolean;
}

export interface ChainSnapshot {
  symbol: string;
  underlying: UnderlyingQuote;
  expirations: string[];
  selected_expiration: string;
  calls: OptionQuote[];
  puts: OptionQuote[];
  updated_at: string;
  market_data_mode: MarketDataMode;
}

export interface VolSurfacePoint {
  symbol: string;
  expiration: string;
  strike: number;
  moneyness: number;
  implied_vol: number;
  option_right: OptionRight;
  updated_at: string;
}

export interface TermStructurePoint {
  symbol: string;
  expiration: string;
  days_to_expiry: number;
  atm_iv: number | null;
  atm_strike: number | null;
  method: string | null;
  sample_size: number;
  status: "available" | "unavailable";
  updated_at: string;
}

export interface UnderlyingSearchResult {
  symbol: string;
  description: string;
  exchange: string;
  currency: string;
  market_data_mode: MarketDataMode;
}

export interface WatchlistItem {
  symbol: string;
  note?: string | null;
  created_at: string;
}

export interface RecentChainView {
  symbol: string;
  viewed_at: string;
}

export interface PricingAssumptions {
  valuation_date?: string;
  underlying_price: number;
  risk_free_rate: number;
  dividend_yield: number;
  volatility_shift: number;
  days_forward: number;
}

export interface StrategyLegDraft {
  leg_id: string;
  instrument_type: InstrumentType;
  side: "long" | "short";
  quantity: number;
  contract?: OptionContract | null;
  quote?: OptionQuote | null;
  entry_price?: number | null;
  stock_price?: number | null;
  underlying_symbol?: string | null;
}

export interface StrategyDefinition {
  name: string;
  template?: string | null;
  underlying_symbol: string;
  underlying_price: number;
  legs: StrategyLegDraft[];
}

export interface PayoffPoint {
  spot: number;
  value: number;
}

export interface StrategyLegValuation {
  leg_id: string;
  market_value: number | null;
  theoretical_value: number | null;
  entry_value: number | null;
  pnl_open: number | null;
  warnings: string[];
}

export interface StrategyValuation {
  strategy_name: string;
  underlying_symbol: string;
  assumptions: PricingAssumptions;
  net_debit_credit: number | null;
  entry_cost: number | null;
  current_value: number | null;
  theoretical_value: number | null;
  pnl_open: number | null;
  max_profit: number | null;
  max_loss: number | null;
  max_profit_state: PayoffMetricState;
  max_loss_state: PayoffMetricState;
  breakevens: number[];
  breakeven_intervals: Array<{ start: number; end: number | null }>;
  payoff: PayoffPoint[];
  legs: StrategyLegValuation[];
  pricing_state: PricingState;
  status_message: string | null;
  warnings: string[];
}

export interface SavedStrategyRecord {
  strategy_id: string;
  name: string;
  strategy: StrategyDefinition;
  updated_at: string;
}

export interface UserSettings {
  theme: string;
  default_rate: number;
  default_dividend_yield: number;
  watchlist_symbols: string[];
  recent_symbols: string[];
  selected_symbol?: string | null;
  left_panel_size: number;
  right_panel_size: number;
}

export interface ScenarioInput {
  underlying_moves_pct: number[];
  implied_vol_shifts: number[];
  days_forward: number[];
  valuation_date?: string;
  risk_free_rate: number;
  dividend_yield: number;
}

export interface ScenarioDayState {
  days_forward: number;
  expiration_state: "pre_expiry" | "at_or_after_expiry" | "mixed" | "no_option_legs";
  volatility_shift_effective: boolean | null;
  message: string | null;
}

export interface ScenarioPoint {
  underlying_price: number;
  move_pct: number;
  vol_shift: number;
  days_forward: number;
  current_value: number | null;
  theoretical_value: number | null;
  pnl_open: number | null;
}

export interface ScenarioGridResult {
  strategy_name: string;
  underlying_symbol: string;
  base_underlying_price: number;
  points: ScenarioPoint[];
  pricing_state: PricingState;
  status_message: string | null;
  warnings: string[];
  volatility_shift_effective: boolean | null;
  day_states: ScenarioDayState[];
}
