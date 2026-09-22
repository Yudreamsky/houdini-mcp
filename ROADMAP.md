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

## Added in 0.5: one reusable modeled sample and companion Skill

The pipe-joint/support recipe supplies a self-contained HDA, stable instance upsert, measured geometry checks and four-view/part-type previews. Save/reopen, standalone HDA loading and a Mantra image close the first modeling loop. A same-repository Skill stores tested workflows and pitfalls without duplicating geometry code. See [0.5 validation](docs/V05-VALIDATION.md).

## Next, driven by feedback on this sample

1. Adjust shape, component simplifications and parameter relationships using user feedback or actual dimensions before multiplying asset types.
2. A fixed horizontal 90-degree bend is now delivered in 0.6, with measured matching end rings and explicit end-port centers. Next extend to one branch/tee case only if needed; arbitrary routing and general collision/clearance checks are not delivered.
3. If close-ups or large layouts require them, introduce detail levels and true packed instances, checking both visible result and resource use.
4. Expand XPU to physical materials only with a controlled conversion/render comparison for this sample; current XPU remains map-only.

Each accepted increment updates its relevant Skill reference with conditions, evidence and limits. Ideas remain proposals until implemented and tested.

## Added in 0.6: first routed sample

Two independently sized straight legs connect through a hollow 90-degree elbow. The existing tools select a second recipe without changing old straight asset identity. Matching inner/outer end rings, a shifted-elbow negative case, full/isolated views, save/reopen, standalone HDA and Mantra image validate this bounded route. See [0.6 validation](docs/V06-VALIDATION.md).

## Added in 0.12: one local assembly replacement

`pipe_rack_coupled` composes frozen rack and coupling generators. A saved-baseline comparison preserves 142 non-target parts, while native AABB lower bounds check neighboring supports. Full views, HIP reopen, standalone HDA and Mantra are verified. 0.13 now provides a bounded two-joint chain on the foreground black pipe, with one second-position parameter. Arbitrary joint lists remain deferred until a variable-count case needs them. Upper framing connections remain uncertain and should be studied before construction. See [0.12 validation](docs/V012-VALIDATION.md).

## Added in 0.13: repeated black-pipe connection chain

The seventh recipe retains the coupled rack and adds a second blue joint on pipe 3, with three continuous hollow spans. Native inspection checks interfaces, each joint separately, and the actual axial pipe span beneath every support. A new position parameter is sufficient for this fixed case; no arbitrary list or general replacement API is claimed. 0.14 adds lobes to one blue body; broader propagation and upper-frame attachment interpretation remain future work. See [0.13 validation](docs/V013-VALIDATION.md).

## Added in 0.14: first lobed blue body

One blue body now has a scalloped profile, end collars and actual bolt holes. The bolt-in-hole check distinguishes bounded holes from exterior free space, backed by a rotated-body negative. Other bodies remain as visual comparisons. Next use user feedback on this silhouette before propagating it; upper-frame attachments remain uncertain and need reference interpretation first. See [0.14 validation](docs/V014-VALIDATION.md).

## Later, when repeated work justifies it

0.11 completes the first photo-study component: an independent orange external split coupling with two pipe stubs, actual lug holes and measured interfaces. It uses the existing 22 tools, with save/reopen and standalone-HDA verification. 0.12 has integrated one instance into a separate rack candidate and verified neighboring supports and unchanged-part fingerprints; multiple typed joints and uncertain upper framing remain future work. See [0.11 validation](docs/V011-VALIDATION.md).

2026-09-21 photo-understanding follow-up (documentation only): first prototype one orange external coupling and two short pipes, then validate its interfaces before supporting multiple typed joints. Identify slotted framing by member continuity and attachments, not screen direction; occluded intersections remain uncertain. See [case and implementation boundary](docs/PHOTO-READING-CASE.md). Runtime remains 0.10; no new tool is claimed for this review.

0.10 uses the original photo to refine a separate rack variant and adds exact-part focus. Observed gaps remain: multiple heterogeneous joints per pipe (especially the red pipe's orange external fitting), vertical slotted frames/connection brackets, and photographic camera/material matching. Implement these through specific reference-backed components before assembly animation; do not treat the present flange template as a full photo reconstruction.

0.9 adds the user-approved shared-hanger assembly: three parallel pipes with independent diameters and bottom rises, linked seats/U-bolts and a common channel at each support station. Actual polygon-hole, bearing and neighboring-envelope checks reuse the existing workflow. Arbitrary pipe counts, multiple tiers and engineering component standards remain outside scope. See [0.9 validation](docs/V09-VALIDATION.md).

0.8 applies the first specific visual correction: downward-open U-bolts, pipe bearing and underside hardware in both recipes, with an inverted-clamp negative and local detail views. Old definitions remain inspectable and protected from implicit migration. This improves the existing sample; it does not add a third recipe or engineering component standard.

0.7 improves repeated use before adding components: structured parameter contracts, read-only instance preflight, automatic existing-recipe inference and one reusable acceptance script for both recipes. Future recipes should reuse this lifecycle and add concrete geometry/interface checks, not duplicate machine-specific acceptance scripts.

- Keyframes and saved-scene checkpoints beyond numeric presets.
- Broader camera controls and richer visual acceptance beyond the delivered sample views and basic pixel statistics.
- Generalize the XPU adapter only when another real asset (for example the digital globe) supplies a concrete validation case.
- Reusable delivery checks for HDA packaging, saved scenes and animation outputs.

Keep `execute_code` as the advanced escape hatch. Prefer a small number of reliable workflow tools to a large collection of single-operation wrappers. Ideas listed here are not implemented capabilities.
