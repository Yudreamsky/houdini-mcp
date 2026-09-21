# 0.9 validation — three pipes on shared hangers

2026-09-21, Windows / Houdini20.5.487. MCP0.9.0, 22 tools, three recipes. User approved one bounded assembly: three parallel pipes with separate diameters, spacings and heights, sharing each transverse support. Source/Skill were backed up before editing; old assets are retained.

## Geometry and parameters

`pipe_rack_sample` runs along X, arranges pipes across Z, with Y up. Pipe 2 is at Z=0; pipe 1 is at -spacing_12 and pipe 3 at spacing_23. Independent diameter_i/wall_i/rise_i parameters accompany common length, support_pitch, hanger_height, bolt_count and segments. Rise means pipe bottom elevation above the web, not center elevation.

Each station has one continuous perforated channel, two outer hanging rods and three downward-open U-bolts. Nonzero rise creates a simplified solid bearing seat; zero rise rests the pipe directly on the web. U legs still pass through the same web, with washers/nuts below. Slot positions follow the actual legs. The channel endpoints follow the outer pipes, with illustrative edge allowances.

Default dimensions are length2.4m, diameters0.32/0.25/0.20m, center spacings0.60/0.55m and rises0/0.10/0.02m. Default mesh: **191 parts, 20,672 points, 20,284 primitives, two support stations**. All dimensions, round rods, slot pattern, seats and anchors are visual examples, not manufacturer or structural specifications.

The preflight constraint for adjacent center spacing is conservative: >=0.775 times the sum of diameters +0.04m, leaving flange-envelope clearance regardless of rise. Hanger height must clear each diameter+rise+0.2m. Structured constraints introduce `terms={parameter:coefficient}` plus offset for multiple right-hand fields; existing right/scale rules remain valid. Geometry validators remain authoritative.

## Verification performed

| Check | Observed result |
|---|---|
| Unit suite | 45 passed. Four new tests cover closed positive-volume meshes, shared counts, changed dimensions, all-zero-rise minimum-diameter case, stable support names, height-only beam invariance, three negative cases and 36 contract combinations. |
| Real HOM rack | Default build passed. Missing middle-pipe bearing seat, middle-pipe displacement, and 12mm U-bolt lateral shift each failed actual mesh inspection. Invalid spacing preflight preserved current parameters; omitted-recipe update grew from two to four stations and reset reproduced the initial geometry hash. |
| Existing assets | Delivered 0.8 straight and elbow HIPs passed inspection, preflight and no-op upsert; geometry hashes stayed `bab9cfb3e4771d6a1aaa5c76313a212e32cb1849cce8c5e208f2a8337aacbca0` and `6a78e82ec866997aa28f472fe25b2595f95a3911ca1fd0daaaa5ba011999f755`. Their generation source files and embedded recipe identities were not changed. |
| GUI SDK workflow | The existing `scripts/accept_asset.py` now accepts the rack recipe. Catalog, read-only preflight, create, inferred no-op, invalid values/recipe refusal, growth, views, reset, package, reopen and standalone verification all passed. |
| Parameter growth | Length3.6m, diameter1=.45m, diameter2=.30m, spacings.75/.65m and rises.06/0/.16m produced 247 parts and four support stations. Default reset returned 191 parts and the same geometry fingerprint. |
| Independent HDA | HDA rebuilt in fresh hython without repository src on sys.path; actual geometry matched the delivered instance. |
| Images | Full assembly 960×540 Mantra and a 1200×900 one-support detail completed with no pixel warnings. Full render, end/top views, grown perspective and detail were actually viewed. The detail uses three shortened pipe sections to expose the shared support; the HDA is untouched. |

New HDA type: `workai::pipe_rack_sample::1.0.0d2ed51d54a9`.

Default geometry SHA256: `7d4ed8107afff2da5fd4b4652a732013155fcda9915b17265757f7d10e999f48`.

Inspection extracts actual parts from the cooked mesh. Existing pipe-joint checks operate on copied per-pipe geometry in its local frame. The new assembly check measures pipe/flange envelopes, bearing paths, beam bounds, fastener positions and holes. For a rod hole, its center must lie inside the web outline but outside all top-surface polygons, and its radius must be less than the distance to polygon edges. This improves on a nearest-vertex estimate for this new assembly; it is not a generic collision engine.

## Local evidence

Generated scenes, HDA and raw logs are excluded from Git:

- `assets/pipe-rack-v01/default-01/`: sample.hip, render-demo.hip, instance.json, HDA, standalone.json, report.json and default/updated views.
- Full render job `b220c6f4c51e4181a6f6aec75b2a56d7`; detail job `479c701038c542829fd8ee2ba500a123`.
- `evidence/v09-acceptance/hom-01/report.json`, from published `tests/rack_acceptance.py`.
- `evidence/v09-acceptance/elbow-regression-01/report.json`: existing elbow HOM creation/update/guards/save-reopen and displaced-elbow negative passed after the shared inspection refactor. Its catalog assertion now allows additional recipes.
- `evidence/v09-acceptance/`: unit/Skill logs, visual review, prior/current asset fingerprints and final session/process verification.

## Limits and recovery

Fixed three-pipe layout and common length/pitch only; no arbitrary routing, multilayer racks, load calculations, full collision detection or manufacturer-standard seats/holes. Render lighting is generic; all small threads and installation details are not modeled. Parameter declarations do not establish engineering compliance.

Actual MCP calls used external SDK stdio. Native Codex Houdini tool discovery remains independently unverified. Companion project Skill remains discoverable through its existing junction. No global configuration or memory was modified.

Previous geometry/render evidence is inherited only where source and file fingerprints match. The two old recipes were checked with HOM in this release; their full GUI render lifecycle was not rerun. Existing render lifecycle code is unchanged.

Rollback baseline: `0ba5b54494baf7b706b105e08deae6f70bca4ed8` (0.8), backup `evidence/pre-v09-backup`. After checking for active renders, restore source/Skill and reload the client. Preserve the new scene/library: the HDA remains independently loadable, but old MCP has no rack recipe management.
