from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REQUIRED_MODULES = {
    "app/api/router.py",
    "app/models/market.py",
    "app/quant/strategy.py",
    "app/services/market_service.py",
    "app/services/adapters/ibkr.py",
    "app/services/adapters/ibkr_compat.py",
    "app/services/adapters/ibkr_contracts.py",
    "app/services/adapters/ibkr_runtime.py",
    "app/services/normalization/market.py",
}


def verify_wheel(path: Path) -> int:
    if not path.is_file() or path.suffix != ".whl":
        raise ValueError(f"Expected one wheel file, received: {path}")

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

    missing = sorted(REQUIRED_MODULES - names)
    leaked_tests = sorted(name for name in names if name.startswith("tests/") or "/tests/" in name)
    if missing:
        raise RuntimeError(f"Wheel is missing required application modules: {', '.join(missing)}")
    if leaked_tests:
        raise RuntimeError(f"Wheel unexpectedly contains test files: {', '.join(leaked_tests[:5])}")

    app_modules = sorted(name for name in names if name.startswith("app/") and name.endswith(".py"))
    print(f"Verified {path.name}: {len(app_modules)} application modules; all required packages present.")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/verify_wheel.py <wheel-path>", file=sys.stderr)
        return 2
    try:
        return verify_wheel(Path(sys.argv[1]))
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        print(f"Wheel verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
