# 0.4 validation — 2026-09-21

Environment: Windows, Houdini 20.5.487 / Python 3.11, RTX 4090. The test client used the real MCP SDK over stdio, calling the dedicated GUI bridge and durable hython/husk workers. This does not establish native Codex tool discovery.

## Verified

- All 17 tools were enumerated; external server reported 0.4.0. The existing GUI's base bridge remained loaded at 0.1.0; operation modules reload independently.
- Correct map preflight passed. Unsupported asset type and invalid renderer were rejected. Repeated requests returned the same job; changing renderer or quality under the same request ID failed.
- A five-frame XPU preview at 320x180 rendered frames 97 and 98, then cooperatively cancelled. A child job copied these verified frames and rendered 99–101. The original status record's hash did not change.
- After deliberate corruption of frame 99's test PNG, preview rejected its changed hash. A new child reused four frames and rerendered only frame 99. Unchanged-frame PNG hashes remained equal; requesting resume on the fully verified result did not create another job.
- Every new XPU output had completed-frame OptiX statistics naming RTX 4090 with 100% contribution. CPU Embree was disabled. Reused outputs retain their evidence and source-job identity.
- `get_render_preview` returned actual ImageContent PNG bytes matching the manifest hash. Source EXR and composited pixels were finite and nonuniform for normal map outputs. Visual inspection showed the blue dotted map and glow.
- A worker-only `intensity=0` override produced a completed, visibly black image with `all_black_or_empty` warning. The GUI parameters and source scene were untouched.
- Mantra final (4x4) regression and XPU final (64 samples) completed and returned valid native previews. XPU preview uses 16 samples. These presets do not promise equal picture quality.
- A further 960x540 / 64-sample XPU frame completed and was visually inspected through its native preview. Recorded worker time was 7.24s: load 0.63s, USD export 1.13s, husk process 5.30s (startup-to-hook 1.46s within that process), composite 0.18s and inspection 0.30s. Overlapping portions must not be summed. This is one working-session observation, not a benchmark promise.
- 30 portable unit tests cover transport, snapshots/lifecycle, renderer-aware deduplication, frame-specific device evidence, warning semantics, preview bounds/hashes, and refusal to resume while the owned renderer remains active.

Production HIP and HDA hashes matched before/after. GUI remained on the original clean scene at frame 97. No asset/scene files, credentials, machine configuration or render evidence are published in this source repository.

## Scope and timing

This is a restricted adapter for `workai::indonesia_glow_map::2.0`, its validated emissive material and orthographic camera. The local asset is not distributed in this repository. Other objects/lights are excluded. Arbitrary Principled shaders, volume assets and the digital globe need separate adapters and acceptance scenes.

Timing records include scene load, USD export, husk startup to its first pre-frame hook, each pre/post-frame interval, process lifetime, composition, inspection and worker elapsed time. Frame intervals include scene updates and compilation. Composition may overlap rendering; timings cannot be summed as independent wall times. Mantra reports its combined render call instead of inventing separate startup/export times. No speedup claim is derived from these lifecycle tests; the earlier [three-frame comparison](KARMA-XPU-COMPARISON.md) has its own workload and limits.

Cancellation is cooperative at a frame boundary, not an immediate kill. On the tested 20.5 build, a pre-frame exception exits husk with code 1; the worker accepts this only with its explicit cancellation receipt and completion receipts for all started frames. Other errors still fail. The newer documented SkipFrame behavior was not assumed to hold on this installation. A hung current frame may still require manual investigation.

Development failures are retained locally: initial frame-list argument grouping, an unavailable COP resolution method, and the 20.5 cancellation exit behavior. The accepted build passes frames as separate arguments, reads dimensions from the written PNG header, and uses explicit cancellation receipts.

## Reproduction

Run `python -m pip install -e ".[test]"`, then `python -m unittest discover -s tests -v` for the portable suite. Real asset acceptance requires the local map HIP/HDA and the saved, clean GUI scene described above. Submit frames 97–101 via `render_frames(renderer="karma_xpu", quality="preview")`, cancel after the first published frame, wait for `cancelled`, resume and inspect hashes/previews. Test corruption only on disposable acceptance outputs. Set `parameters={"intensity": 0}` on a separate worker job for the black-frame check.

The complete local SDK harness, per-job immutable requests, logs, manifests and image content are retained under the workspace evidence directory. The source-only repository intentionally omits those private paths and assets.
