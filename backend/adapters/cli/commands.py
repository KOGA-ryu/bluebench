from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import TextIO

from backend.adapters.codex.action_packet import generate_action_packet
from backend.adapters.codex.cold_start_packet import build_cold_start_packet
from backend.context import build_context_pack
from backend.experiments.runner import run_experiment
from backend.history import load_experiment_records, log_experiment_result, summarize_experiment_history
from backend.instrumentation.storage import InstrumentationStorage
from backend.recommend import recommend_next_experiment
from backend.derive.hotspot_ranker import rank_file_hotspots
from backend.derive.run_comparator import compare_runs
from backend.evidence.loaders.evidence_loader import load_run_evidence


def hotspot_summary_command(project_root: Path, run_id: str, *, storage=None) -> dict[str, object]:
    evidence = load_run_evidence(run_id, project_root=project_root, storage=storage)
    return {"run_id": run_id, "hotspots": rank_file_hotspots(evidence)}


def compare_run_command(project_root: Path, baseline_run_id: str, current_run_id: str, *, storage=None) -> dict[str, object]:
    baseline = load_run_evidence(baseline_run_id, project_root=project_root, storage=storage)
    current = load_run_evidence(current_run_id, project_root=project_root, storage=storage)
    return {
        "baseline_run_id": baseline_run_id,
        "current_run_id": current_run_id,
        "comparison": compare_runs(baseline, current),
    }


def action_packet_command(project_root: Path, run_id: str, *, storage=None) -> dict[str, object]:
    return generate_action_packet(run_id, project_root=project_root, storage=storage)


def cold_start_command(repo_root: Path) -> dict[str, object]:
    packet = build_cold_start_packet(repo_root)
    lines = [
        "BlueBench Cold Start",
        "Project Type: " + str(packet["project_type"]),
        "Likely Entry Points:",
    ]
    lines.extend(f"- {path}" for path in packet["entry_points"])
    lines.append("Primary Subsystems:")
    lines.extend(f"- {name}" for name in packet["primary_subsystems"])
    lines.append("First Review Targets:")
    for target in packet["first_review_targets"]:
        lines.append(f"- {target['path']}")
        for reason in target["reason"]:
            lines.append(f"  reason: {reason}")
        lines.append(f"  confidence: {target['confidence']}")
    lines.append("Suggested Next Actions:")
    lines.extend(f"- {action}" for action in packet["recommended_next_actions"])
    return {"cold_start_packet": packet, "formatted_summary": "\n".join(lines)}


def stress_canonical_command(
    project_root: Path,
    iterations: int,
    *,
    stdout: TextIO,
    storage=None,
    summary_every: int = 10,
    jitter_ms: float = 0.0,
    inject_history_failure_every: int = 0,
    seed: int = 7,
) -> int:
    storage = storage or InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
    current_run_id, baseline_run_id = _resolve_stress_run_pair(project_root, storage)
    stable_target: str | None = None
    iteration_durations: list[float] = []
    initial_fd_count = _open_fd_count()
    rng = random.Random(seed)
    recovery_required = False

    for index in range(1, iterations + 1):
        started = time.perf_counter()
        inject_failure = inject_history_failure_every > 0 and index % inject_history_failure_every == 0
        try:
            flow = _run_canonical_flow_iteration(
                project_root,
                current_run_id,
                baseline_run_id,
                storage=storage,
                jitter_seconds=max(0.0, jitter_ms) / 1000.0,
                rng=rng,
                fail_history_log=inject_failure,
            )
        except RuntimeError as exc:
            if inject_failure and str(exc) == "injected history log failure":
                recovery_required = True
                payload = {
                    "iteration": index,
                    "status": "expected_injected_failure",
                    "avg_iteration_runtime_ms": round((sum(iteration_durations) / len(iteration_durations)) * 1000.0, 3)
                    if iteration_durations
                    else 0.0,
                    "fd_count": _open_fd_count(),
                }
                stdout.write(json.dumps(payload, sort_keys=True) + "\n")
                continue
            stdout.write(
                json.dumps({"error": str(exc), "iteration": index, "status": "unexpected_failure"}, sort_keys=True) + "\n"
            )
            return 1

        elapsed = time.perf_counter() - started
        iteration_durations.append(elapsed)

        target = str(flow["action_packet"]["primary_target"]["path"])
        if stable_target is None:
            stable_target = target
        elif target != stable_target:
            stdout.write(json.dumps({"error": f"canonical hotspot drifted to {target}", "iteration": index}) + "\n")
            return 1
        if recovery_required:
            recovery_required = False

        if summary_every > 0 and (index % summary_every == 0 or index == iterations):
            payload = {
                "iteration": index,
                "avg_iteration_runtime_ms": round((sum(iteration_durations) / len(iteration_durations)) * 1000.0, 3),
                "fd_count": _open_fd_count(),
            }
            stdout.write(json.dumps(payload, sort_keys=True) + "\n")

    if recovery_required:
        stdout.write(json.dumps({"error": "final iteration ended on injected failure without recovery"}, sort_keys=True) + "\n")
        return 1

    if len(iteration_durations) >= 20:
        first_window = sum(iteration_durations[:10]) / 10.0
        last_window = sum(iteration_durations[-10:]) / 10.0
        if last_window > max(first_window * 4.0, first_window + 0.05):
            stdout.write(
                json.dumps(
                    {
                        "error": "iteration latency grew unbounded",
                        "first_window_ms": round(first_window * 1000.0, 3),
                        "last_window_ms": round(last_window * 1000.0, 3),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            return 1

    final_fd_count = _open_fd_count()
    if initial_fd_count is not None and final_fd_count is not None and final_fd_count > initial_fd_count + 8:
        stdout.write(
            json.dumps(
                {
                    "error": "open file descriptor count increased unexpectedly",
                    "initial_fd_count": initial_fd_count,
                    "final_fd_count": final_fd_count,
                },
                sort_keys=True,
            )
            + "\n"
        )
        return 1

    stdout.write(
        json.dumps(
            {
                "status": "ok",
                "iterations": iterations,
                "run_id": current_run_id,
                "baseline_run_id": baseline_run_id,
                "target": stable_target,
                "initial_fd_count": initial_fd_count,
                "final_fd_count": final_fd_count,
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BlueBench adapter commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    action_packet_parser = subparsers.add_parser("action-packet", help="Generate a canonical Codex action packet.")
    action_packet_parser.add_argument("--run", dest="run_id", required=True, help="Completed run id.")
    action_packet_parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root containing .bluebench/instrumentation.sqlite3",
    )

    experiment_parser = subparsers.add_parser("experiment", help="Run canonical BlueBench experiments.")
    experiment_subparsers = experiment_parser.add_subparsers(dest="experiment_command", required=True)
    experiment_run_parser = experiment_subparsers.add_parser("run", help="Run a registered experiment.")
    experiment_run_parser.add_argument("experiment_name", help="Registered experiment name.")
    experiment_run_parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root containing .bluebench/instrumentation.sqlite3",
    )
    experiment_run_parser.add_argument("--run-id", dest="run_id")
    experiment_run_parser.add_argument("--baseline-run-id", dest="baseline_run_id")
    experiment_run_parser.add_argument("--current-run-id", dest="current_run_id")

    history_parser = subparsers.add_parser("history", help="Show experiment history.")
    history_subparsers = history_parser.add_subparsers(dest="history_command", required=True)
    history_show_parser = history_subparsers.add_parser("show", help="Show recorded experiment records for a target.")
    history_show_parser.add_argument("--target", required=True)
    history_show_parser.add_argument("--experiment")
    history_show_parser.add_argument("--project-root", default=str(Path.cwd()))
    history_summary_parser = history_subparsers.add_parser("summary", help="Show confidence summary for a target.")
    history_summary_parser.add_argument("--target", required=True)
    history_summary_parser.add_argument("--experiment")
    history_summary_parser.add_argument("--project-root", default=str(Path.cwd()))

    recommend_parser = subparsers.add_parser("recommend-next", help="Recommend the next deterministic investigation step.")
    recommend_parser.add_argument("--target", required=True)
    recommend_parser.add_argument("--run", dest="run_id")
    recommend_parser.add_argument("--baseline", dest="baseline_run_id")
    recommend_parser.add_argument("--project-root", default=str(Path.cwd()))

    cold_start_parser = subparsers.add_parser("cold-start", help="Build a compact first-contact repo investigation packet.")
    cold_start_parser.add_argument("--repo", dest="repo_root", required=True)

    stress_parser = subparsers.add_parser("stress-canonical", help="Repeat the canonical flow to validate endurance stability.")
    stress_parser.add_argument("--iterations", type=int, default=100)
    stress_parser.add_argument("--project-root", default=str(Path.cwd()))
    stress_parser.add_argument("--jitter-ms", type=float, default=0.0)
    stress_parser.add_argument("--inject-history-failure-every", type=int, default=0)
    stress_parser.add_argument("--seed", type=int, default=7)

    return parser


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stdout or sys.stdout

    if args.command == "action-packet":
        payload = action_packet_command(Path(args.project_root), args.run_id)
        output.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    if args.command == "cold-start":
        payload = cold_start_command(Path(args.repo_root))
        output.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    if args.command == "experiment" and args.experiment_command == "run":
        payload = run_experiment(
            args.experiment_name,
            project_root=Path(args.project_root),
            run_id=getattr(args, "run_id", None),
            baseline_run_id=getattr(args, "baseline_run_id", None),
            current_run_id=getattr(args, "current_run_id", None),
        )
        log_experiment_result(
            Path(args.project_root),
            payload,
            baseline_run_id=getattr(args, "baseline_run_id", None),
            current_run_id=getattr(args, "current_run_id", None) or getattr(args, "run_id", None),
        )
        output.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    if args.command == "history" and args.history_command == "show":
        payload = {
            "target": args.target,
            "records": load_experiment_records(
                Path(args.project_root),
                target=args.target,
                experiment=getattr(args, "experiment", None),
            ),
        }
        output.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    if args.command == "history" and args.history_command == "summary":
        payload = summarize_experiment_history(
            Path(args.project_root),
            target=args.target,
            experiment=getattr(args, "experiment", None),
        )
        output.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    if args.command == "recommend-next":
        payload = recommend_next_experiment(
            args.target,
            run_id=getattr(args, "run_id", None),
            baseline_run_id=getattr(args, "baseline_run_id", None),
            project_root=Path(args.project_root),
        )
        output.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    if args.command == "stress-canonical":
        return stress_canonical_command(
            Path(args.project_root),
            args.iterations,
            stdout=output,
            jitter_ms=getattr(args, "jitter_ms", 0.0),
            inject_history_failure_every=getattr(args, "inject_history_failure_every", 0),
            seed=getattr(args, "seed", 7),
        )

    parser.error(f"Unknown command: {args.command}")
    return 2


def _resolve_stress_run_pair(project_root: Path, storage: InstrumentationStorage) -> tuple[str, str]:
    runs = storage.list_completed_runs(limit=2, project_root=project_root)
    if not runs:
        raise ValueError("No completed runs available for stress-canonical")
    current_run = runs[0]
    baseline_run_id = storage.fetch_previous_comparable_run_id(
        str(current_run["run_id"]),
        str(current_run["scenario_kind"]),
        str(current_run["hardware_profile"]),
        project_root=project_root,
    )
    if not baseline_run_id:
        if len(runs) < 2:
            raise ValueError("A previous comparable run is required for stress-canonical")
        baseline_run_id = str(runs[1]["run_id"])
    return str(current_run["run_id"]), baseline_run_id


def _run_canonical_flow_iteration(
    project_root: Path,
    current_run_id: str,
    baseline_run_id: str,
    *,
    storage: InstrumentationStorage,
    jitter_seconds: float = 0.0,
    rng: random.Random | None = None,
    fail_history_log: bool = False,
) -> dict[str, object]:
    _sleep_with_jitter(jitter_seconds, rng)
    compare_payload = run_experiment(
        "compare_runs",
        project_root=project_root,
        baseline_run_id=baseline_run_id,
        current_run_id=current_run_id,
        storage=storage,
    )
    _sleep_with_jitter(jitter_seconds, rng)
    if fail_history_log:
        raise RuntimeError("injected history log failure")
    log_experiment_result(project_root, compare_payload, baseline_run_id=baseline_run_id, current_run_id=current_run_id)
    target = str(compare_payload["result"]["derived"]["file_deltas"][0]["file_path"])
    _sleep_with_jitter(jitter_seconds, rng)
    action_packet = generate_action_packet(current_run_id, project_root=project_root, storage=storage)
    _sleep_with_jitter(jitter_seconds, rng)
    recommendation = recommend_next_experiment(
        target,
        run_id=current_run_id,
        baseline_run_id=baseline_run_id,
        project_root=project_root,
        storage=storage,
    )
    _sleep_with_jitter(jitter_seconds, rng)
    context_pack = build_context_pack(project_root, current_run_id, "current", mode="short", storage=storage)
    return {
        "target": target,
        "action_packet": action_packet,
        "recommendation": recommendation,
        "context_pack": context_pack,
    }


def _open_fd_count() -> int | None:
    for path in ("/proc/self/fd", "/dev/fd"):
        try:
            return len(os.listdir(path))
        except OSError:
            continue
    return None


def _sleep_with_jitter(jitter_seconds: float, rng: random.Random | None) -> None:
    if jitter_seconds <= 0.0:
        return
    jitter_rng = rng or random.Random(7)
    time.sleep(jitter_rng.uniform(0.0, jitter_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
