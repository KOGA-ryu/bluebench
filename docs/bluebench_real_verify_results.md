# BlueBench Real Verify

## Saved Artifact

- Reusable `.bbtest`: [bluebench_real_verify.bbtest](/Users/kogaryu/dev/bluebench/bluebench_real_verify.bbtest)
- Verification script: [bluebench_real_verify.py](/Users/kogaryu/dev/bluebench/tools/verification/bluebench_real_verify.py)

## What Was Tested

- A real BlueBench verification workload using the instrumentation runner.
- First attempt:
  - `backend/triage/cli.py`
  - failed because the runner executes script paths with `runpy.run_path(...)`, and `triage/cli.py` depends on relative package imports.
- Second attempt:
  - `tools/verification/bluebench_real_verify.py`
  - valid entry script, real BlueBench code path, long-running workload.

## Confirmed Results

### 1. Direct CLI script path is not a valid Stress Engine target

Observed:

- `backend/triage/cli.py` failed under the runner with:
  - `ImportError: attempted relative import with no known parent package`

Implication:

- package-style CLI modules are not safe Stress Engine targets when launched as raw script paths.

Action:

- use a wrapper entry script such as [bluebench_real_verify.py](/Users/kogaryu/dev/bluebench/tools/verification/bluebench_real_verify.py)
- or extend the runner later to support module execution (`python -m ...`) explicitly

### 2. The reusable verification entry script runs, but exposes a scaling issue

Observed live state from the `bluebench_real_verify.py` run:

- elapsed time exceeded `58s`
- `raw_function_row_count`: `26`
- `sampler_sample_count`: `229`
- external bucket time heavily dominated by `external:stdlib`
- measured file/function coverage was not increasing in proportion to elapsed time

Implication:

- the run is progressing, but too much time is being spent in broad stdlib-heavy work for this verification path
- this is not a good steady-state verification profile yet

Likely cause:

- BlueBench still does too much broad repo scanning/loading work before the filtered triage/context layers get to narrow the result set
- `.venv` contamination was fixed in triage output, but the upstream project-loading path is still too expensive for self-verification

## Practical Judgment

### What passed

- instrumentation backend is functional
- report writing is functional
- Stress Engine can target a real in-repo verification script
- the saved `.bbtest` format is reusable

### What failed or remains weak

- direct package CLI script targets are not safe as raw script paths
- self-verification workload is too scan-heavy to be considered a clean baseline
- current real verify profile is trustworthy as a bottleneck finder, not yet as a compact regression benchmark

## Actionable Improvements

### High priority

1. Add module-mode execution support to the runner
- allow Stress Engine scenarios to choose:
  - script path
  - module path
- this removes the `runpy.run_path(...)` relative-import limitation

2. Reduce self-verification scan scope
- exclude `.venv`, `site-packages`, caches, and generated paths earlier in the project-loading pipeline, not just in triage summarization

3. Add verification quality rules
- mark a verification run as weak if:
  - runtime grows large
  - file coverage remains low
  - stdlib/external pressure dominates

### Medium priority

4. Add a dedicated BlueBench self-check workload
- one purpose-built internal script that:
  - loads a bounded project slice
  - generates triage
  - generates context pack
  - exits predictably

5. Add a verification checklist doc
- launch
- completion
- aggregation
- explorer
- inspector
- report path
- trust judgment

## Recommended Reuse

For future manual reruns:

1. Open Stress Engine
2. Open [bluebench_real_verify.bbtest](/Users/kogaryu/dev/bluebench/bluebench_real_verify.bbtest)
3. Choose `Editable run spec`
4. Start the run

If the goal is a reliable benchmark rather than bottleneck discovery, prefer a tighter internal verification script after the project-loading scope is reduced.
