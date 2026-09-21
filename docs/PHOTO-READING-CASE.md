# Photo understanding before procedural expansion

2026-09-21, documentation-only follow-up to MCP 0.10. No new geometry recipe, runtime tool or version release in this increment.

## Observed failure pattern

The three-pipe template passed geometric checks but used the same flange/body construction for visually different joints. Its round hangers also did not reproduce the reference's slotted framing. A model's topology and parameter tests cannot establish reference fidelity.

The local review now separates visible features, user-specified U-bolt orientation, plausible interpretation and occluded geometry. Screen diagonals are not world verticals: trace a member across pipes and nearby fixings before assigning its role. A crossing in the photo alone does not establish a connection.

Reference names remain descriptive: orange external coupling and blue connection body. Manufacturer information supplies analogies only: [Victaulic grooved technology](https://www.victaulic.com/grooved-technology/), [I-177N reassembly, page 5](https://assets.victaulic.com/assets/uploads/literature/I-177N.pdf), and [Hilti MP-UB](https://www.hilti.com.qa/c/CLS_MODULAR_SUPPORT_SYSTEM/CLS_PIPE_SUPPORTS/r12293802). None identifies the photographed products or licenses transferring their dimensions and engineering specifications.

## Implementation order derived from the review

1. Prototype one distinct external coupling with two short coaxial pipe ends. Separate housings, seam/lugs and fasteners; label hidden geometry as inferred.
2. Inspect actual axial passage, housing and fastener alignment in end/side/oblique views. Use deliberate shifted-pipe, shifted-housing and misplaced-fastener negative cases before claiming validation.
3. Integrate only after save/reopen and standalone-asset checks. Preserve the existing model and compare unchanged neighboring parts.
4. Then add a structured list of stable-ID joints; do not force an array through the current numeric parameter interface. Revisit slotted framing when its attachment interpretation is sufficiently constrained.

The current source confirms the boundary: reference_geometry has one scalar offset per pipe; procedural_assets advertises structured_inputs=false; recipe_contract expects finite numbers. Generic execute_code flexibility is not a supported reusable assembly API. Current inspect/preview part-name selection can already support visual study, so no new inspection tool is proposed merely for this step.

## Evidence and limits

Local-only artifacts: assets/photo-study-v01/STUDY.md, review.html, the original image and the user's annotated correction. They contain localized observations and the next sample's acceptance criteria. The photo and derived review are excluded from Git.

This increment checks documentation, current source boundaries, review-page static references and Skill structure. The embedded browser blocked opening the local file URL; page rendering and button behavior are not browser-verified. No alternate browser route was attempted. It does not rerun Houdini, render a new model or establish an engineering design. Implementation checks above are future acceptance criteria, not completed tests. Skill backup is in evidence/photo-study-v01/backup; revert this documentation commit to undo the guidance change.
