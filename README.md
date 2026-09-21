# Houdini MCP

一个随实际资产制作逐步完善的本地 Houdini MCP。当前版本 **0.2.0**，已在 **Windows / Houdini 20.5.487 / Python 3.11** 验证。

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

- 已保存 HIP 的绝对路径、显式 `asset_libraries` HDA 路径。
- `rop_path`、`source_cop_node`、`composite_node`。
- 起止帧和分辨率；可选 `asset_path` 与数字 `parameters` 覆盖。

每个任务复制 HIP 和给定 HDA，输出写入独立 `evidence/render-jobs/<job_id>`。未保存的 GUI 修改不会进入快照，其他纹理/缓存尚不自动打包。后台 worker 由长期运行的 Houdini 会话启动，不依赖短命 MCP 客户端。

提交返回 job_id，**不表示渲染完成**。查询状态直到 `completed` 或失败；`status.json` 保存逐帧哈希，工具响应只返回最近一帧以限制载荷。进程退出、存在部分图片、桥接超时都不会自动判定成功。

单任务限制 1–300 帧，预览最大 1920×1080；这是当前边界，不是性能承诺。尚无取消、自动续跑或自动重试工具。部分正确帧可以在核对相同 HIP/HDA/参数快照后人工复用。

## 验证

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/acceptance.py
```

第一条运行传输、队列与任务状态单元测试，不需要 Houdini。第二条使用 `HOUDINI_HYTHON`（或默认安装位置）执行真实 headless MCP 验收，会创建独立样例文件。GUI 验收见 `tests/gui_acceptance.py --help`，需要先启动专用 GUI 并加载 headless 验收工程。

0.2.0 开发验证包含参数化地图资产、独立 HDA 加载、保存重开、点阵地理检查、分帧渲染与动画输出。机器专属配置、场景、凭据和大体积渲染证据不提交此仓库。其他 Houdini 版本、操作系统与渲染器未验证。

## 边界与迭代

- `execute_code` 是可信本机执行入口，不是安全沙箱；不要暴露给不可信远端。
- Python 异常可能留下部分修改；Undo 分组不等于事务。
- 已开始的同步执行超时不能强制终止 Houdini；必须检查实际状态后决定后续动作。
- `set_asset_parameters` 只支持数字参数，先检查整批输入；不会保存文件或覆盖表达式。
- 停止 MCP/关闭窗口前先检查后台渲染状态。
- 当前活跃 GUI 可能保留旧桥接模块，`ping` 分开显示已加载桥接版本与外部 MCP 版本；重启专用会话后统一加载磁盘版本。

后续按真实使用问题迭代，计划见 [ROADMAP.md](ROADMAP.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。每个增量保留可复现样例和必要验证，尚未实现的建议不计入能力。
