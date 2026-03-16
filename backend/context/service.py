from __future__ import annotations

from pathlib import Path

from backend.adapters.codex.context_pack import build_codex_context_pack
from backend.instrumentation.storage import InstrumentationStorage
from backend.triage.service import generate_triage

from .session_state import load_session_state


CONTEXT_LIMITS = {
    "tiny": {
        "entry_points": 1,
        "hot_files": 5,
        "hot_functions": 3,
        "risks": 3,
        "actions": 3,
        "hypotheses": 3,
    },
    "short": {
        "entry_points": 3,
        "hot_files": 10,
        "hot_functions": 10,
        "risks": 5,
        "actions": 5,
        "hypotheses": 5,
    },
    "full": {
        "entry_points": 10,
        "hot_files": 25,
        "hot_functions": 25,
        "risks": 10,
        "actions": 10,
        "hypotheses": 10,
    },
}


def build_context_pack(
    project_root: Path,
    active_run_id: str | None,
    run_view_mode: str,
    mode: str = "short",
    storage: InstrumentationStorage | None = None,
    *,
    session_state: dict[str, object] | None = None,
    focus_targets: list[dict[str, object]] | None = None,
    open_files: list[str] | None = None,
    include_prefixes: list[str] | None = None,
) -> dict[str, object]:
    if mode not in CONTEXT_LIMITS:
        raise ValueError("mode must be 'tiny', 'short', or 'full'")
    if run_view_mode not in {"current", "previous"}:
        raise ValueError("run_view_mode must be 'current' or 'previous'")

    resolved_project_root = Path(project_root).expanduser().resolve()
    runtime_storage = storage or InstrumentationStorage(
        resolved_project_root / ".bluebench" / "instrumentation.sqlite3"
    )
    runtime_storage.initialize_schema()
    resolved_session = session_state if isinstance(session_state, dict) else load_session_state(resolved_project_root)
    effective_run_id = active_run_id or _session_string(resolved_session, "selected_run_id")
    effective_run_view_mode = run_view_mode or _session_string(resolved_session, "run_view_mode") or "current"
    effective_open_files = list(open_files or _session_string_list(resolved_session, "open_files"))
    effective_focus_targets = list(focus_targets or _session_targets(resolved_session))
    limits = CONTEXT_LIMITS[mode]

    codex_context = build_codex_context_pack(
        resolved_project_root,
        effective_run_id,
        effective_run_view_mode,
        storage=runtime_storage,
        limit_hot_files=limits["hot_files"],
    )
    selected_run = codex_context.get("selected_run")
    display_run = codex_context.get("display_run")
    display_run_id = str((display_run or {}).get("run_id") or "") if isinstance(display_run, dict) else None

    triage_mode = "full" if mode == "full" else "quick"
    triage = generate_triage(
        resolved_project_root,
        run_id=display_run_id,
        mode=triage_mode,
        storage=runtime_storage,
        include_prefixes=include_prefixes,
    )
    project = dict(triage.get("project") or {})
    runtime_context = dict(triage.get("runtime_context") or {})
    compute = dict(triage.get("compute") or {})
    architecture = dict(triage.get("architecture") or {})
    operational_risks = dict(triage.get("operational_risks") or {})
    recommendations = list(triage.get("recommended_actions") or [])
    hypotheses = list(triage.get("hypotheses") or [])

    compact_risks = _compact_risks(operational_risks, limits["risks"])
    compact_actions = recommendations[: limits["actions"]]
    compact_hypotheses = hypotheses[: limits["hypotheses"]]
    codex_summary = dict(codex_context.get("summary") or {})
    compact_project = {
        "name": project.get("name"),
        "root": project.get("root"),
        "app_type_guess": project.get("app_type_guess"),
        "entry_points": list(project.get("entry_points") or [])[: limits["entry_points"]],
    }

    context = {
        "mode": mode,
        "project": compact_project,
        "session": {
            "selected_run_id": effective_run_id,
            "display_run_id": display_run_id,
            "run_view_mode": effective_run_view_mode,
            "open_files": effective_open_files,
            "focus_targets": effective_focus_targets,
            "last_triage_mode": _session_string(resolved_session, "last_triage_mode"),
        },
        "runtime": {
            "selected_run": selected_run,
            "display_run": display_run,
            "quality_warnings": list(runtime_context.get("quality_warnings") or []),
        },
        "compute": {
            "hot_files": [
                {
                    "file_path": item.get("file_path"),
                    "normalized_compute_score": item.get("normalized_compute_score"),
                    "rolling_score": item.get("rolling_score"),
                    "total_time_ms": item.get("raw_ms"),
                    "call_count": item.get("call_count"),
                }
                for item in list(codex_summary.get("hotspots") or [])[: limits["hot_files"]]
            ]
            or list(compute.get("hot_files") or [])[: limits["hot_files"]],
            "hot_functions": list(compute.get("hot_functions") or [])[: limits["hot_functions"]],
            "regressions": list(compute.get("regressions") or [])[: limits["hot_files"]],
        },
        "architecture": {
            "subsystems": list(architecture.get("suspected_subsystems") or [])[: limits["risks"]],
            "coupling_hotspots": list(architecture.get("relationship_hotspots") or [])[: limits["risks"]],
            "mixed_concern_files": list(architecture.get("mixed_concern_files") or [])[: limits["risks"]],
        },
        "risks": compact_risks,
        "actions": compact_actions,
        "hypotheses": compact_hypotheses,
        "canonical_summary": codex_summary,
        "evidence_types": dict(codex_summary.get("evidence_types") or _build_evidence_types(
            context_mode=mode,
            selected_run=selected_run,
            display_run=display_run,
            compact_risks=compact_risks,
            compact_actions=compact_actions,
        )),
    }

    if mode == "full":
        context["triage"] = triage
    return context


def build_context_pack_from_session(
    project_root: Path,
    mode: str = "short",
    storage: InstrumentationStorage | None = None,
    include_prefixes: list[str] | None = None,
) -> dict[str, object]:
    session_state = load_session_state(project_root)
    return build_context_pack(
        project_root,
        _session_string(session_state, "selected_run_id"),
        _session_string(session_state, "run_view_mode") or "current",
        mode=mode,
        storage=storage,
        session_state=session_state,
        include_prefixes=include_prefixes,
    )


def _compact_risks(operational_risks: dict[str, object], limit: int) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for name in list(operational_risks.get("native_dependencies") or []):
        items.append({"label": str(name), "evidence_type": "heuristic", "source": "native_dependencies"})
    for name in list(operational_risks.get("optional_dependencies") or []):
        items.append({"label": str(name), "evidence_type": "heuristic", "source": "optional_dependencies"})
    for text in list(operational_risks.get("launch_assumptions") or []):
        items.append({"label": str(text), "evidence_type": "inferred", "source": "launch_assumptions"})
    return items[:limit]


def _build_evidence_types(
    *,
    context_mode: str,
    selected_run: dict[str, object] | None,
    display_run: dict[str, object] | None,
    compact_risks: list[dict[str, object]],
    compact_actions: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    measured: list[dict[str, object]] = []
    heuristic: list[dict[str, object]] = []
    inferred: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []

    if selected_run is not None:
        measured.append({"label": str(selected_run.get("run_name") or ""), "source": "selected_run"})
    else:
        missing.append({"label": "No selected run", "source": "selected_run"})
    if display_run is not None:
        measured.append({"label": str(display_run.get("run_name") or ""), "source": "display_run"})
    else:
        missing.append({"label": "No display run", "source": "display_run"})

    for item in compact_risks:
        evidence_type = str(item.get("evidence_type") or "")
        if evidence_type == "heuristic":
            heuristic.append({"label": str(item.get("label") or ""), "source": str(item.get("source") or "")})
        elif evidence_type == "inferred":
            inferred.append({"label": str(item.get("label") or ""), "source": str(item.get("source") or "")})

    for action in compact_actions:
        inferred.append(
            {
                "label": str(action.get("title") or ""),
                "source": "recommended_actions",
                "confidence": str(action.get("confidence") or ""),
            }
        )

    return {
        "measured": measured,
        "heuristic": heuristic,
        "inferred": inferred,
        "missing": missing,
        "context_mode": [{"label": context_mode, "source": "build_context_pack"}],
    }


def _session_string(session_state: dict[str, object], key: str) -> str | None:
    value = session_state.get(key)
    return value if isinstance(value, str) and value else None


def _session_string_list(session_state: dict[str, object], key: str) -> list[str]:
    value = session_state.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _session_targets(session_state: dict[str, object]) -> list[dict[str, object]]:
    value = session_state.get("focus_targets")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
