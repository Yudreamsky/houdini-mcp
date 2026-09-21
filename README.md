# Houdini MCP

一个随实际资产制作逐步完善的本地 Houdini MCP。当前版本 **0.5.0 / 21 工具**，针对 **Windows / Houdini 20.5.487 / Python 3.11**。

外部 Python 提供 MCP stdio 服务；Houdini 内部使用标准库、`hou` 及随 Houdini 提供的 NumPy / USD。命令通过本机认证 TCP 队列交给 Houdini 主线程执行，无需给 Houdini 安装 MCP SDK。

## 工具

| 工具 | 用途 |
|---|---|
| `ping` | Houdini / MCP 版本、PID、当前文件和 GUI 状态 |
| `get_scene_info` | 场景、子节点、选择、时间与保存状态 |
| `get_node_info` | 参数、连接、错误及可选 SOP 几何统计 |
| `execute_code` | 在主线程运行可信 Python；用 `result` 返回 JSON |
| `get_viewport_screenshot` | 当前视口 PNG，以原生 MCP 图片返回 |
| `save_scene` | 绝对路径另存，返回实际文件大小和 SHA256 |
| `open_scene` | 打开工程；默认拒绝丢弃未保存修改 |
| `set_asset_parameters` | 预验证后批量设置数字参数，拒绝动画通道 |
| `render_frames` | 从 HIP / HDA 快照提交 Mantra 或限定地图 Karma XPU + COP2 任务 |
| `get_render_status` | 查询进度、最近输出、完成或具体失败原因 |
| `get_render_preview` | 返回哈希验证后的原生 PNG 图片、画面告警、计时与 GPU 证据 |
| `get_capabilities` | 精确会话、保存状态、渲染节点与可选 NVIDIA 显卡/驱动探测 |
| `preflight_render` | 检查当前已保存工程、相机、依赖、节点和磁盘空间 |
| `cancel_render` | 请求完成当前帧后停止，须查询到 cancelled 才算停止 |
| `resume_render` | 创建子作业，复用哈希通过的帧，补渲缺失或损坏帧 |
| `get_asset_schema` | 数字参数类型、维度、范围、默认值、条件与动画状态 |
| `asset_preset` | 捕获、列举或应用数字参数预设，排除动画通道 |
| `list_procedural_assets` | 查询已实现的程序化配方、单位和参数范围 |
| `upsert_asset_instance` | 按稳定 ID 创建或更新管道连接/支吊架样段，参数不变时不重复创建 |
| `inspect_asset_instance` | 回读样段实际几何，检查尺寸、孔拓扑、选定连接与支架覆盖 |
| `preview_asset_views` | GUI 正/侧/顶/透视及零件类型隔离预览，返回原生 PNG |

## 程序化资产与配套 Skill

0.5 首个配方 `pipe_support_sample` 包含空心直管、带实际螺栓孔的法兰、垫片、螺栓/垫圈/螺母、穿孔槽钢横担、夹箍、吊杆和简化锚板。它是可调视觉样段，尺寸不是照片实测值或工程规格。

先调用 `list_procedural_assets`，再调用 `upsert_asset_instance(instance_id="pipe-sample", parameters={"length":2.4,"diameter":0.32})`。返回实际 SOP 路径、HDA 库、参数、修改前值和几何检查结果；实例需另行保存。相同 ID 原地更新，参数相同不修改节点；动画通道、人工解锁的 HDA 内容和配方版本变化均拒绝静默覆盖。

参数单位为米，包括长度、外径、壁厚、支架节距、吊杆高度，以及螺栓数量和圆周分段。组合约束在写入前校验。法兰、螺栓圈和横担随管径变化，支架随长度增减，存续零件保留稳定 `name` / `part_type`。当前直接生成分组多边形，尚无通用管线布置器、packed instancing 或标准件规格库。

HDA 首次使用时由版本化 Python 源码生成到 `.runtime/asset-library`，类型名含配方指纹；完整算法嵌入 HDA PythonModule，交付库不依赖仓库源码。保存 HIP 时显式携带对应 HDA；实例参数和 HDA 默认值须分别记录。源码仓库包含生成算法和测试，生成后的 HIP/HDA/图片保留本地。

`inspect_asset_instance(path)` 核查实际局部几何与选定接口，不是通用碰撞或承载检查。`preview_asset_views(path, views=["front","right","top","perspective"])` 返回完整样段多视图；可按检查结果中的 `part_type` 过滤。预览恢复显示、选择、视角等现场设置，但临时显隐/过滤仍可能使 HIP 标为未保存；不能把该操作当作完全只读。视口图用于几何检查，实体材质已用 Mantra 实测；本样段尚不支持限定地图 XPU 适配器。

配套 [houdini-asset-workflow Skill](skills/houdini-asset-workflow/SKILL.md) 与代码同仓库：入口按需读取样段方法、渲染经验和经验维护规则。MCP 提供操作，HDA/脚本实现参数关系，Skill 保存经过验证的使用方法与适用边界。为客户端安装时应链接或复制整个 Skill 文件夹；项目级 `.agents/skills` 可指向此源目录。安装路径存在与当前会话发现 Skill 是两项独立检查。

## 安装与启动

需要已安装、可正常授权运行的 Houdini。外部 Python 建议使用独立虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe launch_gui.py
```

默认寻找 Houdini 20.5.487。安装位置不同可显式指定：

```powershell
.\.venv\Scripts\python.exe launch_gui.py --houdini "C:/path/to/Houdini/bin/houdinifx.exe"
```

启动器为专用 Houdini 进程设置插件与首选项目录，不修改全局 Houdini packages。活动会话存在时拒绝重复启动；不会自动接管已有窗口。会话凭据写入被 Git 忽略的 `.runtime/gui-session.json`，不要分享该文件。

## MCP 客户端配置

按客户端配置格式添加 stdio 服务，使用真实的绝对路径。例如 TOML：

```toml
[mcp_servers.houdini]
command = 'C:/path/to/houdini-mcp/.venv/Scripts/python.exe'
args = ['C:/path/to/houdini-mcp/run_mcp.py']
startup_timeout_sec = 20
tool_timeout_sec = 150

[mcp_servers.houdini.env]
HOUDINI_MCP_SESSION_FILE = 'C:/path/to/houdini-mcp/.runtime/gui-session.json'
HOUDINI_HYTHON = 'C:/path/to/Houdini/bin/hython.exe'
```

GUI 启动器与客户端的 `HOUDINI_HYTHON` 应指向同一安装版本。启动 GUI 后，让客户端重新加载 MCP；先调用 `ping` 和 `get_scene_info` 核对目标。配置存在不代表当前客户端已经完成工具加载。

快速 smoke 操作：在独立空场景中通过 `execute_code` 创建 geometry/sphere，回读参数并截图，再 `save_scene` 到新文件，使用 `open_scene` 重开核对。复杂变更前先保存检查点。

## 后台渲染

支持 Mantra，以及指定自发光地图的 Karma XPU 适配器。二者都使用已有 `ifd` ROP 作为相机入口及 COP2 文件源/输出节点。向 `render_frames` 提供：

- 当前 GUI 已加载且已保存的 HIP 绝对路径、显式 `asset_libraries` HDA 路径。
- `rop_path`、`source_cop_node`、`composite_node`。
- 起止帧和分辨率；可选 `asset_path` 与数字 `parameters` 覆盖。
- `renderer="mantra"`（默认）或 `"karma_xpu"`，`quality="preview"`（默认）或 `"final"`。Mantra 对应 2×2 / 4×4，XPU 对应 16 / 64 采样；档位名称不保证同画质，也不等于美术验收。

每个任务复制 HIP 和给定 HDA，输出写入独立 `evidence/render-jobs/<job_id>`。预检拒绝未保存场景、缺失 HDA、错误 ROP/相机/COP 和已识别的缺失文件。其他纹理/缓存只记录指纹，尚不自动打包，渲染期间不要修改它们。Python/VEX 动态打开的路径无法自动发现。后台 worker 由长期运行的 Houdini 会话启动，不依赖短命 MCP 客户端。

提交返回 job_id，**不表示渲染完成**。查询状态直到 `completed` 或失败；`status.json` 保存逐帧哈希，工具响应只返回最近一帧以限制载荷。进程退出、存在部分图片、桥接超时都不会自动判定成功。

单任务限制 1–300 帧，预览最大 1920×1080，同时最多两个活跃任务。可提供 `request_id`：同一 ID、同一输入返回原任务；同一 ID 改变参数会报错。省略 ID 时按 HIP/HDA/参数指纹去重。要有意重新渲染，请使用新 ID；若外部依赖已改变，旧请求会拒绝复用，须新 ID 重新预检。

调用 `cancel_render(job_id)` 后继续查询状态。两种渲染器均在帧边界协作停止，不强杀当前帧；卡住时不能保证立即取消。对 `cancelled`、`failed` 或确认进程已退出的 `interrupted` 作业调用 `resume_render`，会保留原记录并创建新任务，校验 HIP/HDA/外部依赖及逐帧 PNG/EXR 哈希，只复用完整帧。对已有 `completed` 作业也可检查并补渲损坏帧。输入指纹改变会拒绝续渲，`launch_unknown` 或 worker 已退出但渲染子进程仍在运行的 `renderer_stopping` 不允许续渲，须先确认实际进程状态。

**XPU 适配范围严格限定为 `workai::indonesia_glow_map::2.0`**：正交相机、方形像素、指定自发光材质、带 primitive Cd 的多边形。其他场景对象和灯光不导出；不支持通用 Principled 转 MaterialX、体积或任意资产。该本地资产未包含在源码仓库中。适配器生成独立 USD 与 MaterialX Unlit，并复用 COP2 光晕。整个待渲帧列表共用一个 husk 进程；取消或 worker 退出后，帧钩子跳过剩余帧。

XPU 禁用 Embree CPU 设备；每帧必须在 husk 完成统计中找到 OptiX 实际贡献才计为完成。`get_capabilities.gpu_probe` 仅为硬件枚举，`gpu_evidence` 是逐帧执行证据。独立 [XPU 对照测试](docs/KARMA-XPU-COMPARISON.md) 的速度结论仍仅适用于该样片。

用 `get_render_preview(job_id, frame=97)` 获取已完成帧，省略 frame 取最新帧。图片以原生 MCP ImageContent 返回，限制为作业内记录、哈希正确、尺寸合规的 PNG；损坏帧拒绝返回，可通过续渲修复。画面检查分别统计线性 EXR 与光晕合成结果，全黑、纯色、全透明返回告警，**有意的黑帧可正常完成**；非有限像素视为失败。没有告警也不代表画面符合创作目标。

计时分别记录场景加载、USD 导出、husk 启动到首帧前钩子、逐帧钩子间耗时、合成、检查及 worker 总耗时。逐帧含场景更新/编译，不是纯 GPU 内核耗时。合成可以与下一帧渲染重叠，不能直接相加。Mantra 的 `render_call_seconds` 包含 IFD 导出、子进程启动及渲染，未冒充为可分离的纯渲染时间。

0.4 的 renderer/quality 参与请求指纹。同一个 request_id 改渲染器或质量会拒绝。0.3 原有作业按冻结参数续渲；0.4 新作业默认使用 preview 档位，可能与旧工程 ROP 自设采样不同。`gpu_probe.xpu_render_verified` 已移除，改用明确的 `verification_scope` 和逐帧证据。

## 资产参数预设

先用 `get_asset_schema(path)` 检查数字参数，使用 `asset_preset(action="capture", name="blue_map", path=...)` 捕获，`action="list"` 列举，`action="apply"` 恢复。预设保存在被 Git 忽略的 `.runtime/presets`，名称限字母、数字、下划线与短横线。

捕获跳过动画、锁定和禁用通道；应用要求相同节点类型及数字参数结构，先整批验证，返回修改前值。已有同名预设须显式 `overwrite=true`。预设不是 HIP 检查点，不含几何、字符串、关键帧或外部资源；重大编辑前仍应另存工程。`set_asset_parameters` 从 0.3 起直接返回参数及 `before`，不再套用 `execute_code.result` 外层。

## 验证

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -p "test_*.py" -v
python tests/acceptance.py
# 新进程执行程序化 HDA 验收，输出目录必须尚不存在：
& 'C:/path/to/Houdini/bin/hython.exe' tests/procedural_acceptance.py evidence/procedural-check-01
```

`unittest` 运行传输、队列、任务状态和纯几何单元测试，不需要 Houdini。`tests/acceptance.py` 使用 `HOUDINI_HYTHON`（或默认安装位置）执行真实 headless MCP 验收，会创建独立样例文件。GUI 基础验收见 `tests/gui_acceptance.py --help`。`tests/procedural_acceptance.py` 通过真实 HOM 检查新样段的创建、更新、保护、打包和重开，独立于 MCP 传输/GUI 验收。

0.5.0 通过 **34 项单元测试**、真实 GUI MCP 样段创建/幂等更新/尺寸联动/多视图/保存重开，以及无仓库源码路径的独立 HDA 加载。样段 Mantra 960×540 实际渲染通过。详见 [0.5 验证与限制](docs/V05-VALIDATION.md)。

0.4.0 通过 30 项单元检查，并经真实 MCP stdio 调用完成 XPU 五帧取消/续渲/单帧损坏修复、原生图片、黑帧告警、Mantra 回归及 XPU 两档采样；另验 960×540 / 64 采样预览。RTX4090 逐帧 OptiX 贡献为100%，原 HIP/HDA 指纹保持不变。详见 [0.4 验证](docs/V04-VALIDATION.md)。0.3 的预设/schema/表达式保护与0.2 的资产、视频验收记录继续保留。

机器专属配置、场景、凭据和大体积渲染证据不提交此仓库。其他 Houdini 版本、操作系统未验证；渲染器范围限上文 Mantra 与限定地图 XPU。Codex 当前对话的原生 MCP 工具加载仍是独立待验项，不能用外部 SDK 成功替代。

## 边界与迭代

- `execute_code` 是可信本机执行入口，不是安全沙箱；不要暴露给不可信远端。
- Python 异常可能留下部分修改；Undo 分组不等于事务。
- 已开始的同步执行超时不能强制终止 Houdini；必须检查实际状态后决定后续动作。
- `set_asset_parameters` 只支持数字参数，先检查整批输入；不会保存文件或覆盖表达式。
- 停止 MCP/关闭窗口前先检查后台渲染状态。
- 当前活跃 GUI 可能保留旧桥接模块，`ping` 分开显示已加载桥接版本与外部 MCP 版本；重启专用会话后统一加载磁盘版本。

后续按真实使用问题迭代，计划见 [ROADMAP.md](ROADMAP.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。每个增量保留可复现样例和必要验证，尚未实现的建议不计入能力。
