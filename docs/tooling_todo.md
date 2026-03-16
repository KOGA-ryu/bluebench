# Tooling TODO

This is the current sibling-tooling backlog around BlueBench and DeltaBench.

The rule for all of them:

- one engineering question per tool
- evidence first
- derive once
- compact packets
- no giant umbrella platform

## Priority Candidates

### TestBench

Purpose:
- identify what tests matter
- record what actually ran
- show where validation is weak
- compress test relevance and test-result continuity

Why it matters:
- the current Test Chain is useful, but still narrow
- validation quality is one of the biggest sources of wasted engineering time

Likely scope:
- recommended tests
- executed tests
- compact result summaries
- coverage gap hints
- weak-validation warnings

### FailureBench

Purpose:
- preserve compact local memory of failures
- answer what broke, where, under what command/profile, and whether it is recurring

Why it matters:
- agents and humans both rediscover the same failures too often
- failure memory is usually fragmented across terminal history, test logs, and chat

Likely scope:
- recent failures
- recurring failure targets
- command/profile linkage
- compact failure packets
- rerun suggestions

### ConfigBench

Purpose:
- map runtime/config/profile knobs
- identify which settings materially change behavior
- highlight risky or confusing config surfaces

Why it matters:
- many repos are behavior-driven by flags, profiles, env vars, and config files
- this is often tribal knowledge instead of structured evidence

Likely scope:
- config surface map
- risky flag/profile combinations
- default vs override summaries
- config relevance packets

### CacheBench

Purpose:
- distinguish cold vs warm behavior
- show cache effectiveness and distortion
- catch stale-cache or cache-sensitive performance conclusions

Why it matters:
- cache state quietly invalidates a lot of engineering conclusions
- scanner-like systems especially benefit from explicit cold/warm analysis

Likely scope:
- cold/warm comparison packets
- cache-sensitivity experiments
- stale-cache warnings
- repeatability with cache-state labels

### DependencyBench

Purpose:
- identify structural choke points and boundary crossings
- show what modules are central or risky to touch

Why it matters:
- many review and refactor risks come from dependency shape, not file size

Likely scope:
- subsystem boundary crossings
- central module ranking
- structural choke-point packets
- import risk summaries

## Value Ranking

Likely highest practical value:
1. TestBench
2. FailureBench
3. ConfigBench
4. CacheBench
5. DependencyBench

Most low-key useful:
1. FailureBench
2. ConfigBench
3. CacheBench

## Direction

BlueBench:
- runtime truth

DeltaBench:
- change-risk truth

These siblings should extend the same model:
- reduce reorientation cost
- reduce guesswork
- preserve engineering memory
- compress context for humans and agents

The main risk to avoid:
- turning this into one giant workflow god-object
- or a vague orchestration platform

The right direction is still:
- narrow tools
- explicit contracts
- compact artifacts
- cumulative memory
