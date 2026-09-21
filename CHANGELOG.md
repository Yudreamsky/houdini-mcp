# Changelog

## 0.8.0

- Corrected both pipe recipes from closed ring clamps to downward-open round U-bolts following the user's reference correction. The pipe bears on the channel; two legs pass through aligned slots with washers/nuts below. Default straight/elbow assemblies now contain 77/155 parts.
- Added actual U opening, crown/pipe bearing, leg-hole clearance and underside hardware checks. A flipped U-bolt negative fails despite retaining a closed solid mesh. Preserved read-only inspection of legacy HDA geometry; version guards reject implicit migration.
- Both geometry identities change intentionally; existing HIP/HDA files remain unchanged. New visual parameters, including 8mm rods and local slot layout, are illustrative rather than measured product specifications.
- Passed 41 unit tests, fresh HOM negative/legacy acceptance, and both recipes through the reusable real GUI MCP, save/reopen, standalone HDA and Mantra workflow. Added local detail renders and companion Skill lessons about reference shape versus mesh health. See [validation](docs/V08-VALIDATION.md).

## 0.7.0

- Added `preflight_asset_instance` (22 tools total): read-only merged parameter validation and instance/channel guards, with ready, planned values and structured violations. No HDA compilation/installation, parameter writes or explicit geometry cook.
- Catalog now exposes integer/number types and structured cross-parameter rules. Preflight/upsert share preparation; embedded geometry validators remain authoritative. Metadata is outside geometry source so both delivered HDA identities remain unchanged.
- Omitted recipe now infers an existing owned instance's recipe; new instances still default to straight. Explicit recipe mismatch remains rejected; ownership, animated/locked channels, unlocked content and recipe-version guards are preserved.
- Added portable `scripts/accept_asset.py` for the two recipes: real GUI MCP create/update/inspect/views/package/reopen, standalone verification with `scripts/verify_hda.py`, optional Mantra render and source-scene restoration. New output directory and explicit expected clean HIP required; visual review remains separate.
- Added parameter-contract consistency tests and real HOM guard/readonly acceptance. Companion Skill now routes to reusable preflight/acceptance instructions, including failure handling and recipe-inference version differences.
- Passed 40 unit tests, real HOM no-mutation/guard checks, both recipes through the same GUI SDK script with standalone HDA and Mantra, and an expected invalid-update failure with clean source restoration. See [validation](docs/V07-VALIDATION.md).

## 0.6.0

- Added `pipe_elbow_sample`, a fixed horizontal 90-degree route with independently sized inlet/outlet legs, a hollow elbow, two flange joints and repeated supports. The existing 21 tools now serve two recipes; no new single-operation wrappers.
- Preserved straight recipe source and HDA identity. The elbow HDA embeds the original algorithm in a private namespace and remains standalone. Instance recipe changes are rejected; elbow updates must explicitly select the recipe.
- Added actual endpoint-ring matching, port centers, elbow wall/diameter checks and straight-leg validation in each leg's local frame. A deliberately shifted, still-closed elbow is rejected by interface inspection.
- Added three unit tests (37 total) and reproducible `tests/elbow_acceptance.py`. Real GUI MCP creation/update, invalid input/recipe/animation protection, multiviews, save/reopen, standalone HDA and 1280x720 Mantra render passed. Original map and straight sample files stayed unchanged.
- Added an elbow-route Skill reference covering centerline radius, axes, interfaces and verified failure cases. Project Skill discovery is now observed in Codex's available-skill list; native Houdini MCP tool discovery remains independently unverified.
- Scope remains a visual sample, not arbitrary routing, tee fittings, packed instancing, physical-material XPU or engineering certification. See [validation](docs/V06-VALIDATION.md).

## 0.5.0

- Added four tools (21 total): procedural recipe catalog, owned-instance upsert, cooked-geometry inspection and bounded multiview/part-type previews.
- Added a parameterized straight-pipe joint/support sample: hollow pipes, perforated flanges and channels, bolts, washers, nuts, clamps and repeated hangers. Dimensions are illustrative; hidden fittings and threads are simplified. This is not a general pipe router or engineering component library.
- Compile a content-addressed, self-contained HDA from the versioned recipe. Stable instance/part IDs, combined parameter validation, unchanged-input no-op and manual/animated-content protection make repeated use predictable.
- Inspect actual mesh dimensions, closed edges, flange-hole topology, selected bolt clearances/contact and support coverage. Return object transforms separately; no claim of general collision checking or structural certification.
- GUI previews return native PNGs and restore view/display state, including each requested view's camera. Aspect-aware orthographic framing and removal of unused isolation points fixed defects found during visual review. Temporary operations may still mark the scene dirty.
- Added the same-repository `houdini-asset-workflow` Skill with focused modeling/rendering references and evidence-based experience maintenance.
- Fixed render preflight treating generated built-in hlight shadow maps as missing inputs; missing existing/reused shadow maps are still rejected. Verified both modes in real HOM and rendered the sample through Mantra.
- Passed 34 unit tests, real GUI MCP creation/update/multiview/reopen checks, standalone embedded HDA loading and reproducible headless HOM acceptance. Original map files were unchanged. See [validation](docs/V05-VALIDATION.md).
- Physical-material XPU, arbitrary HDA management, full reference-photo reconstruction and native Codex MCP discovery remain outside verified scope.

## 0.4.0

- Added explicit `mantra` / `karma_xpu` and `preview` / `final` options to preflight and rendering. Options participate in request fingerprints. New jobs default to preview (Mantra 2x2; XPU 16), final uses Mantra 4x4 / XPU 64; these are sampling presets, not quality-equivalence claims.
- Added a deliberately narrow USD/MaterialX Unlit adapter for `workai::indonesia_glow_map::2.0`, with emissive material, primitive Cd and orthographic-camera checks. Other assets/materials are rejected; other scene objects/lights are excluded.
- XPU uses one GPU-only husk process per pending frame list, with per-frame OptiX contribution evidence. Frame-boundary cancellation, frozen-input continuation, corrupt-frame repair and original-record retention work on the shared job system.
- Added `get_render_preview` (17 tools total): bounded, hash-verified native PNG ImageContent with raw/composited black, uniform and transparent warnings. Intentional black frames complete with warnings; nonfinite pixels fail.
- Recorded load, USD export, renderer startup/frame/process, composite/inspection and worker wall timings with their measurement boundaries. Reused output evidence retains its source job.
- Added owned renderer process tracking to prevent continuation while an exited worker's renderer is still active. Houdini 20.5's frame-hook exit code 1 is accepted as cancellation only with an explicit stop receipt and all started frames completed.
- Replaced ambiguous `gpu_probe.xpu_render_verified` with inventory `verification_scope`; actual GPU evidence belongs to rendered frames.
- Passed 30 unit tests and real MCP stdio validation: XPU cancel at 2/5, continue to 5/5, repair one corrupt frame, native preview, intentional black warning, Mantra regression and both XPU sampling presets. Source HIP/HDA stayed unchanged. Details: [validation](docs/V04-VALIDATION.md).
- Native Codex tool discovery remains independently unverified; other Houdini versions, general shader conversion and other asset types are not claimed.

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
