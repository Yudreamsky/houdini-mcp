# 0.6 validation

2026-09-21, Windows / Houdini 20.5.487. External MCP 0.6.0 exposes the same 21 tools and two recipes. Real GUI calls used SDK stdio; no claim that native Codex Houdini tools have loaded. The companion Skill is now present in Codex's available-skill list and was read through its project entry.

## New sample and measured result

`pipe_elbow_sample` connects two straight legs with one horizontal 90-degree hollow elbow. Each leg reuses the original flange joint and hanger assembly. Y is up; inlet follows +X and outlet follows +Z. Default straight lengths are 2.4 m / 1.8 m, centerline bend radius 0.6 m, diameter 0.32 m, wall 0.008 m, support pitch 0.9 m, hanger height 1.2 m, eight bolts per joint, 48 cross-section / 24 bend segments. Dimensions remain illustrative.

Default output: 139 components, 16,064 points, 15,792 primitives, four support groups. HDA type `workai::pipe_elbow_sample::1.0.c5d291ef5bf5`; geometry SHA256 `35bac19aa4a8f57b37a1daf5f646362b6493b76b7059bb21629edf3d4c4f7cb6`.

Both internal interfaces have 96 versus 96 actual inner/outer boundary vertices, with maximum nearest-vertex matching error 0.0 at the default parameters. Actual measured diameter approximately 0.32000006 m and wall 0.00800006 m. End-port centers match (-2.4, 0.212, 0) and (0.6, 0.212, 2.4) within floating-point tolerance. Reported directions describe the fixed recipe's end planes, not a general connection solver.

## Checks performed

| Check | Actual result |
|---|---|
| Unit tests | 37 passed, including three new tests for combined constraints, elbow manifold edges/winding/positive volume and matching end rings across different parameters, stable part identity and endpoint/support linkage. |
| Headless HOM | `tests/elbow_acceptance.py` created both recipes, verified original straight hash, rejected bad radius/diameter and recipe changes, updated dimensions, packaged HDA, saved/reopened and matched geometry. |
| Negative inspection | Shifted only the elbow geometry by 0.01 m in an inspection copy. The mesh remained closed; dimensional and both endpoint-ring checks correctly failed. Production/HDA geometry was not edited by this test. |
| GUI MCP | Actual catalog/upsert/inspect/preview/save/open/render calls. Same ID/parameters returned no change, one object and saved clean state. Invalid radius combination, same-ID recipe replacement and animated inlet length were rejected. |
| Parameter linkage | Inlet 4.2 m, outlet 3.6 m, diameter 0.5 m and radius 0.9 m passed; supports increased four to eight while retaining existing part names. Returned to defaults and reopened successfully. |
| Visual review | Full front, right, top and perspective, grown top/perspective, isolated elbow and supports captured. Reviewed complete L layout, both legs, end opening, flange hardware and support orientation. No full ceiling scene is implied. |
| Standalone HDA | Fresh hython without repository src on sys.path installed the delivered HDA, applied instance parameters and reproduced the same geometry hash. |
| Mantra | Job `8c804d292bdf45f4bed75ee9dde9d56f`, 1280x720, final 4x4 samples completed. Verified native PNG, no pixel warnings, actual image visually checked. Simple presentation lighting, not photograph matching. |
| Existing assets | Original map HIP/HDA and delivered straight sample HIP/demo/HDA byte hashes stayed unchanged. Existing straight instance upsert under new code preserved clean state and geometry hash `003557c7280606753d40662751ce954779cfdddeae724b7e29462a9ef8504e27`. |

The first headless acceptance attempt hit an invalid Python node handle after HIP reload; the test now resolves the stored path after reload. The failed run remains under `hom-01`; `hom-02` passed. This was a test-harness lifetime error, not accepted evidence or a geometry correction.

## Local evidence and delivery

Source repository excludes machine configuration, credentials, supplied photographs and generated assets/evidence.

- Delivery index: `assets/pipe-elbow-v01/README.md`; accepted asset directory `assets/pipe-elbow-v01/afb958e4/` contains HIP, HDA, parameters, views, Mantra image and standalone verification.
- GUI SDK report: `evidence/v06-acceptance/acceptance-afb958e4.json`.
- Reproducible HOM report: `evidence/v06-acceptance/hom-02/report.json`.
- Unit log, Skill validation and final session/process evidence: `evidence/v06-acceptance/`.

## Limits and rollback

This is a fixed horizontal 90-degree visual recipe. No variable-angle/multi-point routes, tee/branch, generalized collision detection, simulation mesh, LOD, packed instances or physical-material XPU were added. R >= 1.5D is a recipe constraint, not an engineering standard. Component walls have closed touching end faces at internal interfaces; the bore remains open, but parts are not fused into a single simulation mesh.

Inspection measures local-space geometry and returns the object transform separately. It does not derive engineering compliance. The two straight-leg checks run in their respective local frames; top-level part bounds are in asset coordinates. The existing GUI preview dirty-state caveat remains.

The original straight source is unchanged. The elbow HDA embeds it in a private module namespace to avoid rebinding its global parameter definitions. Both sources contribute to the elbow version hash, so future code changes cannot silently migrate old instances.

Rollback baseline is `bccda9d1442e2ddee73b781f67a082530d220cf5` (0.5.0), with local pre-change backup `evidence/pre-v06-backup`. Confirm no active render, restore source and reload MCP. Preserve new HIP/HDA files separately; their embedded geometry is standalone, while 0.5 does not manage the elbow recipe. Project Skill uses the same canonical repo directory and requires no new installation/configuration change.
