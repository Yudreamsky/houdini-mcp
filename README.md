# Houdini MCP

一个随实际资产制作逐步完善的本地 Houdini MCP。当前版本 **0.10.0 / 22 工具 / 4 个程序化配方**，针对 **Windows / Houdini 20.5.487 / Python 3.11**。

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
| `list_procedural_assets` | 查询配方、单位、数字类型/范围及结构化跨参数约束 |
| `preflight_asset_instance` | 只读检查组合参数和实例/通道保护，返回拟用值及具体错误，不生成几何 |
| `upsert_asset_instance` | 按稳定 ID 创建或更新直管、90°弯头或三管共用支吊架样段，参数不变时不重复创建 |
| `inspect_asset_instance` | 回读样段实际几何，检查尺寸、孔拓扑、选定连接与支架覆盖 |
| `preview_asset_views` | GUI 正/侧/顶/透视，按类型或精确构件名隔离聚焦，返回原生 PNG |

## 程序化资产与配套 Skill

0.5 首个配方 `pipe_support_sample` 包含空心直管、带实际螺栓孔的法兰、垫片、螺栓/垫圈/螺母、穿孔槽钢横担、夹箍、吊杆和简化锚板。它是可调视觉样段，尺寸不是照片实测值或工程规格。

先调用 `list_procedural_assets`，再调用 `upsert_asset_instance(instance_id="pipe-sample", parameters={"length":2.4,"diameter":0.32})`。返回实际 SOP 路径、HDA 库、参数、修改前值和几何检查结果；实例需另行保存。相同 ID 原地更新，参数相同不修改节点；动画通道、人工解锁的 HDA 内容和配方版本变化均拒绝静默覆盖。

参数单位为米，包括长度、外径、壁厚、支架节距、吊杆高度，以及螺栓数量和圆周分段。组合约束在写入前校验。法兰、螺栓圈和横担随管径变化，支架随长度增减，存续零件保留稳定 `name` / `part_type`。当前直接生成分组多边形，尚无通用管线布置器、packed instancing 或标准件规格库。

HDA 首次使用时由版本化 Python 源码生成到 `.runtime/asset-library`，类型名含配方指纹；完整算法嵌入 HDA PythonModule，交付库不依赖仓库源码。保存 HIP 时显式携带对应 HDA；实例参数和 HDA 默认值须分别记录。源码仓库包含生成算法和测试，生成后的 HIP/HDA/图片保留本地。

`inspect_asset_instance(path)` 核查实际局部几何与选定接口，不是通用碰撞或承载检查。`preview_asset_views(path, views=["front","right","top","perspective"])` 返回完整样段多视图；可按检查结果中的 `part_type` 过滤。预览恢复显示、选择、视角等现场设置，但临时显隐/过滤仍可能使 HIP 标为未保存；不能把该操作当作完全只读。视口图用于几何检查，实体材质已用 Mantra 实测；本样段尚不支持限定地图 XPU 适配器。

配套 [houdini-asset-workflow Skill](skills/houdini-asset-workflow/SKILL.md) 与代码同仓库：入口按需读取样段方法、渲染经验和经验维护规则。MCP 提供操作，HDA/脚本实现参数关系，Skill 保存经过验证的使用方法与适用边界。为客户端安装时应链接或复制整个 Skill 文件夹；项目级 `.agents/skills` 可指向此源目录。安装路径存在与当前会话发现 Skill 是两项独立检查。

### 0.6：水平90°弯头样段

使用 `upsert_asset_instance(instance_id="elbow-sample", recipe="pipe_elbow_sample", parameters={"inlet_length":2.4,"outlet_length":1.8,"bend_radius":0.6})`。0.7起，后续更新已有实例可省略recipe，自动读取其配方；新实例省略recipe仍默认直管。同ID显式选择不同配方会拒绝覆盖。两配方共用工具；0.6/0.7保留旧直管算法，0.8按用户反馈修正两配方的固定件并生成新HDA类型。

新配方包含两段带法兰/支架的直管和一只空心弯头，0.8默认155个构件（0.6/0.7为139）。入口沿+X，出口沿+Z，Y向上；inlet/outlet_length只计直段，bend_radius是中心线半径，另有bend_segments控制弯曲细分。直管的管径、壁厚、螺栓数量和支架参数继续有效。本样例要求中心线半径至少为外径1.5倍，属于配方约束，不表示管件标准。

检查器测量两接口的内外环匹配误差、端口中心、弯头外径/壁厚，并在各自局部坐标内复用两条直段的检查。1厘米弯头错位的负例可被识别。完整顶视、侧视、透视和独立HDA验证见 [0.6 验证](docs/V06-VALIDATION.md)；该配方仍是固定水平90°，没有任意多点路由、三通、通用碰撞或流体网格。

### 0.7：只读预检与配方识别

`list_procedural_assets` 在单参数范围之外返回 `constraints`：壁厚比例、吊杆高度、支架覆盖、截面分段倍数、弯曲半径比例，均带规则ID、相关参数、比较操作和系数。数值参数带 `integer` / `number` 类型。这些属于视觉配方约束，不是工程标准。

先调用 `preflight_asset_instance(instance_id="elbow-sample", parameters={"diameter":0.5,"bend_radius":0.9})`。已有实例按当前值合并，新实例按默认值合并；ready=true 返回解析后的recipe、before、拟用parameters、是否新建/改变。ready=false 返回结构化errors；组合错误包含code、fields、actual和limit，实例/通道保护包含code和message。必须检查ready，不能只看MCP调用是否成功。

预检不安装/编译HDA、不新建节点、不写参数、不主动cook。与upsert共用实例解析和校验路径；upsert仍重新校验并生成/检查几何。预检不是状态锁或几何验收，期间场景变化会影响写入结果。动画/锁定/禁用通道、人工解锁HDA内容、外来对象和配方版本变化继续受保护。

### 0.8：开口向下的U形管卡

根据用户对参考照片的纠正，两配方将闭合圆箍改为开口朝下的圆杆U形件：上部弧段扣住管子，两条直腿穿过横担孔位，垫圈和螺母在横担下方；管底落在横担顶面。默认直管77构件、弯头155构件。圆杆直径8mm、局部孔位排列和未建螺纹均为视觉样例，不是照片量测或产品标准。

检查器读取实际几何，核管底接触、U形开口、冠部接触、两腿孔隙及垫圈/螺母位置；倒置U形的负例会失败。新样段measurement包含 `support_style="u_bolt_v1"`、`pipe_web_contact_gaps` 和 `u_bolts`。保留旧HDA的只读检查，旧圆箍返回 `legacy_closed_ring` 与旧接触字段；旧版检查通过不表示符合本次照片纠正。版本保护拒绝直接更新旧实例，应创建新ID对照、另存。详见 [0.8验证](docs/V08-VALIDATION.md)。

### 0.9：三根平行管道共用横担

创建 `upsert_asset_instance(instance_id="rack-sample", recipe="pipe_rack_sample")`。三根管沿X，排列沿Z，Y向上；每处支撑只有一根共用横担、两根外侧吊杆和三个向下开口的U形管卡。默认长2.4m、两组支撑、191构件。原直管/弯头的生成源码和HDA类型指纹保持不变。

`diameter_1/2/3`、`wall_1/2/3`、`rise_1/2/3`分别控制各管；`spacing_12/23`为水平中心距，第二管Z=0。rise是管底相对横担顶面的抬高量，不是管中心高度；非零rise生成简化承托座，U腿延长到同一横担下方。length/support_pitch/hanger_height、螺栓数和分段共用。当前固定三根，不支持任意管数或多层路由。

横担随外侧管位置及管径延伸。间距须至少为相邻两管外径之和×0.775+0.04m，保守预留法兰外包络；吊杆高度须容纳每根管的直径+rise+0.2m。这些是样段约束，不是规范。catalog中涉及多个参数的右侧值用 `terms={参数:系数}` 加offset表示；已有单字段right/scale规则保持兼容。

检查实际管/法兰包络净距、各管承托、共用横担覆盖、吊杆/管卡穿孔及下方紧固件。穿孔检查读取实际顶面多边形，要求杆中心位于孔内且杆半径小于到孔边的距离。通用碰撞、承载与厂家节点细节仍不在范围内。详见 [0.9验证](docs/V09-VALIDATION.md)。

### 0.10：照片参考变体与构件聚焦

新配方 `pipe_rack_reference` 保留原三管配方，另建照片导向的局部样段：默认三管底部共面，黑管同径，槽钢增加回折边及小切角；银色法兰之间改为较厚蓝色连接本体。joint_offset_1/2/3分别移动各管接头，管段外端不动；接头压到支撑站会被预检拒绝。这个非线性站位检查由配方校验器执行，catalog.validation_notes明确说明，未冒充已声明为线性constraints。

新建时明确 `recipe="pipe_rack_reference"`；旧三配方的算法及HDA类型保持不变。照片变体当前每管仍只有一处法兰模板，红管橙色连接、重复接头、竖向型钢框架和吊顶风管未重建；型号、背面截面及尺寸尚无依据。它不是完整照片复刻。

`preview_asset_views(path, views=["perspective"], part_names=["pipe2_flange_left","pipe2_gasket","pipe2_flange_right"])` 可只看选定节点。part_names允许1–128个唯一已存在名称，从inspect_asset_instance.parts读取；与part_types同时指定时取交集，无匹配则报错。自动按所选几何取景，图片元数据返回所选名称和局部包围盒。临时节点/显隐会恢复，但HIP仍可能标dirty。详见 [0.10验证](docs/V010-VALIDATION.md)。

### 可复用GUI验收脚本

在本仓库根目录，以安装了MCP依赖的外部Python运行：

```powershell
python scripts/accept_asset.py --recipe pipe_elbow_sample --expected-hip 'C:/project/current-saved.hip' --output 'C:/project/new-acceptance-01' --hython 'C:/Program Files/Side Effects Software/Houdini 20.5.487/bin/hython.exe' --render
```

将路径替换为现场值。脚本核对当前GUI正是expected-hip且无未保存修改，临时切换场景创建独立样段；运行期间不要同时编辑该Houdini会话。输出目录必须不存在，不覆盖旧结果。`--recipe`支持四个已实现配方；可用 `--parameters` 和 `--update` 指定JSON参数文件，否则采用默认值和已验加长/加粗样例。

流程覆盖约束查询、只读预检、创建、自动识别/幂等、无效参数/配方拒绝、尺寸修改、多视图、复位、HIP/HDA打包、重开、独立hython重建。`--render`额外配置通用相机/灯光并渲染一帧Mantra；不指定时不运行渲染。最后恢复原HIP和帧，核保存状态与源HIP文件指纹。不会保证恢复所有面板布局。

交付 `report.json`、`instance.json`、`sample.hip`、HDA、多视图、`standalone.json`；请求渲染时另有render-demo.hip和原生PNG。技术通过与实际看图分开，`visual_review`保留pending，操作者另记视觉结论。失败日志保留；默认渲染超时300秒时只请求取消，不声称已停止，应查询job_id确认后再重跑。没有自动发布或配置修改。

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
& 'C:/path/to/Houdini/bin/hython.exe' tests/elbow_acceptance.py evidence/elbow-check-01
& 'C:/path/to/Houdini/bin/hython.exe' tests/preflight_acceptance.py evidence/preflight-check-01
& 'C:/path/to/Houdini/bin/hython.exe' tests/u_bolt_acceptance.py evidence/u-bolt-check-01
& 'C:/path/to/Houdini/bin/hython.exe' tests/rack_acceptance.py evidence/rack-check-01
& 'C:/path/to/Houdini/bin/hython.exe' tests/reference_acceptance.py evidence/reference-check-01
```

`unittest` 运行传输、队列、任务状态和纯几何单元测试，不需要 Houdini。`tests/acceptance.py` 使用 `HOUDINI_HYTHON`（或默认安装位置）执行真实 headless MCP 验收，会创建独立样例文件。GUI 基础验收见 `tests/gui_acceptance.py --help`。`tests/procedural_acceptance.py` 通过真实 HOM 检查新样段的创建、更新、保护、打包和重开，独立于 MCP 传输/GUI 验收。

0.5.0 通过 **34 项单元测试**、真实 GUI MCP 样段创建/幂等更新/尺寸联动/多视图/保存重开，以及无仓库源码路径的独立 HDA 加载。样段 Mantra 960×540 实际渲染通过。详见 [0.5 验证与限制](docs/V05-VALIDATION.md)。

0.6.0 通过 **37项单元测试**，真实GUI MCP弯头样段完整调用、尺寸联动、参数/配方保护、保存重开，独立HDA加载及1280×720 Mantra渲染。新增headless HOM检查故意平移弯头的负例；既有直管在新工具下幂等更新且几何指纹不变。项目Skill本轮已进入Codex可用列表并实际读取；原生Houdini MCP工具发现仍是独立待验项。

0.7.0通过 **40项单元测试**、真实HOM只读/保护检查，以及同一份可复用GUI MCP脚本对两配方的完整执行（均含独立HDA和960×540 Mantra）。无效更新的预期失败路径也验证了原场景恢复和文件不变。详见 [0.7验证](docs/V07-VALIDATION.md)。

0.8.0通过 **41项单元测试**、真实HOM倒置U形负例及旧HDA检查/版本保护；两配方再次通过同一GUI MCP验收脚本、保存重开、独立HDA和Mantra。另渲染局部近景并实际看图，旧资产文件指纹不变。详见 [0.8验证](docs/V08-VALIDATION.md)。

0.9.0通过 **45项单元测试**、真实HOM三管承托/偏移/错孔负例、旧直管与弯头检查及幂等更新；新三管配方完成真实GUI MCP尺寸联动、多视图、保存重开、独立HDA和Mantra，完整与局部图片实际看图。详见 [0.9验证](docs/V09-VALIDATION.md)。

0.10.0通过 **48项单元测试**、实际连接本体错位负例及旧三管指纹回归；照片变体通过GUI SDK、重开、独立HDA、Mantra。按名称聚焦的非法筛选拒绝、显示/选择恢复及几何不变通过，细长构件透视取景已实际看图。详见 [0.10验证](docs/V010-VALIDATION.md)。

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
