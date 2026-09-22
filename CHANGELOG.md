# Changelog

## 0.15.0

- Corrected the user-identified construction: `pipe_rack_isolated` replaces the first pipe-3 continuous blue body with one independent rubber buffer per bolt. Default eight pads, 212 parts; 204 saved-baseline parts unchanged. Existing eight generators remain byte-identical; nine recipes reuse 22 tools.
- Inspect actual connected pad meshes, bounded holes, paired bolt axes, flange seating and conservative pad-to-pad air gaps. Nonlinear radius/count/bore checks reject incompatible parameter combinations. Internal flow/seal connection explicitly remains unmodeled; the other two legacy blue bodies await correction.
- Added a separately assigned matte rubber shader in the render demo. Updated the companion Skill to withdraw the old continuous-body interpretation while preserving the proven hole-membership lesson. See [validation](docs/V015-VALIDATION.md).

## 0.14.0

Historical construction interpretation withdrawn in 0.15: the blue components are independent rubber buffers. The following records technical validation of the earlier geometry, not correctness of its construction.

- Added `pipe_rack_lobed`, refining only the first pipe-3 blue body with lobes, end collars, a central bore and actual bolt holes in one welded mesh. One diameter-relative depth parameter; existing seven generators remain unchanged. Eight recipes reuse 22 tools.
- Native body inspection extracts actual end-cap boundary loops, requiring bolts inside bounded holes before testing projected clearance. A half-pitch rotation demonstrated why positive clearance outside the body is not successful hole engagement.
- 69 unit tests and independent native-body/saved-rack HOM checks pass: 204 original parts unchanged, only one body modified; displaced/rotated/blocked-bore/blocked-hole negatives rejected. GUI SDK updates/reset, HIP reopen, standalone HDA and actual Mantra renders pass. See [validation](docs/V014-VALIDATION.md) for GUI/HDA/render evidence and inferred-shape limits.

## 0.13.0

- Added `pipe_rack_repeated`: two blue joints on foreground pipe 3, three hollow spans and one additional second-joint position parameter. Existing six generators remain unchanged; 22 tools serve seven recipes. Fixed two-joint case, not an arbitrary joint-list API.
- Inspect actual axial span coverage, both pipe/body/flange interfaces, each joint's bolt/hole relationships and support-to-pipe interval membership. Moving the second joint preserves the first joint and support geometry.
- 64 unit tests and saved-baseline native HOM checks pass; 160 original parts are unchanged, one original right span changes and 44 parts are added. Displaced/missing spans, displaced body/bolt and support-in-joint negatives are rejected. GUI SDK updates/reset, four-support growth, HIP reopen, standalone HDA and Mantra pass. See [validation](docs/V013-VALIDATION.md) for GUI/HDA/render evidence and limitations.

## 0.12.0

- Added `pipe_rack_coupled`, a separate fixed assembly replacing one red-pipe joint with the verified external coupling. Two additional numeric parameters control shell width and clocking. Five existing geometry generators remain unchanged; the same 22 tools serve six recipes.
- Added conservative native-part AABB separation checks against U-bolts, channels and other neighbors, plus per-part face/type/Cd fingerprints for bounded replacement review. These are not general collision or engineering clearance checks.
- Passed 58 unit tests, actual saved-baseline comparison (142 unchanged parts), moved-neighbor and changed-color negatives, GUI SDK updates/reset, HIP reopen, standalone HDA and Mantra. Companion Skill records inheritance scope and clearance limitations. See [validation](docs/V012-VALIDATION.md).

## 0.11.0

- Added the independent `external_coupling_sample`: two hollow pipe stubs, split orange housings, actual lug holes, paired fasteners and an explicitly inferred seal envelope. Seven numeric parameters include axial position and clocking; existing four recipe algorithms remain unchanged.
- Reused the 22-tool workflow with actual local-frame housing/pipe/hardware measurements, polygon-hole clearance and projected-face axial bore checks. This is a visual sample, not a standard fitting; housing keys, pipe grooves and threads are omitted, and lug meshes overlap housing meshes.
- Passed 54 unit tests, three real HOM displaced-part negatives and old photo-rack fingerprint regression, GUI SDK parameter updates/reset, HIP reopen, standalone HDA and Mantra. Updated the companion Skill with measured behavior and limitations. See [validation](docs/V011-VALIDATION.md).

## 0.10.0

- Added `pipe_rack_reference`, a separate photo-guided variant preserving the three existing recipe identities: coplanar default pipe bottoms, equal black-pipe diameters, folded channel return lips, steel flanges around a thicker blue visual body, and independent joint X offsets. Inferred dimensions and unreconstructed features remain explicit.
- Added exact `part_names` isolation/focus to `preview_asset_views`, intersected with optional type filters. Unknown/empty selections fail, and returned metadata identifies selected names and local bounds. Restored selection after viewer context changes and padded perspective framing after actual GUI tests exposed implicit selection and diagonal-part cropping.
- Joint station conflicts are rejected by recipe validation; actual body/flange/pipe interfaces are measured. The blue body remains a visual fitting envelope, not a manufacturer-identified part.
- Passed 48 unit tests, fresh HOM joint-displacement negative and old-rack regression, full GUI SDK/HIP reopen/standalone HDA/Mantra, and exact-part focus/rejection/restoration checks. Failed development runs are retained separately. See [validation](docs/V010-VALIDATION.md).

## 0.9.0

- Added `pipe_rack_sample`: exactly three parallel pipes with independent diameters, walls, bottom rises and two horizontal center spacings. Every support station has one shared channel and two outer hangers; each pipe has a downward-open U-bolt. Nonzero rise creates a simplified bearing seat, with the U-bolt still reaching through the shared web.
- Existing 22 workflow tools now serve three recipes. Added multi-field `terms` to structured constraint right-hand sides for hanger height and conservative flange clearance. Existing right/scale contracts and straight/elbow HDA identities remain unchanged.
- Inspect actual pipe/flange envelopes, shared span/counts, bearing seats, U orientation, polygonal hole clearance and underside hardware. Missing-seat, moved-pipe and missed-hole negative cases fail in actual HOM. This is not general collision checking or engineering certification.
- Extended the reusable GUI acceptance script and companion Skill. Passed 45 unit tests, real HOM assembly/negative checks, unchanged straight/elbow inspection and no-op updates, full GUI MCP create/update/views/package/reopen, standalone HDA and actual Mantra renders. See [validation](docs/V09-VALIDATION.md).

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
