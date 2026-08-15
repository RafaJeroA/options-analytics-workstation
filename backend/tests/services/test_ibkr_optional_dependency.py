from __future__ import annotations

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

BACKEND_ROOT = Path(__file__).parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def _run_without_ibapi(code: str, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    guarded_code = f"""
import builtins
real_import = builtins.__import__
def blocked_import(name, *args, **kwargs):
    if name == 'ibapi' or name.startswith('ibapi.'):
        raise ModuleNotFoundError('ibapi intentionally unavailable for deterministic test')
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked_import
{code}
"""
    return subprocess.run(
        [sys.executable, "-c", guarded_code],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def test_base_dependency_metadata_does_not_install_ibapi() -> None:
    pyproject = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert not any(dependency.lower().startswith("ibapi") for dependency in dependencies)
    assert "build==1.5.0" in pyproject["project"]["optional-dependencies"]["dev"]


def test_mock_mode_imports_and_initializes_without_ibapi(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "MODELLATOR_DATA_MODE": "mock",
        "MODELLATOR_DATABASE_PATH": str(tmp_path / "mock-without-ibapi.db"),
    }
    completed = _run_without_ibapi(
        """
from app.main import create_app
from app.services.market_service import get_market_service
service = get_market_service()
assert service.adapter.mode == 'mock'
assert create_app().title == 'Options Analytics Workstation API'
print('mock-without-ibapi-ok')
""",
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "mock-without-ibapi-ok"


def test_explicit_ibkr_mode_fails_early_without_ibapi(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "MODELLATOR_DATA_MODE": "ibkr",
        "MODELLATOR_DATABASE_PATH": str(tmp_path / "ibkr-without-ibapi.db"),
    }
    completed = _run_without_ibapi(
        """
from app.services.adapters.base import AdapterUnavailableError
from app.services.market_service import get_market_service
try:
    get_market_service()
except AdapterUnavailableError as error:
    message = str(error)
    assert 'compatible official TWS API Python client' in message
    assert 'before enabling IBKR mode' in message
    print('ibkr-missing-client-failed-clearly')
else:
    raise AssertionError('IBKR mode unexpectedly initialized without ibapi')
""",
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ibkr-missing-client-failed-clearly"


def test_ibkr_production_and_smoke_code_use_no_account_or_order_api_calls() -> None:
    source_paths = [
        *sorted((BACKEND_ROOT / "app" / "services" / "adapters").glob("ibkr*.py")),
        BACKEND_ROOT / "scripts" / "ibkr_readonly_smoke.py",
    ]
    forbidden_calls = {
        "cancelAccountSummary",
        "cancelOrder",
        "cancelPositions",
        "exerciseOptions",
        "placeOrder",
        "reqAccountSummary",
        "reqAccountUpdates",
        "reqAccountUpdatesMulti",
        "reqAllOpenOrders",
        "reqCompletedOrders",
        "reqExecutions",
        "reqManagedAccts",
        "reqOpenOrders",
        "reqPnL",
        "reqPnLSingle",
        "reqPositions",
        "reqPositionsMulti",
    }

    observed: list[tuple[str, str, int]] = []
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in forbidden_calls:
                    observed.append((str(path.relative_to(REPOSITORY_ROOT)), node.func.attr, node.lineno))

    assert observed == []
