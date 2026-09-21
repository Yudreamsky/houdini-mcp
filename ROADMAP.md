# Iteration roadmap

Improve the MCP through actual asset work. Each increment needs a reproducible scene, visible output and relevant save/reopen checks.

## Delivered in 0.3: session preflight and recoverable rendering

1. `get_capabilities`: distinguish MCP/bridge versions, session identity, active scene, renderer node types and GPU inventory. Native client integration remains independently unverified.
2. `preflight_render`: inspect saved state, HDA/texture/cache dependencies, camera, resolution and output destination before a long render.
3. `resume_render`: retain immutable snapshots, skip hash-verified frames and render only missing/corrupt frames; preserve the original failure record.
4. `cancel_render`, request idempotency and concurrency limits, backed by process identity rather than PID alone.
5. Numeric parameter schemas and presets with animated-channel protection.

## Proposed next: a measured Karma XPU preview

Convert a copy of the accepted map to Solaris/USD and MaterialX. Render the same camera/frame/resolution with Mantra and Karma XPU, verify that the GPU actually participates, compare visible emission/bloom/color and wall-clock time, then add a renderer selection to the MCP if the result is useful. No performance claim or automatic production-scene conversion before this comparison.

## Later, when repeated work justifies it

- Keyframes and saved-scene checkpoints beyond numeric presets.
- Framing and rendered-image feedback.
- Reusable delivery checks for HDA packaging, saved scenes and animation outputs.

Keep `execute_code` as the advanced escape hatch. Prefer a small number of reliable workflow tools to a large collection of single-operation wrappers. Ideas listed here are not implemented capabilities.
