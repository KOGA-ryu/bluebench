# Terminology

## hotspot

Definition:
File with the highest measured compute cost in a run.

Canonical producer:
`backend/derive/hotspot_ranker.py`

Consumers:
- Inspector
- context packs
- reports
- action packets
- recommender

Rules:
Must never be recomputed outside the derive layer.

## bottleneck

Definition:
The dominant measured source of runtime cost for a run or comparison context.

Canonical producer:
`backend/derive/summary_builder.py`

Consumers:
- Stress Engine summary
- reports
- context packs
- recommender

Rules:
Must be derived from canonical hotspot ranking and canonical comparisons, not ad hoc UI logic.

## run_quality

Definition:
Coverage and trace-overhead quality label for a single run.

Canonical producer:
`backend/instrumentation/collector.py`

Consumers:
- Stress Engine
- evidence store
- reports
- context packs

Rules:
Must not be re-scored in downstream consumers.

## confidence

Definition:
Rule-based confidence level derived from experiment history sample count, improvement rate, and variance.

Canonical producer:
`backend/history/confidence.py`

Consumers:
- history summaries
- context packs
- recommender

Rules:
Must never be inferred in UI or adapters without going through history summaries.

## verified

Definition:
State where a result has been checked against canonical evidence and downstream consumers agree on the same canonical target or output.

Canonical producer:
`tests/test_canonical_flow.py`

Consumers:
- developer workflow
- review docs
- future release checks

Rules:
Must refer to canonical-flow verification, not informal visual inspection alone.

## comparison

Definition:
Canonical before/after delta object between a baseline run and a current run.

Canonical producer:
`backend/derive/run_comparator.py`

Consumers:
- Stress Engine
- reports
- action packets
- recommender

Rules:
Must never be recomputed outside the derive layer.
