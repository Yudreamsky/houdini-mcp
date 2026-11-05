# Karma 试渲与调参

`domain_recipe(domain="render")` 展开 `karma`，按 `action="run"`、`name="karma"` 调用。它只读已保存的 HIP，在后台 hython 里临时设置 Karma，工程文件不会被保存，返回值里的 `hip_unchanged` 可核对。窗口里用 `graph_edit` 搭的场景，先 `window_session(action="save",session_id=id)` 存盘再渲染。当前只渲染 /obj 场景的单帧；Solaris（/stage）里的渲染设置还不读取。

先 `inspect` 看相机、灯、ROP 和材质。多台相机时，之后每次都传 `camera`。没有灯时 Karma 会自动加一盏头灯，先告诉用户这时的亮度和阴影不代表最终效果。

Karma 读不了的材质，渲染前会临时转成 MaterialX，只在后台的内存里改，工程文件不变。`inspect` 的 `material_conversion` 分别列出 XPU 和 CPU 会转换哪些、哪些无法转换；每次 `render` 的 `materials` 记录实际转换了什么，以及哪些地方是近似。

- 旧式 /shop 材质：Karma 的 CPU 和 XPU 都不读。`v_constant` 转成按几何颜色直接发光的无光照材质，雨滴示例因此和 Mantra 原图一致。`v_plastic`、`v_metal`、`v_glass`、`v_decal`、`v_supermat` 和 /shop 里的 Principled 转成 standard_surface。
- /mat 里的 Principled，CPU 原样读取，不转换。XPU 有自带的近似处理，实测以下效果都正常，所以默认不转：颜色、粗糙度、金属度、法线、发光和不透明度贴图，以及玻璃、清漆、光泽和点颜色。
- XPU 的近似会丢掉凹凸贴图和透明度贴图。用到这两种时，整个材质转成 MaterialX：所有贴图通道一起转换，贴图值与参数相乘，和 CPU 渲染一致。
- XPU 的近似还会忽略次表面散射。转换后的效果比原样离 CPU 更远，所以这种情况只提示改用 `engine="cpu"`。
- 转换结果里会写明哪些没有对应，例如各向异性、色散，或清漆层单独的凹凸。
- 其他 VEX 材质和 `v_matte` 这类遮罩材质无法转换：XPU 下要用 `engine="cpu"`，或在工程里改成 MaterialX。
- 想看原样效果时传 `changes={"convert_materials": false}`；也可以把原样和转换后放进同一次 `compare` 对照。
- 几何颜色 `Cd` 在 Karma 里叫 `displayColor`。打包几何（packed）内部的材质路径不会被改写。
- XPU 第一次遇到新的材质组合时要编译着色器，可能卡几十秒到几分钟，之后同类材质每张只要几秒。

`presets` 列出四套预设和全部可调项。`preview` 长边最多 960，32 采样，显卡降噪，30 秒封顶，适合看构图和光的方向。`standard` 长边最多 1920，128 采样，2 分钟封顶，用来看明暗层次、反射和阴影。`final` 用相机原分辨率、512 采样、不降噪，单帧最长 8 分钟。`scene` 沿用 `rop` 指定的 Karma 节点自己的采样和降噪。`changes` 只接受列出的控制项，例如 `{"samples":128,"denoiser":"off"}`。

- 先把用户的意见落到一个量上。说“太噪”，就看采样数和降噪；有零星飞白，就降低 `color_limit`；玻璃或水发黑，就提高 `refraction_limit` 和 `reflection_limit`。说“太暗”，先查灯和材质的提示，不要只靠加采样。
- 用 `compare` 并排 2–4 个方案，相机和帧保持一致。判断噪点和细节时，传 `zoom=[左,上,右,下]` 放大同一块区域，取值为 0–1 的比例；不要凭缩小的整图下结论。降噪会抹掉细小的反光和纹理，看细节时加一组不降噪的对照。
- `status="time_limit"` 表示渲染到达时间上限，保存的是当时的画面，会更噪。`progress_percent` 是停下时完成的比例；需要更干净时加时间或降分辨率。`gpu_verified` 读的是渲染日志里 OptiX 的实际贡献；XPU 默认只用显卡。显卡降噪第一次使用要准备约 2 分钟，之后每张只需几秒。
- XPU 渲染前会看一眼显卡：其他程序（例如本地 AI 模型）把使用率占到 70% 以上，或显存剩不到 4 GB 时，`notes` 会提醒，`gpu_load` 记录当时的读数。这时到时间上限多半是显卡被占，可以稍后再试或改用 `engine="cpu"`。
- `preset="scene"` 沿用工程 Karma 节点自己的设置。工程里只有一个 Karma 节点时不用传 `rop`；有多个时要指定；一个都没有时会提示改用其他预设。
- 渲染使用的处理器线程数是本机逻辑核心数减 4，记录在 `render_threads`；可用环境变量 `HOUDINI_RESEARCH_RENDER_THREADS` 指定。后台进程超时时，它启动的渲染进程会一起结束，报错仍然说明是超时。
- `render` 传 `topic` 时保存为经验卡，`compare` 总会保存对照卡。用 `knowledge(topic="渲染")` 找回，用 `evidence(key)` 或 `evidence(key, variant=方案名)` 取原图。
- 用户选定一个方案后，用 `save_preset(name=..., preset=底板预设, changes=..., note=选择理由)` 保存，以后传 `preset=该名字` 即可。只在用户明确选择后保存。
