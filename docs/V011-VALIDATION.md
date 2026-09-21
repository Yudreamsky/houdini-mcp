# 0.11 validation — external coupling visual sample

2026-09-21, Houdini20.5.487 on Windows; external SDK MCP stdio. MCP0.11.0, 22 tools, five recipes. The user approved the bounded next sample from the photo study, with experience retained in the companion Skill.

## Delivered scope

`external_coupling_sample`: two hollow short pipe sections, two orange housing halves, four lugs with actual through holes, two bolts/heads/nuts, four washers and an inferred seal envelope: **19 named parts, 2,620 points, 2,552 primitives**.

Parameters: total length, outside diameter, wall, shell width, joint X offset, clocking about X in degrees, circular segments. Defaults are 0.8m / 0.32m / 0.008m / 0.09m / 0m / 25deg / 64. All dimensions and rear/internal interpretation are illustrative. Clocking leaves the pipe meshes unchanged; moving the joint preserves the exterior pipe endpoints. The numeric contract leaves at least 80mm pipe beyond either shell end, a recipe restriction rather than a construction rule.

HDA `workai::external_coupling_sample::1.0.fcee6249d884`. Default geometry SHA256 `5f7758be3c6160c4a2074c26427b9b25e91951b52f35edfb9471aa79383ccbc1`. Generated files remain local under `assets/coupling-v01/default-01`.

This is not yet installed into the three-pipe sample. The four previous generation modules and old HIP/HDA files are preserved. No new generic assembly API or joint-list input is claimed.

## Actual verification

- **54 unit tests** passed. New coverage includes closed consistently oriented positive-volume parts; the actual axial bore and lug hole clearance; 15 diameter/clocking combinations; parameter-contract agreement; unchanged pipe meshes under clocking; shifted pipe/housing/bolt negatives; shifted seal and flow-bore obstruction negatives.
- Fresh **HOM** `tests/coupling_acceptance.py` creates the asset and modifies native polygons independently. A pipe shifted 20mm off axis, a housing shifted 20mm axially, and a bolt moved 20mm from its lug are each rejected. Invalid end clearance is refused before parameter mutation. The old photo rack retains its accepted geometry SHA `f0b7052ea2af278d5ee6f2e8188c47a32e4903d7d34d22192d8b49a120363764`.
- **GUI MCP SDK** `scripts/accept_asset.py --recipe external_coupling_sample`: catalog, non-mutating preflight, creation, inferred no-op, invalid wall and recipe rejection, update/reset, multiview, HDA packaging, HIP reopen, independent hython reconstruction without repository src and full Mantra render passed.
- Updated instance used length1m, diameter0.4m, shell_width0.12m, offset0.12m, clocking-35deg. Reset reproduced the default fingerprint.
- Additional actual SDK part-name previews isolate housings/lugs/fasteners. The final saved sample passes the expanded seal/bore inspector and retains its geometry fingerprint. Original map/frame97 is restored cleanly in each workflow.

Actual checks measure extracted polygons after undoing the clocking transform. Lug-hole clearance tests polygon coverage and distance to edges, not merely bolt centers. Axial clearance uses face projections to detect a face spanning the bore even if its vertices are outside it. These are bounded interfaces, not a general collision or structural design analysis.

## Visual review and evidence

The full render and end/side views distinguish the external housing from the earlier double-flange template. The isolated end view shows two shell halves and both fastener stations. The first lower-angle detail render was technically completed but too dark to judge the underside; a stronger fill overexposed surfaces, so a separate balanced-lighting candidate was produced. Intermediate HIP/PNG/job evidence remains preserved. Near views intentionally frame the coupling; a separate full view covers both pipe ends.

- `evidence/v011-acceptance/unit-tests.txt` and `hom-01/report.json`.
- `assets/coupling-v01/default-01/report.json`, `instance.json`, `standalone.json`.
- Full Mantra job `0e791b8862f14734a661f6c42bba0d5b`, 960x540.
- First underside detail `7334f0a884b64c0781f09c21612d1d71`; strong-fill candidate `4c9bd36d6e9c408eba8225cda835c9ea`, both 1200x900. Latest detail metadata and visual assessment are in `evidence/v011-acceptance/detail-balanced-report.json` and `visual-review.json`.
- Final source/asset preservation and session evidence: `artifact-verification.json`, `final-session.json`, `process-verification.json` in the same evidence directory.

The final unit suite includes the additional seal check added after the first GUI run. The final SDK detail workflow re-inspected the saved native geometry with that checker; unchanged save/reopen and generation were not redundantly rerun.

## Limitations, experience and rollback

The model interprets a photographed external silhouette. It does not identify a manufacturer, model, pressure rating or actual dimensions. The rear half is inferred symmetric. Housing and lug meshes deliberately overlap as a visual casting approximation; they are not one fabrication solid. Grooved pipe ends, housing engagement keys, real seal profile, threads, wear and photo-matched material are not implemented. A positive-volume closed mesh and open bore cannot validate sealing or load capacity.

The companion Skill records local-frame inspection, named-part isolation, inferred internals and the observed lower-view lighting failure. E001/E006 guided end/side/oblique and visual-before-numeric review; E008 preserves the source and old assets. Native Codex Houdini-tool discovery remains unverified; actual transport is external SDK stdio.

Rollback source/Skill to `de0baa7c0f2669eff960ce6c16cc86fccf181451` or `evidence/pre-v011-backup` after checking for active renders, then reload MCP. Preserve the new HIP/HDA; it remains standalone but the previous server does not manage the fifth recipe. No global Skill/configuration or memory changes.
