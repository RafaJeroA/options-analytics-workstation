from __future__ import annotations

import pytest

pytest.importorskip("ibapi")

from ibapi.decoder import Decoder
from ibapi.protobuf.ErrorMessage_pb2 import ErrorMessage

from app.services.adapters.ibkr_compat import probe_ibapi_compatibility
from app.services.adapters.ibkr_runtime import _RuntimeCallbacks


def test_installed_official_client_matches_modern_compatibility_contract() -> None:
    compatibility = probe_ibapi_compatibility()

    assert compatibility.compatible is True
    assert compatibility.package_version is not None


def test_protobuf_error_message_decodes_through_modern_runtime_callback() -> None:
    calls: list[tuple[object, ...]] = []

    class Recorder:
        def _handle_error(
            self,
            req_id: int,
            code: int,
            message: str,
            *,
            error_time: int | None = None,
            advanced_order_reject_present: bool = False,
        ) -> None:
            calls.append(
                (
                    req_id,
                    error_time,
                    code,
                    message,
                    advanced_order_reject_present,
                )
            )

    class Wrapper(_RuntimeCallbacks):
        def __init__(self) -> None:
            self.runtime = Recorder()
            self.protobuf_seen = False

        def errorProtoBuf(self, message: ErrorMessage) -> None:  # noqa: N802
            self.protobuf_seen = True

    message = ErrorMessage(
        id=91,
        errorTime=1_786_725_602,
        errorCode=354,
        errorMsg="Requested market data is not subscribed.",
        advancedOrderRejectJson="{}",
    )
    wrapper = Wrapper()

    Decoder(wrapper, serverVersion=999).processErrorMsgProtoBuf(message.SerializeToString())

    assert wrapper.protobuf_seen is True
    assert calls == [
        (
            91,
            1_786_725_602,
            354,
            "Requested market data is not subscribed.",
            True,
        )
    ]
