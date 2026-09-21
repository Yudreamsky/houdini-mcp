# Changelog

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
