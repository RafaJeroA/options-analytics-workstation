from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SEGMENTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    "local_backups",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".tsbuildinfo"}
SECRET_PATTERNS = {
    "private key": re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "assigned credential": re.compile(
        r"(?im)^\s*(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*[\"']?[^\s\"']{8,}"
    ),
    "private Windows user path": re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s]+\\"),
}


def _git_bytes(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
    return completed.stdout


def _paths(mode: str) -> list[str]:
    if mode == "tracked":
        output = _git_bytes("ls-files", "-z")
    else:
        output = _git_bytes("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return sorted(item.decode("utf-8") for item in output.split(b"\0") if item)


def _content(path: str, mode: str) -> bytes:
    if mode == "staged":
        return _git_bytes("show", f":{path}")
    return (REPOSITORY_ROOT / PurePosixPath(path)).read_bytes()


def _forbidden_path_reason(path: str) -> str | None:
    normalized = PurePosixPath(path)
    lowered_parts = {part.lower() for part in normalized.parts}
    name = normalized.name.lower()
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment file"
    if lowered_parts & FORBIDDEN_SEGMENTS:
        return f"generated/private directory: {sorted(lowered_parts & FORBIDDEN_SEGMENTS)[0]}"
    if normalized.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"forbidden artifact suffix: {normalized.suffix.lower()}"
    if any(part.lower().endswith(".egg-info") for part in normalized.parts):
        return "generated package metadata"
    if tuple(part.lower() for part in normalized.parts[:2]) in {
        ("screenshots", "private"),
        ("evidence", "private"),
    }:
        return "private evidence directory"
    return None


def check(mode: str) -> list[str]:
    findings: list[str] = []
    for path in _paths(mode):
        reason = _forbidden_path_reason(path)
        if reason:
            findings.append(f"{path}: {reason}")
            continue

        data = _content(path, mode)
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path}: possible {label}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject secrets and generated/private repository artifacts.")
    parser.add_argument(
        "--tracked",
        action="store_true",
        help="Scan every tracked file (CI/release mode); default scans the staged snapshot.",
    )
    args = parser.parse_args()
    mode = "tracked" if args.tracked else "staged"
    try:
        findings = check(mode)
    except (OSError, RuntimeError) as error:
        print(f"Repository hygiene check could not run: {error}", file=sys.stderr)
        return 2

    if findings:
        print(f"Repository hygiene check failed ({mode} files):", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print(f"Repository hygiene check passed ({mode} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
