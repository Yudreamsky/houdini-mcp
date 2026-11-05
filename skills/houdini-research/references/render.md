# Karma 试渲与调参

`domain_recipe(domain="render")` 展开 `karma`，按 `action="run"`、`name="karma"` 调用。它只读已保存的 HIP，在后台 hython 里临时设置 Karma，工程文件不会被保存，返回值里的 `hip_unchanged` 可核对。当前只渲染 /obj 场景的单帧；Solaris（/stage）里的渲染设置还不读取。

先 `inspect` 看相机、灯、ROP 和材质。多台相机时，之后每次都传 `camera`。没有灯时 Karma 会自动加一盏头灯，先告诉用户这时的亮度和阴影不代表最终效果。旧式 /shop 材质 Karma 完全不读，CPU 和 XPU 都按默认材质渲染。/mat 里的 VEX 材质只有 CPU 支持；Principled Shader 在 XPU 下被简化近似。要准确材质效果就用 `engine="cpu"`，或改用 MaterialX。

`presets` 列出四套预设和全部可调项。`preview` 长边最多 960，32 采样，显卡降噪，30 秒封顶，适合看构图和光的方向。`standard` 长边最多 1920，128 采样，2 分钟封顶，用来看明暗层次、反射和阴影。`final` 用相机原分辨率、512 采样、不降噪，单帧最长 8 分钟。`scene` 沿用 `rop` 指定的 Karma 节点自己的采样和降噪。`changes` 只接受列出的控制项，例如 `{"samples":128,"denoiser":"off"}`。

- 先把用户的意见落到一个量上。说“太噪”，就看采样数和降噪；有零星飞白，就降低 `color_limit`；玻璃或水发黑，就提高 `refraction_limit` 和 `reflection_limit`。说“太暗”，先查灯和材质的提示，不要只靠加采样。
- 用 `compare` 并排 2–4 个方案，相机和帧保持一致。判断噪点和细节时，传 `zoom=[左,上,右,下]` 放大同一块区域，取值为 0–1 的比例；不要凭缩小的整图下结论。降噪会抹掉细小的反光和纹理，看细节时加一组不降噪的对照。
- `status="time_limit"` 表示渲染到达时间上限，保存的是当时的画面，会更噪。需要更干净时加时间或降分辨率。`gpu_verified` 读的是渲染日志里 OptiX 的实际贡献；XPU 默认只用显卡。显卡降噪第一次使用要准备约 2 分钟，之后每张只需几秒。
- `render` 传 `topic` 时保存为经验卡，`compare` 总会保存对照卡。用 `knowledge(topic="渲染")` 找回，用 `evidence(key)` 或 `evidence(key, variant=方案名)` 取原图。
- 用户选定一个方案后，用 `save_preset(name=..., preset=底板预设, changes=..., note=选择理由)` 保存，以后传 `preset=该名字` 即可。只在用户明确选择后保存。
