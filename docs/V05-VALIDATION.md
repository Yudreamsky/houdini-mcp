# 0.5 validation and limitations

Validated 2026-09-21 on Windows, Houdini 20.5.487 / Python 3.11.7. External MCP server 0.5.0 enumerates 21 tools. The existing GUI bridge remains 0.1.0 and dynamically loads operation modules. These are real SDK stdio calls to the MCP server; native Codex discovery is independently unverified.

## Delivered sample

`pipe_support_sample` is a representative straight pipe connection and hanger assembly, not a reconstruction of the whole supplied ceiling photograph. Metre-based default parameters: length 2.4, outer diameter 0.32, wall 0.008, support pitch 0.9, hanger height 1.2, eight flange bolts and 48 circular segments. No dimension is claimed to be measured from the photograph.

Default output: 69 named components, 6,832 points and 6,696 primitives. Geometry SHA256 `003557c7280606753d40662751ce954779cfdddeae724b7e29462a9ef8504e27`; recipe source produces HDA type `workai::pipe_support_sample::1.0.2d42ebe19614`. The fingerprint covers primitive names/indices and point positions, not materials or all Houdini attributes.

The mesh includes hollow pipes, two flanges with actual bores/bolt holes, gasket, bolt shafts/hex heads/washers/nuts, perforated channel webs/lips, clamps, hanger rods/nuts and simplified anchor plates. Slot shapes are elliptical approximations; threads, hidden building attachments and surrounding roof/ductwork are omitted. No engineering standard, load capacity or installation compliance is asserted.

## Actual checks

| Check | Result and scope |
|---|---|
| Unit tests | 34 passed: prior transport/job tests plus invalid recipe inputs, component topology/winding/positive volume, stable part identity and flange-hole Euler characteristic. |
| Real GUI MCP | New catalog/upsert/inspect/preview tools called through stdio. Same instance/parameters created no duplicates and preserved the saved GUI clean state. Invalid inputs and animated channels were rejected without altering geometry. |
| Dimensional linkage | Diameter 0.32 → 0.5 and length 2.4 → 3.6 updated the assembly; supports increased 2 → 4 and retained existing part IDs. Actual geometry checks passed; reset to defaults passed. |
| Geometry inspection | Measured diameter, wall, length, flange diameter, bolt count/circle, bolt span and hole clearance; checked closed edges, nonzero faces, flange-hole topology, selected clamp/web contact and support coverage. Default minimum bolt-hole radial clearance was approximately 0.0048 m. |
| Visual review | Viewed full front/right/top/perspective, grown assembly and isolated supports. Found and fixed cropped orthographic views and orphan points in filtered previews. Display-state restoration was checked. These are geometry review images, not shader validation. |
| HIP save/reopen | Explicit local HDA dependency selected, scene saved and reopened; measured checks and geometry hash matched. |
| Standalone HDA | Separate hython process without repository src on sys.path loaded the delivered HDA and applied saved instance parameters; identical geometry hash. Geometry code is embedded in PythonModule. |
| Reproducible HOM test | Published `tests/procedural_acceptance.py` passed in fresh hython: combined validation, same-instance update, unlocked/animated content protection, linkage, HDA packaging and reopen. This test does not claim MCP/GUI coverage. |
| Mantra | Real MCP render job completed at 960×540, final 4×4 samples; native preview returned, no pixel warnings. Image visually checked for the assembly, visible pipe opening, flange hardware and perforated channels. Lighting/materials are a simple presentation, not photographic matching. |
| Shadow-map regression | Generated hlight shadow-map destinations no longer trigger a false missing-input error. Existing-map mode still flags a missing file. Real HOM test checked both branches; unrelated dirty-state errors were retained. |
| Skill | Canonical repo Skill and project-linked folder both passed skill-creator validation. Project junction points to the repo source. Discovery by a new Codex turn remains a separate check. |
| Original assets | Original map HIP/HDA SHA256 unchanged. GUI restored to original map at frame 97, unsaved_changes=false; final ping reports external MCP 0.5.0. |

## Evidence retained locally

Assets, supplied photograph, session credentials and raw render evidence are intentionally not uploaded to the source repository. Local delivery index: `assets/pipe-support-v01/README.md`.

- Latest full GUI SDK acceptance: `evidence/v05-acceptance/acceptance-b77c6248.json`.
- Delivered sample, demo scene, HDA, instance parameters, views and standalone report: `assets/pipe-support-v01/872926b7/`.
- Mantra report: `evidence/v05-acceptance/final-sample.json`, job `cee403cc61834229b2f4f6f7b9b2c3e5`.
- Reproducible HOM result: `evidence/v05-acceptance/reproducible-hom-02/report.json`.
- Shadow-map regression: `evidence/v05-acceptance/shadowmap-regression.json`.
- Unit output and final state/hash verification: `evidence/v05-acceptance/unit-tests.txt`, `final-verification.json`.

Intermediate failures are retained. Hython can report dirty state immediately after saving, so the headless acceptance asserts idempotent geometry/instance behavior; clean-state preservation was checked in the real GUI. The first headless run's failed dirty-state assertion was not treated as acceptance.

## Boundaries and recovery

Only this recipe is managed; arbitrary HDA installation, pipe routing, general collision detection, packed instancing, LODs, cross-application export and physical-material XPU are not implemented by this increment. XPU remains limited to the prior emissive map. Prior XPU cancellation/resume evidence is inherited because those execution paths were unchanged; no new performance claim is made.

Multiview capture temporarily changes visibility/filter nodes and restores UI state, but may mark the scene dirty. Save a working checkpoint first and save the intended result after review. Inspection reports local dimensions and a separate object transform, not world-scale compliance.

Recipe hashes prevent silent migration; unlocked HDA contents and animated/locked channels are protected. On recipe changes, retain the old instance and create a new one for comparison. Do not overwrite production files to test the new recipe.

Pre-0.5 source/state backup is retained locally under `evidence/pre-v05-backup`. Source baseline is commit `2668cff3a8d5d0c12104219856ba35e29134afdd` (0.4.0). After confirming no active render, restore that baseline and reload the MCP client to roll back tools. Keep new sample HIP/HDA files separately; their embedded geometry remains loadable, but 0.4 does not expose the new managed tools. Remove only the project Skill junction if reverting that installation; retain the canonical source and evidence.
