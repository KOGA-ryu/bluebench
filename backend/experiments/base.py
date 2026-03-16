from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ExperimentResult:
    name: str
    evidence: dict[str, Any]
    derived: dict[str, Any]
