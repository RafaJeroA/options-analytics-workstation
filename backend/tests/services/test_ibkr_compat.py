from __future__ import annotations

from inspect import signature
from types import SimpleNamespace

import pytest

import app.services.adapters.ibkr_compat as compat_module
from app.services.adapters.ibkr_compat import (
    MODERN_ERROR_PARAMETERS,
    IBAPICompatibilityError,
    probe_ibapi_compatibility,
    require_compatible_ibapi,
)
from app.services.adapters.ibkr_runtime import _RuntimeCallbacks


class _ModernWrapper:
    def error(
        self,
        reqId: int,
        errorTime: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        return None


class _LegacyWrapper:
    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        return None


class _ModernTickTypes:
    @staticmethod
    def toStr(value: int) -> str:  # noqa: N802 - official API naming
        return str(value)


def _module_loader(*, version: str, wrapper: type[object] = _ModernWrapper):
    modules = {
        "ibapi": SimpleNamespace(__version__=version),
        "ibapi.client": SimpleNamespace(EClient=object),
        "ibapi.contract": SimpleNamespace(Contract=object),
        "ibapi.ticktype": SimpleNamespace(TickTypeEnum=_ModernTickTypes),
        "ibapi.wrapper": SimpleNamespace(EWrapper=wrapper),
    }
    return modules.__getitem__


def test_missing_ibapi_reports_actionable_external_installation() -> None:
    def missing_loader(name: str) -> object:
        raise ModuleNotFoundError(name)

    result = probe_ibapi_compatibility(module_loader=missing_loader)

    assert result.available is False
    assert result.compatible is False
    assert result.reason_code == "ibapi_missing"
    assert "official TWS API distribution" in result.detail
    assert "before enabling IBKR mode" in result.detail


def test_obsolete_ibapi_is_rejected_before_callback_initialization() -> None:
    result = probe_ibapi_compatibility(module_loader=_module_loader(version="9.81.1.post1"))

    assert result.available is True
    assert result.compatible is False
    assert result.package_version == "9.81.1.post1"
    assert result.reason_code == "ibapi_version_obsolete"
    assert "minimum supported" in result.detail


def test_compatible_modern_ibapi_is_accepted() -> None:
    result = probe_ibapi_compatibility(module_loader=_module_loader(version="10.45.1"))

    assert result.available is True
    assert result.compatible is True
    assert result.package_version == "10.45.1"
    assert result.reason_code == "compatible"


def test_newer_version_with_legacy_error_signature_is_rejected() -> None:
    result = probe_ibapi_compatibility(
        module_loader=_module_loader(version="10.46.0", wrapper=_LegacyWrapper)
    )

    assert result.compatible is False
    assert result.reason_code == "ibapi_interface_incompatible"


def test_runtime_callback_bridge_exposes_explicit_modern_error_signature() -> None:
    assert tuple(signature(_RuntimeCallbacks.error).parameters) == MODERN_ERROR_PARAMETERS


def test_require_compatible_ibapi_raises_typed_actionable_error(monkeypatch) -> None:
    incompatible = probe_ibapi_compatibility(module_loader=_module_loader(version="9.81.1.post1"))
    monkeypatch.setattr(compat_module, "probe_ibapi_compatibility", lambda: incompatible)

    with pytest.raises(IBAPICompatibilityError, match="official TWS API Python client") as failure:
        require_compatible_ibapi()

    assert failure.value.reason_code == "api_version_incompatible"
    assert failure.value.compatibility.reason_code == "ibapi_version_obsolete"
