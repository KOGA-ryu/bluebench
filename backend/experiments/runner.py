from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .registry import get_experiment_recipe


def run_experiment(name: str, **kwargs) -> dict[str, Any]:
    recipe = get_experiment_recipe(name)
    if recipe is None:
        raise ValueError(f"Unknown experiment: {name}")

    missing_args = [arg for arg in recipe.required_args if kwargs.get(arg) in (None, "")]
    if missing_args:
        raise ValueError(f"Missing required args for {name}: {', '.join(missing_args)}")

    result = recipe.handler(
        **{key: kwargs[key] for key in recipe.required_args},
        **_extra_kwargs(kwargs, recipe.required_args),
    )
    payload = asdict(result) if is_dataclass(result) else dict(result or {})
    return {
        "experiment": recipe.name,
        "result_type": recipe.result_type,
        "result": payload,
    }


def _extra_kwargs(kwargs: dict[str, Any], required_args: tuple[str, ...]) -> dict[str, Any]:
    return {
        key: value
        for key, value in kwargs.items()
        if key not in required_args and value not in (None, "")
    }
