# Canonical Flow Hardening Review

## Purpose

This document records the protection work added after the evidence/derive extraction.
The goal is to prevent semantic drift by testing the canonical flow end to end and
locking the public packet contracts used by downstream consumers.

## What Is Now Protected

### End-to-end canonical flow

`tests/test_canonical_flow.py` verifies one coherent chain:

1. canonical run evidence exists
2. canonical compare experiment runs
3. experiment outcome is logged to history
4. history summary reads the logged record
5. action packet reads canonical evidence + derive
6. context pack reads canonical summary
7. run report reads canonical summary
8. next-experiment recommender reads canonical summary + history

The test asserts that all of those surfaces agree on the same primary hotspot target.

### Contract shape tests

`tests/test_contracts.py` locks the top-level shape for:

- action packets
- history summaries
- next-experiment packets

These tests are intentionally simple. They are there to catch accidental field drift.

## What Is Still Not Fully Protected

- UI rendering parity is not covered by full interactive tests.
- Terminology consistency is still convention-driven, not schema-enforced.
- Context-pack field naming still has room for cleanup (`selected_run` vs `display_run` roles).
- Experiment history remains artifact-backed JSONL, not indexed or version-migrated.

## Recommended Next Protection Steps

1. Add one terminology doc for canonical meanings:
   - hotspot
   - bottleneck
   - confidence
   - quality
   - verified
   - comparison

2. Add one focused UI consistency suite for:
   - Stress Engine summary text
   - Inspector provenance warnings
   - active-run badge warnings

3. Add contract-version assertions for:
   - context pack schema version
   - action packet schema version
   - recommendation packet schema version

4. Add repeatability fixtures for:
   - low-confidence history
   - high-variance history
   - degraded schema comparison warnings

## Current Assessment

BlueBench is now in a better state than a typical internal tool at this stage:

- canonical evidence exists
- canonical derivation exists
- multiple consumers read from it
- experiment history exists
- deterministic recommendation exists
- end-to-end coherence is now tested

The main risk has shifted from missing architecture to future convenience drift.
These tests are intended to make that drift visible early.
