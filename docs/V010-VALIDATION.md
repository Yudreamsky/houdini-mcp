# 0.10 validation — photo-guided local modeling and part focus

2026-09-21, Windows/Houdini20.5.487, MCP0.10.0: 22 tools, four recipes. User asked to keep modeling toward the supplied field photo and identify capability gaps before assembly animation. This release refines a local three-pipe node study; it does not reconstruct the entire ceiling scene.

## Reference interpretation and geometry

The original image and the user's inverted-U correction were viewed. Existing generic riser blocks were not evidenced by the photo. A separate `pipe_rack_reference` defaults to zero rise, similarly sized black pipes, folded channel sides with return lips and small chamfered outer corners. These defaults are adjustable interpretations, not measurements of actual installation heights or standard channel sizes.

The blue joint now has visible axial thickness between steel-colored flanges. The original fitting's identity and internal function are unknown; its lobed exterior and product details are not reproduced. The red pipe still uses this template rather than its photographed orange external fitting. There is still one joint per pipe; repeated joints, vertical slotted framing, brackets, ducts and ceiling are explicit remaining gaps.

`joint_offset_1/2/3` move each fitting, fasteners and adjacent inner pipe ends while retaining outer pipe endpoints. Body length is an illustrative 88mm. The recipe rejects overlap with a support station. This nonlinear station check runs after declarative constraints and is disclosed by catalog.validation_notes, rather than being misrepresented as a fully declarative linear rule.

Default result: **187 components, 20,296 points, 19,892 primitives**. HDA `workai::pipe_rack_reference::1.0.4dbf1e15fcbd`; geometry SHA256 `f0b7052ea2af278d5ee6f2e8188c47a32e4903d7d34d22192d8b49a120363764`. The base straight, elbow and rack generation files remain byte-identical to 0.9; old recipe identities are retained.

## Tool improvement and actual checks

`preview_asset_views` accepts 1–128 exact unique existing part_names. Optional part_types intersects that selection; unknown names, empty lists and empty intersections fail before view mutation. Temporary filtering frames only selected geometry and returns names/bounds alongside native PNGs. Actual selection restoration was fixed after discovering that viewer.setPwd could implicitly select the host object. Perspective framing gained conservative aspect padding after a long diagonal support was visibly cropped. Padding may leave generous margins.

| Verification | Actual outcome |
|---|---|
| Unit suite | 48 passed, including closed positive-volume reference geometry, zero default seats, offset joint/pipe-end continuity and support-conflict rejection. |
| Fresh HOM | Default variant passed. Moving the middle blue body 10mm failed measured joint interfaces. Conflicting offset/pitch was refused by preflight. The original 0.9 rack still passed with geometry hash `7d4ed8107afff2da5fd4b4652a732013155fcda9915b17265757f7d10e999f48`. |
| GUI SDK workflow | Catalog/preflight/create/inferred no-op/invalid values and recipe refusal/update/views/reset/package/reopen/standalone HDA/Mantra passed in `default-02`. |
| Exact-part focus | `part-focus-04` passed support/joint selection metadata and bounds, three invalid filters, restored child/display/render/selection state and unchanged source geometry. Original map scene restored cleanly. |
| Actual images | Full Mantra, short-pipe support detail, focused joint/support images were viewed. Latest focused support is fully in frame. Fine underside hardware remains partly occluded; geometric checks and visual clarity are separate evidence. |
| Preservation | 47 prior HIP/HDA files remained byte-identical; three old generation sources unchanged. Source scene returned to the original map, frame97, clean. |

## Evidence and development failures

- `assets/pipe-reference-v01/default-02/`: delivered sample.hip, HDA, instance.json, standalone.json, report.json, views, render-demo.hip and render-0.png.
- Full render job `05ee0de4b0e34fdeb1bd8659c89069a1`; support detail job `4c04571449f34d51840ba6dd87b0d787` (1200×900, shortened pipe sections for visibility, source HDA untouched).
- `evidence/v010-acceptance/hom-01/report.json`, from published `tests/reference_acceptance.py`.
- `evidence/v010-acceptance/part-focus-04/report.json`, from published `tests/part_views_acceptance.py`.
- The first GUI run `default-01` failed on a preview-module syntax error, then restored the original scene. The source was corrected and compiled before a fresh output directory was used. It is not a passed delivery.
- `part-focus-01/02` failed selection restoration; diagnostic snapshots showed only an unwanted selected host object. The restoration order was fixed. `part-focus-03` passed technical checks but its support perspective cropped the beam; `part-focus-04` passed after aspect padding and was visually checked. Failures and intermediate images remain available.
- Local reference photo, analysis, generated scenes and raw evidence remain excluded from Git. Only source, tests and generic documentation are published.

## Remaining gaps and recovery

Priority gaps are multiple different joints on one pipe, the red external coupling, vertical slotted frame/bracket connections, and camera/material matching. Current dimensional defaults, channel orientation/back faces, seats and fitting internals are not engineering evidence. Render lighting is generic; there is no photographic reconstruction claim.

Native Codex Houdini tool discovery remains unverified; actual calls used external SDK stdio. Skill remains project-scoped; no global configuration or memory changes. Existing renderer lifecycle code was unchanged, so unrelated map/XPU/video jobs were not rerun.

Rollback baseline `3e6306d36c5903ec3d476c884442de4ecbc223cd` (0.9), backup `evidence/pre-v010-backup`. Check active renders before restoring source/Skill and reloading MCP. Preserve new HIP/HDA; its embedded algorithms remain standalone, but old MCP cannot manage the new recipe.
