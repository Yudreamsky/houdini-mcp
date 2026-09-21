# Changelog

## 0.3.0

- Added live session/renderer/GPU inventory and mandatory render preflight for newly submitted jobs. GPU inventory does not claim Karma XPU support or measured speed.
- Added frame-boundary cancellation and hash-verified continuation into new child jobs, preserving prior records. Corrupt or missing PNG/EXR pairs are rerendered.
- Added request deduplication, conflicting-ID rejection, a two-job concurrency bound, interprocess locks and Windows process creation-time checks.
- Frozen HIP/HDA and discovered external dependency hashes are checked before execution and continuation. External textures/caches are not packaged.
- Added numeric asset schemas and named presets, integer/toggle/strict-range validation and prior-value reporting. Animated channels remain protected.
- `set_asset_parameters` now returns its result directly, including `before`; callers using the previous `execute_code.result` wrapper must update.
- Passed 21 unit tests plus a real five-frame MCP/Houdini cancellation, continuation and single-corrupt-frame repair exercise. Production HIP/HDA hashes remained unchanged.
- Still Mantra + COP2 only. Native Codex tool loading and Karma XPU rendering remain unverified.

## 0.2.0

- Added `set_asset_parameters`: validate numeric parameter batches, reject unknown/animated channels and wrong tuple dimensions.
- Added `render_frames` and `get_render_status`: background Mantra + COP2 preview jobs with HIP/HDA snapshots, durable progress, output hashes and explicit failed/interrupted/unknown states.
- Render workers start through the persistent Houdini owner so they outlive a short-lived MCP client.
- Atomic progress writes retry transient Windows sharing violations.
- Added render lifecycle tests alongside the existing transport suite.
- Validated against a parameterized dot-map and animated route asset in Houdini 20.5.487. Production assets and local evidence are intentionally outside this source repository.

## 0.1.0

- Initial seven-tool MCP stdio bridge to Houdini's main thread.
- Scene/node inspection, trusted Python execution, native screenshot content, explicit save and guarded reopen.
- Local authenticated session descriptor and length-prefixed transport.
- Headless and GUI acceptance flows.
