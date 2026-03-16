from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .compare_runs import compare_runs_experiment
from .isolate_hotspot import isolate_hotspot_experiment


@dataclass(frozen=True, slots=True)
class ExperimentRecipe:
    name: str
    handler: Callable[..., Any]
    required_args: tuple[str, ...]
    result_type: str


EXPERIMENT_REGISTRY: dict[str, ExperimentRecipe] = {
    "compare_runs": ExperimentRecipe(
        name="compare_runs",
        handler=compare_runs_experiment,
        required_args=("project_root", "baseline_run_id", "current_run_id"),
        result_type="comparison",
    ),
    "isolate_hotspot": ExperimentRecipe(
        name="isolate_hotspot",
        handler=isolate_hotspot_experiment,
        required_args=("project_root", "run_id"),
        result_type="hotspot_isolation",
    ),
}


def get_experiment_recipe(name: str) -> ExperimentRecipe | None:
    return EXPERIMENT_REGISTRY.get(name)
