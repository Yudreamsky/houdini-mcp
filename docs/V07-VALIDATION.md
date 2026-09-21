# 0.7 validation

2026-09-21, Windows / Houdini 20.5.487. MCP 0.7.0 exposes 22 tools and the same two procedural recipes. This increment implements only the approved parameter preflight, existing-instance recipe inference and reusable acceptance workflow. It does not add components or change geometry sources.

## Behavior

`list_procedural_assets` returns numeric types, bounds and declarative cross-parameter rules. Supported comparisons are lt/le/ge against another field times scale plus offset, and integer multiple_of. Rule IDs and participating fields accompany violations. Geometry's embedded validators still run after the contract; declarations and geometry acceptance are checked against each other.

`preflight_asset_instance` merges overrides with current instance values (or defaults for a new ID), resolves recipe and checks combined values plus ownership, editable-content, channel and recipe-version guards. It returns ready=false for validation failures without modifying the scene. Ready=true describes a plan, not geometry completion, a transaction or a reservation. Upsert re-reads and validates current values.

For an existing instance, omitted recipe reads its stored recipe. For a new ID it preserves the prior straight default. Explicit mismatch is rejected; no automatic conversion or migration. The upsert response now includes resolved recipe.

The reusable GUI script accepts explicit expected clean HIP, new output directory, recipe and matching hython path. It runs real SDK MCP calls and a separate standalone HDA subprocess. Optional --render configures and renders one Mantra frame. It restores the source HIP/frame, verifies clean state/source hash, preserves failed reports and never overwrites an existing output directory. It is scoped to the two known recipes, not arbitrary HDA acceptance. UI pane layout and concurrent manual editing are outside its restoration guarantee.

## Evidence

| Check | Observed result |
|---|---|
| Unit suite | 40 passed. Three new tests cover contract/geometry agreement across 108 parameter combinations, simultaneous actionable violations and invalid types/nonfinite values. |
| Real HOM no-mutation | Preflight for new/default and invalid elbow requests preserved node inventory, dirty state, installed HDA files and compiled-library cache file inventory. Existing-instance guards were exercised without changing parameters during the requests. |
| Guards retained | Animated parameter, locked parameter, unlocked HDA, recipe-version mismatch, foreign ownership and explicit recipe mismatch were refused. Existing-instance omitted recipe resolved to elbow. Subsequent upsert re-read a parameter changed after a previous preflight. |
| Straight GUI SDK run | Same reusable script queried constraints, preflighted without scene change, created, inferred/no-op updated, rejected bad input/recipe, changed dimensions, captured views, reset, saved/reopened, loaded standalone HDA and rendered Mantra. Source scene restored cleanly. |
| Elbow GUI SDK run | Same script and assertions passed with recipe selection changed. Invalid combination returned a field-level wall_ratio violation; valid merged planned values equaled actual written parameters. |
| Failure recovery | --update supplied a deliberately invalid diameter/wall combination. Script exited nonzero and preserved failed report; finally restored original HIP cleanly and source bytes remained unchanged. This report is an expected failure, not a passed asset. |
| Standalone and identity | Both generated HDA files rebuilt without repo src on sys.path. Straight geometry hash remained `003557c7280606753d40662751ce954779cfdddeae724b7e29462a9ef8504e27`; elbow remained `35bac19aa4a8f57b37a1daf5f646362b6493b76b7059bb21629edf3d4c4f7cb6`. |
| Render and review | Two Mantra 960x540 final renders completed, native PNGs returned and no pixel warnings. Both images and the elbow top view were actually viewed; complete assemblies were in frame. Generic presentation lighting is not photographic matching. Other unchanged geometry/view behavior inherits prior asset validation. |

Local evidence (intentionally excluded from Git):

- `evidence/v07-acceptance/straight-01/report.json`, job `2d77b6b06c6f4c10b4eb97350c09a119`.
- `evidence/v07-acceptance/elbow-01/report.json`, job `138375dc168b44c5987a1212e78ce9c1`.
- Both directories include sample.hip, HDA, instance.json, views, standalone.json, render-demo.hip and render-0.png.
- `evidence/v07-acceptance/preflight-hom-01/report.json` from published `tests/preflight_acceptance.py`.
- `evidence/v07-acceptance/failure-recovery.json` and `expected-failure-01/report.json`.
- Unit/Skill logs, visual review and final session/asset fingerprints are retained in the same evidence directory.

## Limits and recovery

Current Codex native Houdini tool discovery remains independently unverified; runs used SDK stdio. Project Skill is discoverable and has been read; its validator checks structure, not decision quality. No global configuration, new plugin installation or global memory update was made.

Technical script success does not automatically approve visual output. The script deliberately leaves visual_review pending; an actual reviewer records their conclusion separately. Render timeout requests cancellation but does not guarantee it has stopped. Timeout/process termination paths were not forced in this increment; check the recorded job before another run. Prior render lifecycle evidence is inherited for unchanged code.

Direct parameter setting outside managed upsert can bypass these recipe-specific checks; generic `set_asset_parameters` has not become a general cross-parameter validator. Preflight evaluates current numeric values and does not actively cook geometry; it does not inspect arbitrary expression side effects or certify engineering compliance.

Rollback baseline: `1b3f3348303ac20085fd8899f82c0b1a3c1fc6ef` (0.6.0), backed up locally in `evidence/pre-v07-backup`. After ensuring no active render, restore source/Skill and reload MCP. Existing assets need no conversion because both geometry algorithms/types are unchanged. In 0.6, elbow updates again require explicit recipe and the new preflight tool/scripts are unavailable.
