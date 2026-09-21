# Karma XPU map comparison — 2026-09-21

Karma XPU successfully rendered the existing emissive map on an RTX 4090 using OptiX only, with 100% device contribution reported. This validates a standalone USD/MaterialX workflow; it does not add Karma support to the MCP render tools yet.

Houdini 20.5.487, NVIDIA driver 610.88, 24 GB VRAM, 32 logical CPU processors. Same map geometry, primitive colors, camera, frames 97–99 and 960×540 output, followed by the same COP2 bloom. USD topology, point positions, colors and camera transform were independently checked against the original HIP. Original HIP/HDA hashes remained unchanged.

| Configuration | Three-frame process wall time | Following frame time |
|---|---:|---:|
| Mantra 4×4, 32 threads | 20.79 s | 5.89–6.07 s |
| Mantra 4×4, 8 threads | 21.68 s | 6.10–6.67 s |
| XPU MaterialX Unlit, 16 samples | 12.83 s | 1.92–2.00 s |
| XPU MaterialX Unlit, 64 samples | 20.99 s | 4.95–5.28 s |

The XPU 16 result is faster but visibly noisier on thin lines and tiny dots. The XPU 64 result is closer to Mantra, with similar three-frame wall time and slightly shorter following frames. Do not claim a several-fold gain at matched quality from this sample.

Process wall time includes renderer launch and scene loading, and Mantra's per-frame IFD generation/launch. It excludes shared post-compositing (~0.3 s/frame). XPU has an additional one-time three-frame USD export (~3.61 s), also excluded. The XPU following-frame values are differences of cumulative husk log times; Mantra values time the render call. These are workflow measurements, not isolated kernel benchmarks.

Other GPU applications remained active (roughly 30–40% total GPU activity was also observed during CPU renders, with about 22 GB occupied VRAM). Driver/shader caches were not cleared. This was a three-frame test in the user's working environment, not an exclusive GPU benchmark, a true cold-start test, or full-animation flicker acceptance. Sampling counts are not equivalent algorithms across renderers.

## Compatibility findings

- Preserve geometry and uniform `Cd` in USD. Use `ND_surface_unlit` with `ND_geompropvalue_color3` for this purely emissive asset.
- For Houdini 20.5, the Beauty RenderVar works with a String `driver:parameters:aov:name = "C"`, `sourceType = "lpe"`, and `sourceName = "C.*[LO]"`, matching the native Karma render-settings node's output. An initial raw-C configuration produced black output and was excluded from performance/quality acceptance.
- Explicit `KARMA_XPU_DISABLE_EMBREE_DEVICE=1` and renderer logs establish actual GPU rendering rather than GPU detection alone.
- Use a Sublayer LOP for the standalone USD stage. The comparison HIP was saved, reopened, and its map/settings prims verified.
- Keep bloom in a shared compositing stage so renderer differences are not hidden by separate artistic tuning.

The XPU 64 and Mantra outputs are not pixel-identical. Mean linear blue-channel differences were 0.36–0.67%; visible-region RGB mean absolute differences were about 4.05–4.14 on an 8-bit scale, versus 6.26–6.35 for XPU 16. These describe differences, not equivalent-quality certification.

Full local scenes, side-by-side images, scripts, output hashes and logs remain in the excluded `assets/karma-comparison` directory; they are not part of this source-only repository.

## Next increment

Consider an explicit renderer choice with Solaris/MaterialX preflight, GPU-device evidence and quality presets, retaining the existing render job lifecycle. Keep Mantra available. Larger globe, volume or instancing scenes need their own measurements.

References: [SideFX Karma XPU](https://www.sidefx.com/docs/houdini/solaris/karma_xpu.html), [husk](https://www.sidefx.com/docs/houdini/ref/utils/husk.html). Installed 20.5 help and generated native node output were used to verify version-specific details.
