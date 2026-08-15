from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import import_module, metadata
from inspect import signature
from typing import Any, Callable

from app.services.adapters.base import AdapterUnavailableError

MINIMUM_IBAPI_VERSION = (10, 45, 1)
MINIMUM_IBAPI_VERSION_TEXT = ".".join(str(part) for part in MINIMUM_IBAPI_VERSION)
MODERN_ERROR_PARAMETERS = (
    "self",
    "reqId",
    "errorTime",
    "errorCode",
    "errorString",
    "advancedOrderRejectJson",
)
INSTALLATION_GUIDANCE = (
    "IBKR mode requires a compatible official TWS API Python client. "
    "Install it from the official TWS API distribution before enabling IBKR mode. "
    "From the backend directory, run scripts\\install_official_ibkr_api.ps1."
)


@dataclass(frozen=True, slots=True)
class IBAPICompatibility:
    available: bool
    compatible: bool
    package_version: str | None
    reason_code: str
    detail: str

    def diagnostics(self) -> dict[str, str | bool | None]:
        return {
            "client_api_available": self.available,
            "client_api_compatible": self.compatible,
            "client_api_package_version": self.package_version,
            "minimum_client_api_version": MINIMUM_IBAPI_VERSION_TEXT,
            "client_api_compatibility_reason": self.reason_code,
        }


class IBAPICompatibilityError(AdapterUnavailableError):
    reason_code = "api_version_incompatible"

    def __init__(self, compatibility: IBAPICompatibility) -> None:
        self.compatibility = compatibility
        super().__init__(compatibility.detail)


def _numeric_version(version: str) -> tuple[int, int, int] | None:
    match = re.match(r"^\s*(\d+)\.(\d+)(?:\.(\d+))?", version)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def probe_ibapi_compatibility(
    *,
    module_loader: Callable[[str], Any] = import_module,
    distribution_version: Callable[[str], str] = metadata.version,
) -> IBAPICompatibility:
    try:
        package = module_loader("ibapi")
    except (ImportError, ModuleNotFoundError):
        return IBAPICompatibility(
            available=False,
            compatible=False,
            package_version=None,
            reason_code="ibapi_missing",
            detail=INSTALLATION_GUIDANCE,
        )
    except Exception as error:  # pragma: no cover - defensive import boundary
        return IBAPICompatibility(
            available=False,
            compatible=False,
            package_version=None,
            reason_code="ibapi_import_failed",
            detail=f"{INSTALLATION_GUIDANCE} The current client import failed ({type(error).__name__}).",
        )

    package_version = getattr(package, "__version__", None)
    if not isinstance(package_version, str) or not package_version.strip():
        try:
            package_version = distribution_version("ibapi")
        except Exception:
            package_version = None

    parsed_version = _numeric_version(package_version) if package_version else None
    if parsed_version is None:
        return IBAPICompatibility(
            available=True,
            compatible=False,
            package_version=package_version,
            reason_code="ibapi_version_unknown",
            detail=(
                "The installed ibapi package does not expose a usable version. "
                f"Modellator requires the official TWS API Python client {MINIMUM_IBAPI_VERSION_TEXT} or newer. "
                f"{INSTALLATION_GUIDANCE}"
            ),
        )
    if parsed_version < MINIMUM_IBAPI_VERSION:
        return IBAPICompatibility(
            available=True,
            compatible=False,
            package_version=package_version,
            reason_code="ibapi_version_obsolete",
            detail=(
                f"Installed ibapi {package_version} is incompatible with Modellator; "
                f"the minimum supported official TWS API Python client is {MINIMUM_IBAPI_VERSION_TEXT}. "
                "The obsolete PyPI 9.81.1.post1 client must not be used. "
                f"{INSTALLATION_GUIDANCE}"
            ),
        )

    try:
        client_module = module_loader("ibapi.client")
        contract_module = module_loader("ibapi.contract")
        ticktype_module = module_loader("ibapi.ticktype")
        wrapper_module = module_loader("ibapi.wrapper")
        error_parameters = tuple(signature(wrapper_module.EWrapper.error).parameters)
        has_modern_tick_converter = callable(getattr(ticktype_module.TickTypeEnum, "toStr", None))
        required_types_present = all(
            (
                getattr(client_module, "EClient", None),
                getattr(contract_module, "Contract", None),
                getattr(wrapper_module, "EWrapper", None),
            )
        )
    except Exception as error:
        return IBAPICompatibility(
            available=True,
            compatible=False,
            package_version=package_version,
            reason_code="ibapi_interface_import_failed",
            detail=(
                f"Installed ibapi {package_version} could not load the required modern interface "
                f"({type(error).__name__}). {INSTALLATION_GUIDANCE}"
            ),
        )

    if (
        error_parameters != MODERN_ERROR_PARAMETERS
        or not has_modern_tick_converter
        or not required_types_present
    ):
        return IBAPICompatibility(
            available=True,
            compatible=False,
            package_version=package_version,
            reason_code="ibapi_interface_incompatible",
            detail=(
                f"Installed ibapi {package_version} does not provide the required modern TWS API callback "
                f"interface. Modellator requires official client {MINIMUM_IBAPI_VERSION_TEXT} or newer. "
                f"{INSTALLATION_GUIDANCE}"
            ),
        )

    return IBAPICompatibility(
        available=True,
        compatible=True,
        package_version=package_version,
        reason_code="compatible",
        detail=(
            f"Compatible official TWS API Python client detected: ibapi {package_version} "
            f"(minimum {MINIMUM_IBAPI_VERSION_TEXT})."
        ),
    )


def require_compatible_ibapi() -> IBAPICompatibility:
    compatibility = probe_ibapi_compatibility()
    if not compatibility.compatible:
        raise IBAPICompatibilityError(compatibility)
    return compatibility
