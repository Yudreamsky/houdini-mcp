# Iteration roadmap

Improve the MCP through actual asset work. Each increment needs a reproducible scene, visible output and relevant save/reopen checks.

## Next: session preflight and recoverable rendering

1. `get_capabilities`: distinguish MCP/bridge versions, session identity, active scene and available renderers. Verify native client integration separately from external SDK tests.
2. `preflight_render`: inspect saved state, HDA/texture/cache dependencies, camera, resolution and output destination before a long render.
3. `resume_render`: retain immutable snapshots, skip hash-verified frames and render only missing/corrupt frames; preserve the original failure record.
4. `cancel_render`, request idempotency and concurrency limits, backed by process identity rather than PID alone.

## Later, when repeated work justifies it

- Asset parameter schemas, presets, keyframes and checkpointed changes.
- Framing and rendered-image feedback.
- Reusable delivery checks for HDA packaging, saved scenes and animation outputs.

Keep `execute_code` as the advanced escape hatch. Prefer a small number of reliable workflow tools to a large collection of single-operation wrappers. Ideas listed here are not implemented capabilities.
