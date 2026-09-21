# Houdini MCP

一个随实际资产制作逐步完善的本地 Houdini MCP。当前版本 **0.3.0**，已在 **Windows / Houdini 20.5.487 / Python 3.11** 验证。

外部 Python 提供 MCP stdio 服务；Houdini 内部只运行标准库与 `hou`。命令通过本机认证 TCP 队列交给 Houdini 主线程执行，无需给 Houdini 安装 MCP SDK。

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
| `render_frames` | 从保存的 HIP / HDA 快照提交后台 Mantra + COP2 任务 |
| `get_render_status` | 查询进度、最近输出、完成或具体失败原因 |
| `get_capabilities` | 精确会话、保存状态、渲染节点与可选 NVIDIA 显卡/驱动探测 |
| `preflight_render` | 检查当前已保存工程、相机、依赖、节点和磁盘空间 |
| `cancel_render` | 请求完成当前帧后停止，须查询到 cancelled 才算停止 |
| `resume_render` | 创建子作业，复用哈希通过的帧，补渲缺失或损坏帧 |
| `get_asset_schema` | 数字参数类型、维度、范围、默认值、条件与动画状态 |
| `asset_preset` | 捕获、列举或应用数字参数预设，排除动画通道 |

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

当前限定为 Mantra `ifd` ROP + COP2 文件源和输出节点。向 `render_frames` 提供：

- 当前 GUI 已加载且已保存的 HIP 绝对路径、显式 `asset_libraries` HDA 路径。
- `rop_path`、`source_cop_node`、`composite_node`。
- 起止帧和分辨率；可选 `asset_path` 与数字 `parameters` 覆盖。

每个任务复制 HIP 和给定 HDA，输出写入独立 `evidence/render-jobs/<job_id>`。预检拒绝未保存场景、缺失 HDA、错误 ROP/相机/COP 和已识别的缺失文件。其他纹理/缓存只记录指纹，尚不自动打包，渲染期间不要修改它们。Python/VEX 动态打开的路径无法自动发现。后台 worker 由长期运行的 Houdini 会话启动，不依赖短命 MCP 客户端。

提交返回 job_id，**不表示渲染完成**。查询状态直到 `completed` 或失败；`status.json` 保存逐帧哈希，工具响应只返回最近一帧以限制载荷。进程退出、存在部分图片、桥接超时都不会自动判定成功。

单任务限制 1–300 帧，预览最大 1920×1080，同时最多两个活跃任务。可提供 `request_id`：同一 ID、同一输入返回原任务；同一 ID 改变参数会报错。省略 ID 时按 HIP/HDA/参数指纹去重。要有意重新渲染，请使用新 ID；若外部依赖已改变，旧请求会拒绝复用，须新 ID 重新预检。

调用 `cancel_render(job_id)` 后继续查询状态。它在帧边界协作停止，不强杀当前 Mantra；当前帧卡住时不能保证立即取消。对 `cancelled`、`failed` 或确认进程已退出的 `interrupted` 作业调用 `resume_render`，会保留原记录并创建新任务，校验 HIP/HDA/外部依赖及逐帧 PNG/EXR 哈希，只复用完整帧。对已有 `completed` 作业也可检查并补渲损坏帧。输入指纹改变会拒绝续渲，`launch_unknown` 不会盲目重试；需要先确认实际 worker 状态。

这些工具目前仍使用 **Mantra + COP2**。独立地图样片已完成 [Karma XPU 对照测试](docs/KARMA-XPU-COMPARISON.md)，证实4090实际参与；低采样更快但细线较粗糙，高采样三帧总耗时与Mantra接近。XPU/Solaris/MaterialX 尚未接入通用渲染工具，显卡探测字段也不代表此工具链已支持XPU。

## 资产参数预设

先用 `get_asset_schema(path)` 检查数字参数，使用 `asset_preset(action="capture", name="blue_map", path=...)` 捕获，`action="list"` 列举，`action="apply"` 恢复。预设保存在被 Git 忽略的 `.runtime/presets`，名称限字母、数字、下划线与短横线。

捕获跳过动画、锁定和禁用通道；应用要求相同节点类型及数字参数结构，先整批验证，返回修改前值。已有同名预设须显式 `overwrite=true`。预设不是 HIP 检查点，不含几何、字符串、关键帧或外部资源；重大编辑前仍应另存工程。`set_asset_parameters` 从 0.3 起直接返回参数及 `before`，不再套用 `execute_code.result` 外层。

## 验证

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/acceptance.py
```

第一条运行传输、队列与任务状态单元测试，不需要 Houdini。第二条使用 `HOUDINI_HYTHON`（或默认安装位置）执行真实 headless MCP 验收，会创建独立样例文件。GUI 验收见 `tests/gui_acceptance.py --help`，需要先启动专用 GUI 并加载 headless 验收工程。

0.3.0 开发验证通过 21 项单元检查，并经真实 MCP stdio 调用完成：地图副本的 schema/预设恢复、表达式保留、预检拒绝、重复提交、五帧渲染在两帧后取消、续渲复用两帧并补齐三帧，再故意损坏一帧并仅补渲该帧。原 HIP/HDA 指纹保持不变。0.2.0 地图资产、独立 HDA 加载、点阵地理检查与视频输出结果继续保留。

机器专属配置、场景、凭据和大体积渲染证据不提交此仓库。其他 Houdini 版本、操作系统未验证；渲染器验证范围限上文Mantra与独立XPU地图样片。Codex 当前对话的原生 MCP 工具加载仍是独立待验项，不能用外部 SDK 成功替代。

## 边界与迭代

- `execute_code` 是可信本机执行入口，不是安全沙箱；不要暴露给不可信远端。
- Python 异常可能留下部分修改；Undo 分组不等于事务。
- 已开始的同步执行超时不能强制终止 Houdini；必须检查实际状态后决定后续动作。
- `set_asset_parameters` 只支持数字参数，先检查整批输入；不会保存文件或覆盖表达式。
- 停止 MCP/关闭窗口前先检查后台渲染状态。
- 当前活跃 GUI 可能保留旧桥接模块，`ping` 分开显示已加载桥接版本与外部 MCP 版本；重启专用会话后统一加载磁盘版本。

后续按真实使用问题迭代，计划见 [ROADMAP.md](ROADMAP.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。每个增量保留可复现样例和必要验证，尚未实现的建议不计入能力。
