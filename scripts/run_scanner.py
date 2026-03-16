from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER_ROOT = Path(os.environ.get("SCANNER_ROOT", REPO_ROOT.parent / "scanner")).expanduser().resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.version import load_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scanner product entrypoint.")
    parser.add_argument("--version", action="store_true", help="Print scanner wrapper version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the scanner once.")
    run_parser.add_argument("--instrument", action="store_true", help="Run under BlueBench instrumentation.")
    run_parser.add_argument("--mode", choices=("smoke", "realistic"), default="smoke")

    benchmark_parser = subparsers.add_parser("benchmark", help="Run the scanner live probe benchmark.")
    benchmark_parser.add_argument("--profile", default="top_gainers_mvp")
    benchmark_parser.add_argument("--symbols", default="NVDA,AAPL")
    benchmark_parser.add_argument("--repeats", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(_scanner_version())
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "run":
        if args.instrument:
            return _run_instrumented_scanner(args.mode)
        return _run_scanner_verify(args.mode)
    if args.command == "benchmark":
        return _run_subprocess(
            [
                _scanner_python().as_posix(),
                "core/live_probe.py",
                "--profile",
                str(args.profile),
                "--symbols",
                str(args.symbols),
                "--repeats",
                str(args.repeats),
            ]
        )
    parser.error(f"Unknown command: {args.command}")
    return 2


def _scanner_python() -> Path:
    candidate = SCANNER_ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def _scanner_version() -> str:
    version_path = SCANNER_ROOT / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip() or load_version()
    return load_version()


def _run_scanner_verify(mode: str) -> int:
    return _run_subprocess([_scanner_python().as_posix(), "main.py", "verify", "--mode", mode])


def _run_instrumented_scanner(mode: str) -> int:
    command = [
        sys.executable,
        "-m",
        "backend.instrumentation.script_runner",
        "--database",
        str(SCANNER_ROOT / ".bluebench" / "instrumentation.sqlite3"),
        "--project-root",
        str(SCANNER_ROOT),
        "--script-path",
        str(SCANNER_ROOT / "main.py"),
        "--run-name",
        f"scanner_{mode}_instrumented",
        "--scenario-kind",
        "custom_script",
        "--hardware-profile",
        "local_machine",
        "--",
        "verify",
        "--mode",
        mode,
    ]
    return _run_subprocess(command)


def _run_subprocess(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=str(SCANNER_ROOT))
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
