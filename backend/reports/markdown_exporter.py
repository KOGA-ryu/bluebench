from __future__ import annotations

from pathlib import Path


def export_report_markdown(report: dict[str, object], target_path: Path) -> Path:
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    run = dict(report.get("run") or {})
    measured = dict(report.get("measured") or {})
    hotspots = list(report.get("hotspots") or [])
    comparison = dict(report.get("comparison") or {})
    evidence_types = dict(report.get("evidence_types") or {})
    lines = [
        f"# {report.get('title', 'Run Report')}",
        "",
        "## Run",
        f"- Run: {run.get('run_name') or '-'}",
        f"- Status: {run.get('status') or '-'}",
        f"- Quality: {run.get('quality') or '-'}",
        "",
        "## Measured",
        f"- Runtime: {float(measured.get('runtime_ms') or 0.0):.1f} ms",
        f"- Trace Overhead: {float(measured.get('trace_overhead_ms') or 0.0):.1f} ms",
        "",
        "## Hotspots",
    ]
    lines.extend(
        [
            f"- {item.get('file_path', '-')} · {float(item.get('raw_ms') or 0.0):.1f} ms"
            for item in hotspots
        ]
        or ["- none"]
    )
    lines.extend(
        [
            "",
            "## Comparison",
            f"- Runtime Delta: {float(comparison.get('runtime_delta_ms') or 0.0):+.1f} ms",
            f"- Trace Overhead Delta: {float(comparison.get('trace_overhead_delta_ms') or 0.0):+.1f} ms",
            "",
            "## Summary",
        ]
    )
    lines.extend([f"- {line}" for line in report.get("summary_lines", []) or []] or ["- none"])
    lines.extend(["", "## Evidence Types"])
    for bucket_name in ("measured", "derived", "inferred", "missing"):
        bucket = list(evidence_types.get(bucket_name) or [])
        lines.append(f"- {bucket_name}: {len(bucket)}")
    target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target_path
