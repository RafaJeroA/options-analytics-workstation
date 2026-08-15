from __future__ import annotations

from typing import Any, Protocol


class AdapterUnavailableError(RuntimeError):
    """Raised when a broker adapter is not available."""


class MarketDataNotFoundError(LookupError):
    """Base class for market-data identifiers known not to exist."""


class UnknownSymbolError(MarketDataNotFoundError):
    """Raised when the adapter has positively determined that a symbol is unknown."""


class UnknownContractError(MarketDataNotFoundError):
    """Raised when the adapter has positively determined that a contract is unknown."""


class AmbiguousContractError(RuntimeError):
    """Raised when a broker returns multiple equally plausible contract identities."""


class BrokerAdapter(Protocol):
    mode: str

    def status(self) -> str: ...

    def search_underlyings(self, query: str) -> list[dict[str, Any]]: ...

    def get_underlying_summary(self, symbol: str) -> dict[str, Any]: ...

    def get_option_chain(self, symbol: str, expiration: str | None = None) -> dict[str, Any]: ...

    def get_option_quote(self, contract_id: str) -> dict[str, Any]: ...

    def close(self) -> None: ...
