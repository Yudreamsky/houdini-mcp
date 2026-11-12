# Karma 试渲与调参

`domain_recipe(domain="render")` 展开 `karma`，按 `action="run"`、`name="karma"` 调用。它只读已保存的 HIP，在后台 hython 里临时设置 Karma，工程文件不会被保存，返回值里的 `hip_unchanged` 可核对。窗口里用 `graph_edit` 搭的场景，先 `window_session(action="save",session_id=id)` 存盘再渲染。`render` 和 `compare` 渲单帧，`animate` 渲一段帧（见下文“动画”）；只渲染 /obj 场景，Solaris（/stage）里的渲染设置还不读取。本机装了 Chaos Vantage 时，`changes={"engine": "vantage"}` 改用 Vantage 渲染，见下文“Vantage”。照片级效果（圆角、阴影边、PBR 材质）见 [照片级真实感](photoreal.md)。

先 `inspect` 看相机、灯、ROP 和材质。多台相机时，之后每次都传 `camera`。没有灯时 Karma 会自动加一盏头灯，先告诉用户这时的亮度和阴影不代表最终效果。

Karma 读不了的材质，渲染前会临时转成 MaterialX，只在后台的内存里改，工程文件不变。`inspect` 的 `material_conversion` 分别列出 XPU 和 CPU 会转换哪些、哪些无法转换；每次 `render` 的 `materials` 记录实际转换了什么，以及哪些地方是近似。

- 旧式 /shop 材质：Karma 的 CPU 和 XPU 都不读。`v_constant` 转成按几何颜色直接发光的无光照材质，雨滴示例因此和 Mantra 原图一致。`v_plastic`、`v_metal`、`v_glass`、`v_decal`、`v_supermat` 和 /shop 里的 Principled 转成 standard_surface。
- /mat 里的 Principled，CPU 原样读取，不转换。XPU 有自带的近似处理，实测以下效果都正常，所以默认不转：颜色、粗糙度、金属度、法线和发光贴图，以及玻璃、清漆、光泽和点颜色。
- XPU 的近似会丢掉凹凸贴图和透明度贴图。用到这两种时，整个材质转成 MaterialX：所有贴图通道一起转换，贴图值与参数相乘，和 CPU 渲染一致。
- 镂空也要转换，树叶、草叶这类卡片最常遇到。XPU 的近似把不透明度贴图挖掉的部分当成一层透明的面，不是洞：
  - 只有一层、后面有物体时，看不出差别；
  - 画面的透明通道在洞里仍是不透明，相机本来看不到的天空会从洞里露出来；
  - 叠在一起的镂空面会整片发黑，实测 12 层叶片卡片后面的墙完全看不到；Alpha Mode 选 blend 或 mask 都一样；
  - 底色贴图自带的透明通道（Use Texture Alpha）完全不起作用。

  所以用了不透明度贴图或底色贴图透明通道的 Principled，在 XPU 下整个材质转成 MaterialX，镂空结果和 CPU 一致。
- XPU 的近似还会忽略次表面散射。转换后的效果比原样离 CPU 更远，所以这种情况只提示改用 `engine="cpu"`。
- 转换结果里会写明哪些没有对应，例如各向异性、色散，或清漆层单独的凹凸。
- 其他 VEX 材质和 `v_matte` 这类遮罩材质无法转换：XPU 下要用 `engine="cpu"`，或在工程里改成 MaterialX。
- 想看原样效果时传 `changes={"convert_materials": false}`；也可以把原样和转换后放进同一次 `compare` 对照。
- 几何颜色 `Cd` 在 Karma 里叫 `displayColor`。打包几何（packed）内部的材质路径不会被改写。
- XPU 第一次遇到新的材质组合时要编译着色器，可能卡几十秒到几分钟，之后同类材质每张只要几秒。

`presets` 列出四套预设、灯光预设和全部可调项。`preview` 长边最多 960，32 采样，显卡降噪，30 秒封顶，适合看构图和光的方向。`standard` 长边最多 1920，128 采样，2 分钟封顶，用来看明暗层次、反射和阴影。`final` 用相机原分辨率、512 采样、不降噪，单帧最长 8 分钟。`scene` 沿用 `rop` 指定的 Karma 节点自己的采样和降噪。`changes` 只接受列出的控制项，例如 `{"samples":128,"denoiser":"off"}`。

- 先把用户的意见落到一个量上。说“太噪”，就看采样数和降噪；有零星飞白，就降低 `color_limit`；玻璃或水发黑，就提高 `refraction_limit` 和 `reflection_limit`。说“太暗”，先查灯和材质的提示，不要只靠加采样。
- 用 `compare` 并排 2–4 个方案，相机和帧保持一致。判断噪点和细节时，传 `zoom=[左,上,右,下]` 放大同一块区域，取值为 0–1 的比例；不要凭缩小的整图下结论。降噪会抹掉细小的反光和纹理，看细节时加一组不降噪的对照。
- `status="time_limit"` 表示渲染到达时间上限，保存的是当时的画面，会更噪。`progress_percent` 是停下时完成的比例；需要更干净时加时间或降分辨率。`gpu_verified` 读的是渲染日志里 OptiX 的实际贡献；XPU 默认只用显卡。显卡降噪第一次使用要准备约 2 分钟，之后每张只需几秒。
- XPU 渲染前会看一眼显卡：其他程序（例如本地 AI 模型）把使用率占到 70% 以上，或显存剩不到 4 GB 时，`notes` 会提醒，`gpu_load` 记录当时的读数。这时到时间上限多半是显卡被占，可以稍后再试或改用 `engine="cpu"`。
- `preset="scene"` 沿用工程 Karma 节点自己的设置。工程里只有一个 Karma 节点时不用传 `rop`；有多个时要指定；一个都没有时会提示改用其他预设。
- 渲染使用的处理器线程数是本机逻辑核心数减 4，记录在 `render_threads`；可用环境变量 `HOUDINI_RESEARCH_RENDER_THREADS` 指定。后台进程超时时，它启动的渲染进程会一起结束，报错仍然说明是超时。
- 渲染期间这个 MCP 的其他工具照常可用，例如查经验库、读窗口里的网络、用 `fx_watch` 看进度。同一时间只渲染一个任务，后来的渲染请求排队等前一个结束。
- 取消这次调用，或者客户端断开连接，后台的 hython 和它启动的 husk（或 Vantage）会在几秒内结束，显卡随即空出来。已经渲完的动画帧留在动画文件夹里。
- `render` 传 `topic` 时保存为经验卡，`compare` 总会保存对照卡。用 `knowledge(topic="渲染")` 找回，用 `evidence(key)` 或 `evidence(key, variant=方案名)` 取原图。
- 用户选定一个方案后，用 `save_preset(name=..., preset=底板预设, changes=..., note=选择理由)` 保存，以后传 `preset=该名字` 即可。只在用户明确选择后保存。

## 临时改场景（只对这次渲染）

`overrides` 和 `hide` 在后台的副本上改场景，工程文件不变。`render`、`compare`、`animate` 都能用，Karma 和 Vantage 都支持。

- `overrides={"/obj/节点/参数": 数值}` 临时改参数，例如风力 `{"/obj/WIND/STATE/strength": 1}`。键是参数的完整路径，值是数字、true/false 或文字。
- 参数原来有关键帧或表达式时，这次渲染按固定值，原来的动画不再起作用。结果的 `scene.overrides` 写明每个参数从什么改成什么，`was_animated` 标出原来有动画的。
- `hide=["/obj/BACKDROP"]` 把物体从这次渲染里拿掉。只能填 /obj 里的物体。
- `compare` 里每个方案可以带自己的 `overrides` 和 `hide`，例如 `{"无风": {"overrides": {路径: 0}}, "有风": {"overrides": {路径: 1}}}`。顶层的 `overrides`、`hide` 对所有方案生效；同一个参数两边都写时，以方案自己的为准。
- 能执行代码的参数（Python、脚本、回调一类）和 `graph_edit` 一样受限：主机没有设 `HOUDINI_RESEARCH_ALLOW_CODE=1` 时拒绝。锁定或禁用的参数也拒绝。
- 路径不存在、数值类型不对时直接报错，不会悄悄忽略。
- 传了 `topic` 时，记录里保存这些改动（`scene`），以后能照原样重渲。

## 灯光预设

`changes={"lighting": ...}` 在后台临时换灯，工程文件不变。`scene`（默认）用工程自己的灯。其余四套按灯光师和摄影师的做法定，数值在校准场景上实测过；规则、来源和按意见改灯的对照表见 [布光经验](lighting.md)。

- `day` 日景：暖白色太阳从右前方（30°，高 35°）照来，天空按 CIE 标准晴天。太阳越低越暖、影子越长；`light_elevation` 小于 10 左右就是黄昏。
- `overcast` 阴天：天空按 CIE 阴天，头顶约是地平线的 3 倍。云后太阳那一侧略亮，两侧墙面有明暗差，几乎没有影子。太阳方向也用 `light_angle` 和 `light_elevation` 设。
- `night` 夜景：淡蓝色月光从左后方（-135°）勾出轮廓，夜空比建筑轮廓亮一点。默认保留工程里的点光、聚光、面光等局部灯。
- `studio` 产品摄影棚：两个大柔光箱，主光在 30°、高 45°，辅光在另一侧；后方阴影一侧一条灯条勾边。灰色背景在物体正后方最亮，四角暗约 2 档。
- `hdri` 全景照片：`changes={"lighting": "hdri", "hdri": "照片的完整路径"}`，支持 `.exr` 和 `.hdr`。光的颜色、天空和远景都来自真实照片，照片同时是背景。
  - 后台先在照片里找最亮的方向（多半是太阳），再把照片绕竖轴转动，让它落在 `light_angle` 指定的位置（默认 30，右前方；180 是逆光）。结果的 `lighting.sun` 是找到的高度和方位，`lighting.turn` 是转了多少度。
  - 太阳的高度和天光的强弱由照片决定，所以不接受 `light_elevation` 和 `light_fill`；整体亮度用 `light_exposure` 调。
  - 想要低角度的金色逆光，要换一张太阳低的照片，调参数做不到。
  - Vantage 下照片照常照明；背景是按相机方向贴上去的一份缩小的照片（宽 1024），比 Karma 的背景模糊，像虚化的远景。
  - 实测一张 4K 的户外照片：找到的太阳高度 20.4°、方位 144.1°，和逐像素量出来的 21.0°、143.7° 一致。

方向以相机为准，换相机也不用重算。`light_angle` 是太阳、月亮或主光的水平方向：0 从相机背后照向物体，90 从画面右侧，-90 从左侧，180 是逆光。`light_elevation` 是高度角。摄影棚三盏灯随主光一起转；灯的大小和距离按画面里全部几何体的范围定，场景大小不影响亮度。

- `light_exposure` 整体加减预设灯的亮度（档），不影响保留下来的工程灯。
- `light_fill` 只调补光：日景、夜景调天光，摄影棚调辅光。-1 影子更暗、反差更大，+1 更柔。阴天全是天光，不接受这一项。
- 天空同时是背景。地平线以下按远处的雾气渐变到地面色，相机朝下时背景是地面色，不会出现一堵墙。
- 工程里的天空灯和太阳类灯（envlight、distant、sun）总会被关掉。其他局部灯在夜景默认保留，其余预设默认关掉，可用 `keep_scene_lights` 改。结果里的 `lighting` 列出加了、关了和保留了哪些灯，`notes` 用一句话说明。
- 工程自己的 Karma 节点限定了候选灯，或单独显示（solo）某盏灯时，预设的灯也会加进去。
- 亮度实测值（白色哑光面，CPU 和 XPU 一致）：

  | 预设 | 实测亮度 |
  |---|---|
  | 日景 | 朝太阳的墙约 0.85，水平地面约 0.55，阴影约 0.13 |
  | 阴天 | 水平面约 0.9，墙约 0.5 |
  | 夜景 | 朝月亮的面约 0.14，阴影约 0.03 |
  | 摄影棚 | 白盒子顶面约 1.0，正面约 0.67 |

  没有色调映射，超过 1 会截断成白色，画面里的天空也比照片显得灰。
- 用户说太平、太暗、看不出形状时，按 [布光经验](lighting.md) 的对照表改。一次只改一个量，用 `compare` 并排看。
- 选定的灯光可以和画质一起存成预设，例如 `save_preset(name="夜景出图", preset="standard", changes={"lighting": "night", "light_exposure": 1})`。

## Vantage

`changes={"engine": "vantage"}` 用本机的 Chaos Vantage 渲染：后台把场景导出成 USD，再交给 `vantage_console`。本机实测（RTX 4090）：

- 单帧渲染 0.1–1 秒，另加启动 9–25 秒（第一次启动要编译着色器，最慢），导出几秒；
- 121 帧序列在 1264×744、256 采样下约 2 分钟，同样设置的 Karma XPU 约 7 秒一帧。

所以 Vantage 主要快在序列帧和多次出图；单张时启动时间占大头。

- 预设用 `preview`、`standard`、`final`，采样、分辨率和降噪（`denoiser` 为 `off` 时关）照常生效。`preset="scene"` 和只对 Karma 有效的项（`time_limit`、各类反弹次数、`color_limit`、`light_sampling_quality`、`depth_of_field`、`convert_materials`）会被拒绝。
- 结果和 Karma 的格式一样：
  - `seconds` 是导出加 Vantage 整个进程的时间；
  - `render_seconds`、`startup_seconds`、`export_seconds` 分开记录；
  - `gpu` 是日志里的显卡；
  - `vantage_tries` 是启动次数。Vantage 3.3 约每 8 次启动崩溃 1 次，会自动重启，最多 3 次。
- `compare` 可以把 Karma 和 Vantage 放在一起对照，例如 `{"Karma": {"engine": "xpu"}, "Vantage": {"engine": "vantage"}}`。
- 导出时自动处理 Vantage 和 Karma 的差别，每一项都会写进 `notes`：
  - 所有能转换的材质临时转成 MaterialX，因为 Vantage 只读 MaterialX。
  - 材质里用到的几何颜色（`displayColor`）写成常数，因为 Vantage 在 MaterialX 里读不了几何属性。各处颜色不同的会提示偏浅。
  - 由节点算出、又不含贴图的颜色和数值（例如几何颜色 × 底色）折算成常数。Vantage 算反弹光时会把这种节点当成白色，实测让蓝色箱子脚下出现一圈白光；贴图和直接写的数值没有这个问题。
  - 没有材质、也没有几何颜色的物体，给和 Karma 默认一样的灰（反射率 0.41）。Vantage 自己的默认灰约亮五分之一。
  - 没有法线的物体加平滑法线（折角 60°）。Vantage 不会自动平滑，曲面会变成一块块平面。
  - 灯按类型调暗，和 Karma 一样亮。同样的 USD 灯在 Vantage 里更亮，实测倍数如下表；按表修正后，有材质的测试卡片两边相差 1.5% 以内。

    | 灯的类型 | 平行光、点光、聚光、球光 | 管状光 | 矩形、圆盘面光 | 环境光（天空） |
    |---|---|---|---|---|
    | Vantage 比 Karma 亮 | 约 1.1 倍 | 约 1.3 倍 | 约 1.44 倍 | 约 1.43 倍 |

  - 天空合成到背景：USD 的环境光在 Vantage 里只照明、不显示，所以 Vantage 输出带透明通道的图，再把灯光预设的天空按相机方向贴到后面。Vantage 的透明边是“预乘过透明度”的颜色，合成时按线性光相加，轮廓和地平线不会出现细黑边。
  - `round_edges` 在导出时真实倒角（见 [照片级真实感](photoreal.md)）。
- 限制：
  - 正交相机的单帧可以渲（用命令行的正交宽度）；正交相机的动画会被拒绝，因为 Vantage 在序列里读错正交宽度。
  - 工程自己的环境光贴图只照明、不显示，背景是透明的；要看到天空就用灯光预设。
  - 转不了 MaterialX 的 VEX 材质，在 Vantage 里按默认材质渲染。
  - Karma 的圆角着色、灯的阴影开关等 Karma 专有设置，Vantage 都不认。
- 本机没有 Vantage 时会提示改用 `engine` 的 `xpu` 或 `cpu`。Vantage 装在别处时，用环境变量 `HOUDINI_RESEARCH_VANTAGE` 指向 `vantage_console.exe`。

## 动画

`action="animate"` 加 `frames=[起始帧, 结束帧]` 和 `fps`（默认 24），把一段帧渲成按序号命名的 PNG。本机有 `ffmpeg` 时再合成 MP4。结果的 `folder` 是这段动画的文件夹（`frames` 子文件夹放逐帧图，`clip.mp4` 是视频），返回的图片是首、中、尾三帧并排。传 `topic` 时保存为经验卡。

- Vantage：整段只导出一次、启动一次，最多 480 帧。导出只写所需的帧，塔吊 31 帧导出约 12 秒，整段约 35 秒。`summary` 里有“每帧渲染约几秒”。
- Karma：最多 240 帧，每 48 帧一段。每段只打开一次工程、启动一次渲染进程，场景转换和着色器编译不再每帧重做。本机实测（RTX 4090，640×360、32 采样的小场景）：12 帧共约 7 秒；改动前逐帧渲染，每帧约 3.5 秒、共约 42 秒。约 600 万点的草地场景：12 帧共约 22 秒，改动前约 83 秒。
- 单帧时间上限照常按帧生效。到上限的帧记在 `limited_frames`，其余帧不受影响。
- 某一段中途停了（显卡出错、渲染进程崩溃）时，已渲完的帧保留，等 30 秒后从缺的那一帧接着渲，`resumed_at` 记下接续的帧。连续两次都渲不出新的一帧才报错，报错里写明已渲完的帧在哪个文件夹。
- 每段的渲染日志在动画文件夹里，名字是 `husk-F起始帧.log`。
- 灯光预设按第一帧的相机方向摆放，整段不变；相机运动时太阳不会跟着转。
- 几何很重、又由程序化网络生成的场景（例如 Labs 树工具），先烘焙成 bgeo 再渲染。实测一棵 450 万点的树：直接渲染时后台要重新计算整个网络，约 12 分钟、29 GB 内存；烘焙后 16 秒。
- 导出动画时，USD 导出节点每帧落盘（Flush Data After Each Frame）。不落盘时，Houdini 有时会漏写物体变换，动画在最后几帧冻住：同一个关键帧小球，6 次导出有 4 次出错，打开落盘后 0 次。
- 动画里所有帧用同一台相机，相机自己的动画照常生效。
