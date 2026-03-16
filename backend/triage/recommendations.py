from __future__ import annotations


def build_recommendations(
    static_summary: dict[str, object],
    runtime_summary: dict[str, object],
    architecture_snapshot: dict[str, object],
) -> list[dict[str, object]]:
    recommendations: list[dict[str, object]] = []
    hot_files = list(runtime_summary.get("hot_files") or [])
    quality_warnings = list(runtime_summary.get("quality_warnings") or [])
    regressions = list(runtime_summary.get("regressions") or [])
    entry_points = list(static_summary.get("project", {}).get("entry_points", []))
    mixed_concern_files = list(architecture_snapshot.get("mixed_concern_files") or [])
    operational_risks = dict(static_summary.get("dependencies") or {})
    external_pressure = list(runtime_summary.get("external_pressure") or [])

    if hot_files:
        hottest = hot_files[0]
        recommendations.append(
            {
                "priority": 1,
                "title": f"Inspect {hottest['file_path']} before broad optimization",
                "reason": f"It leads the selected run with score {float(hottest['normalized_compute_score']):.1f} and {float(hottest['total_time_ms']):.1f} ms total time.",
                "expected_impact": "Highest chance of finding a real hotspot quickly.",
                "confidence": "high",
            }
        )
        if int(hottest.get("exception_count", 0)) > 0:
            recommendations.append(
                {
                    "priority": len(recommendations) + 1,
                    "title": f"Stabilize failures in {hottest['file_path']}",
                    "reason": f"The hottest file also recorded {int(hottest['exception_count'])} exceptions.",
                    "expected_impact": "Improves trust in compute signals and reduces runtime instability.",
                    "confidence": "high",
                }
            )
    if quality_warnings:
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "title": "Tighten the verification run before drawing strong conclusions",
                "reason": quality_warnings[0],
                "expected_impact": "Improves trust in all hotspot and regression conclusions.",
                "confidence": "medium",
            }
        )
    if regressions:
        regression = regressions[0]
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "title": f"Review regression in {regression['file_path']}",
                "reason": f"Score changed by {float(regression['score_delta']):+.1f} vs the previous comparable run.",
                "expected_impact": "Fastest route to understanding recent performance drift.",
                "confidence": "high",
            }
        )
    if external_pressure:
        dominant_bucket = external_pressure[0]
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "title": f"Inspect external pressure from {dominant_bucket['bucket_name']}",
                "reason": f"{dominant_bucket['bucket_name']} contributes {float(dominant_bucket['total_time_ms']):.1f} ms in {dominant_bucket['file_path']}.",
                "expected_impact": "Clarifies whether time is dominated by project code or dependency behavior.",
                "confidence": "medium",
            }
        )
    if mixed_concern_files:
        candidate = mixed_concern_files[0]
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "title": f"Separate concerns in {candidate['file_path']}",
                "reason": candidate["reason"],
                "expected_impact": "Reduces future debugging and refactor risk.",
                "confidence": "medium",
            }
        )
    native_modules = list(operational_risks.get("native_modules") or [])
    native_risk_files = list(operational_risks.get("native_risk_files") or [])
    if native_modules and native_risk_files:
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "title": f"Isolate native startup dependencies from {native_risk_files[0]['path']}",
                "reason": f"Native/platform imports ({', '.join(native_risk_files[0]['native_imports'])}) are present near startup paths.",
                "expected_impact": "Makes instrumentation and headless verification easier and reduces environment fragility.",
                "confidence": "medium",
            }
        )
    if entry_points:
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "title": "Verify a non-interactive entry path for instrumentation",
                "reason": f"Top entry candidate is {entry_points[0]['path']}. A headless verification path makes repeated triage more reliable.",
                "expected_impact": "Improves repeatability of runtime evidence.",
                "confidence": "medium",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": 1,
                "title": "Generate a representative completed run",
                "reason": "Static structure alone is not enough for strong optimization guidance.",
                "expected_impact": "Unlocks measured hotspot and regression analysis.",
                "confidence": "high",
            }
        )
    for index, item in enumerate(recommendations, start=1):
        item["priority"] = index
    return recommendations[:5]
