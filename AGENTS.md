# AGENTS.md

## Purpose

This repository uses BlueBench to compress repo context, measure performance, and support AI-assisted engineering.

The goal of the system is to:

- reduce developer orientation time
- reduce token usage for AI agents
- provide reliable evidence for code investigation and optimization

## Core Principles

- Evidence before interpretation
- Prefer measurement over speculation
- Use BlueBench for performance investigations
- Do not duplicate logic across multiple UI or reporting surfaces
- Keep summaries compressed and factual

## BlueBench Workflow

Typical workflow:

1. Run BlueBench scan
2. Inspect hotspots
3. Investigate subsystem behavior
4. Apply targeted code changes
5. Verify improvement using BlueBench comparison

Agents should avoid guessing about performance without evidence.

## Investigation Commands

BlueBench experiments should be used for:

- hotspot investigation
- run comparison
- regression verification
- subsystem isolation

If performance issues are suspected, agents should gather evidence before modifying code.

## Repository Navigation

- Explorer view is for navigation and signals
- Inspector view is the authoritative diagnostic surface
- Stress Engine is used for experiment execution

Agents should treat Inspector data as the most trustworthy diagnostic evidence.
For performance truth, agents should prefer run telemetry, Stress Engine summaries, and BlueBench reports tied to a selected run.

## Run Scope

All compute and performance interpretation must be tied to an explicit selected run.

Agents should not assume that the latest run is the correct source of truth.

## Performance Truth Model

Always distinguish between:

- measured data
- derived metrics
- inferred conclusions
- missing evidence

Agents must clearly label which category information belongs to.

## Optimization Guidelines

When optimizing code:

- focus on measured hotspots
- avoid speculative refactors
- prefer minimal targeted changes
- always verify improvements using BlueBench runs

## AI Context Packs

BlueBench context packs exist to reduce token usage.

Agents should prefer context packs over loading large sections of source code.
Context packs are preferred for orientation and compression, but source code remains the implementation source of truth.

## Final Rule

BlueBench reports and measurements are considered the primary evidence for performance and system behavior in this repository.
