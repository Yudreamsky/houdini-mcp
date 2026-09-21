# 0.8 validation — downward-open U-bolts

2026-09-21, Windows / Houdini 20.5.487. MCP 0.8.0, 22 tools, two recipes. This release keeps the approved 0.7 preflight/inference/acceptance workflow and corrects a reference-shape error identified by the user: the pipe fixing should wrap over the pipe with two legs pointing down, rather than form a closed circular clamp.

## Geometry and compatibility

Both recipes now use an upper semicircular round rod and two straight downward legs. The pipe bottom rests on the channel web at Y=0.044m; the center is D/2+0.044. Each leg passes through a real aligned slot, with a washer and hex nut below the web. Rods extend below the nuts. Default straight and elbow assemblies contain 77 and 155 components respectively.

The rod diameter is an illustrative 8mm. Slots use elliptical approximations and locally adjusted spacing. No thread detail or manufacturer/structural specification is claimed. The reference establishes the U shape and opening direction; exact round versus flat section and dimensions remain unmeasured.

Geometry source fingerprints change intentionally. New HDA types are `workai::pipe_support_sample::1.0.f4605171dab8` and `workai::pipe_elbow_sample::1.0.dd9e02aad6fd`. Old saved scenes and libraries remain untouched. Their read-only inspectors preserve legacy closed-ring checks; passing those checks does not imply compliance with the corrected reference. Managed update/preflight rejects old recipe versions, requiring a new instance ID for comparison and delivery.

New straight measurements expose `support_style=u_bolt_v1`, `pipe_web_contact_gaps`, and per-clamp opening, crown gap and leg-hole clearance. Legacy measurements expose `legacy_closed_ring` and the historical contact field. Elbow leg inspection applies the matching style in each leg's local coordinates.

## Actual checks

- 41 unit tests passed, including U orientation, bearing, aligned hole vertices and underside hardware at three diameters (0.1/0.32/0.6m), plus existing topology, volume, end-ring and parameter-contract checks.
- Fresh HOM `tests/u_bolt_acceptance.py` passed. A copy of actual clamp geometry was flipped vertically; the inspector rejected its opening and missing downward legs although the solid remained closed. Both retained 0.5 straight and 0.6 elbow HDAs still passed their version-specific inspection, and update preflight rejected implicit migration.
- Both recipes passed `scripts/accept_asset.py --render` through real MCP SDK stdio: catalog/preflight, create, inferred no-op update, invalid-input/recipe rejection, dimension changes, views, reset, package, save/reopen, standalone HDA rebuild and 960×540 Mantra.
- New straight geometry SHA256: `bab9cfb3e4771d6a1aaa5c76313a212e32cb1849cce8c5e208f2a8337aacbca0`.
- New elbow geometry SHA256: `6a78e82ec866997aa28f472fe25b2595f95a3911ca1fd0daaaa5ba011999f755`.
- Full straight/elbow renders and local detail renders were actually viewed. Detail scenes isolate one original support and shorten the pipe for visibility, without modifying the source HDA. Generic lighting/materials are not a photo-match.
- GUI source restoration returned to the original map at frame 97 with no unsaved changes. Prior map and sample file hashes were checked against the pre-correction record. Source and project Skill structure validation passed.

## Evidence locations

Generated assets and logs are local and intentionally excluded from Git:

| Evidence | Location |
|---|---|
| Straight package, complete GUI report, standalone HDA, views and render | `assets/pipe-support-v02/straight-01/` |
| Elbow package, complete GUI report, standalone HDA, views and render | `assets/pipe-support-v02/elbow-01/` |
| Default render jobs | Straight `bdb1276237cd4f67b966703a1152bfcd`; elbow `9f98d3d564484268a63bacea2b7bc7e5` |
| Fresh HOM negative and legacy reports | `evidence/v08-acceptance/hom-01/report.json` |
| Unit/Skill validation, visual review, final session/process and file fingerprints | `evidence/v08-acceptance/` |
| Detailed preflight/inference workflow acceptance | `evidence/v07-acceptance/`, documented in [0.7 validation](V07-VALIDATION.md) |

## Limits and rollback

This is a bounded visual sample. Geometry checks are selected recipe-specific tests, not general collision detection, engineering approval or a manufacturer's installation standard. U shape alone cannot establish load capacity. Physical-material XPU and native Codex Houdini MCP discovery remain unverified; the actual client used here is external SDK stdio. No global configuration or memory change was made.

Source/Skill rollback baseline is local 0.7 commit `35a4942`, backed up in `evidence/pre-v08-backup`; 0.6 plus the original current-state file is backed up in `evidence/pre-v07-backup`. Confirm no active renders before restoring source and reloading the client. Preserve new HIP/HDA packages: their embedded geometry remains standalone, but older MCP versions cannot manage the corrected recipes. Old visual circular clamps should not be mistaken for an accepted reference match.
