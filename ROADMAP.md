# Iteration roadmap

Improve the MCP through actual asset work. Each increment needs a reproducible scene, visible output and relevant save/reopen checks.

## Delivered in 0.3: session preflight and recoverable rendering

1. `get_capabilities`: distinguish MCP/bridge versions, session identity, active scene, renderer node types and GPU inventory. Native client integration remains independently unverified.
2. `preflight_render`: inspect saved state, HDA/texture/cache dependencies, camera, resolution and output destination before a long render.
3. `resume_render`: retain immutable snapshots, skip hash-verified frames and render only missing/corrupt frames; preserve the original failure record.
4. `cancel_render`, request idempotency and concurrency limits, backed by process identity rather than PID alone.
5. Numeric parameter schemas and presets with animated-channel protection.

## Measured: a standalone Karma XPU preview

A copy of the map was converted to Solaris/USD and MaterialX, rendered with verified OptiX GPU participation and compared at identical camera/frames/resolution. See [results and limits](docs/KARMA-XPU-COMPARISON.md). Low sampling was faster but noisier; higher sampling had similar three-frame total time to Mantra. The original assets remained unchanged.

## Added in 0.4: limited XPU adapter and rendered feedback

Explicit Mantra / Karma XPU selection and preview/final sampling feed the existing cancellation/resume lifecycle. The adapter only accepts the validated emissive-map asset; other objects and materials are not converted. Per-frame OptiX contribution, native verified PNG preview, black/uniform/transparent warnings and scoped timing make actual outcomes inspectable. See [0.4 validation and limits](docs/V04-VALIDATION.md).

## Later, when repeated work justifies it

- Keyframes and saved-scene checkpoints beyond numeric presets.
- Framing controls and richer visual acceptance beyond basic pixel statistics.
- Generalize the XPU adapter only when another real asset (for example the digital globe) supplies a concrete validation case.
- Reusable delivery checks for HDA packaging, saved scenes and animation outputs.

Keep `execute_code` as the advanced escape hatch. Prefer a small number of reliable workflow tools to a large collection of single-operation wrappers. Ideas listed here are not implemented capabilities.
