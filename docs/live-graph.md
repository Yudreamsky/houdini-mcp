# 在已有 Houdini 窗口建模和做节点实验

## 选窗口与版本

在 MCP 客户端调用 `window_session(action="list")`，取目标窗口的 `id`，用 `window_session(action="state",session_id=id)` 核对工程。若要打开磁盘上的 HIP，在同一窗口调用 `window_session(action="open",session_id=id,hip=路径)`。收到 `unsaved_changes` 时先处理当前工程的未保存修改。列表为空时，才从仓库执行 `python launch.py` 启动受管窗口。通用图工具和实时 `node_lab` 都接受 `session_id`，省略时使用主研发窗口。旧烟花专用操作和 `recipe` 也使用主研发窗口。在其他窗口做实验时，将 ID 显式传给 `node_lab(scope="live")`。

窗口里搭好的场景要交给 `karma`、`node_lab(scope="saved")` 或用户时，调用 `window_session(action="save",session_id=id)` 存回窗口当前的 HIP。也可传 `hip=新的绝对路径`（商业版后缀 `.hip`）另存，之后窗口改用新文件。其他已有文件不会被覆盖，随附的示例工程也不会被改写。返回文件大小和 `sha256`，之后 `state` 显示 `unsaved:false`。从没保存过的新场景必须传 `hip`。

升级前已经打开的窗口可能仍加载旧桥接。若新原语返回 `Unknown action`，先保存该研发工程，再重新打开这个受管窗口，并用列表取得新的 ID。

启动器优先使用 `--houdini` 或 `HOUDINI_EXE` 指定的程序，其次使用 `HFS`。没有指定时，它查找已登记窗口对应的安装版本，优先匹配主研发窗口。没有窗口时，从 Windows 标准安装目录选取最高的完整版本并返回提示。后台 `hython.exe` 和 `houdini.exe` 取自同一安装。多版本并存且无法确定目标时，可显式设置 `HOUDINI_EXE`。本项目的真实 Houdini 验收版本为 20.5.487。

## 用箱体试一次闭环

在空的目标窗口中，先调用 `node_types(category="Sop",query="box",limit=5,session_id=id)` 并确认类型。用 `graph_read(path="/obj",depth=1,limit=5,snapshot=true,session_id=id)` 看起点并记下返回的 `snapshot`。以下是一次 `graph_edit` 的完整参数示例，将 `窗口ID` 替换为选中的 ID。

```json
{
  "session_id": "窗口ID",
  "label": "建立两米宽的箱体",
  "ops": [
    {"op":"create","path":"/obj/BoxStudy","type":"geo"},
    {"op":"create","path":"/obj/BoxStudy/Panel","type":"box"},
    {"op":"set","path":"/obj/BoxStudy/Panel","parm":"sizex","value":2},
    {"op":"create","path":"/obj/BoxStudy/OUT","type":"null"},
    {"op":"connect","path":"/obj/BoxStudy/OUT","source":"/obj/BoxStudy/Panel","input":0,"output":0},
    {"op":"flags","path":"/obj/BoxStudy/OUT","display":true,"render":true}
  ]
}
```

`cook(node="/obj/BoxStudy/OUT",frame=1,session_id=id)` 应返回 8 个点、6 个面，局部 X 向包围盒从 −1 到 1，单位为场景单位。`graph_read(path="/obj/BoxStudy",depth=1,session_id=id)` 可核对节点、连线、非默认参数、锁定或引用状态及最近 cook 错误。每个参数只写数值和确实存在的状态（`locked`、`disabled`、`animated`、`expression`、`reference`），没有的状态不写。要看画面再用 `capture(frame=1,session_id=id)`，可另传镜头 OBJ 的 `camera` 路径。截图最大 704×396；通过相机看时按相机自己的宽高比缩放（900×2000 的相机得到 178×396），画面不会被拉伸，返回的 `resolution` 是图片尺寸。

`diff(key=快照ID,path="/obj",session_id=id)` 将本次添加的 `BoxStudy` 与起点比较。快照覆盖所选深度内的节点，分页只限制当次读回的行数。要比较内部连线，以 `/obj/BoxStudy` 为起点再取深度 1 快照。可信的烟花 `recipe` 记录也可作为对照，MCP 在独立 Houdini 进程校验并读取其节点包。

## 编辑准入与撤销

一批最多 128 项操作。成功后在 Houdini 的 Undo History 里出现 `MCP:` 加批次名称，按一次 Ctrl+Z 撤销该批次。失败会返回出错步骤并回滚。默认检查结果节点的 cook 错误。多人协作或人机轮流调参时，可在 `set` 中传 `expect`，由 MCP 核对预期旧值。改写有动画或引用的参数须显式传 `replace_expression=true`。删除已有节点时用 `allow_delete` 列出准确路径，本会话新建的节点可直接删除。

Houdini 自带的类型（没有资产定义，或定义库在 `$HFS` 下）建节点时运行它的创建脚本，参数和手动新建的一样：相机有 `resx`、`resy`、`focal`、`aperture`、`projection`、`orthowidth`、`near`、`far`，几何物体有 `vm_` 渲染参数，可以在建它的同一批里直接设置。`create` 步骤的 `init_scripts` 说明是否运行了创建脚本（没有运行的才会列在默认返回里）。外部 HDA 仍不运行自己的脚本。

重复摆放同一个零件时用 `copy`：`{"op":"copy","source":"/obj/ASM/foot_01","path":"/obj/ASM/foot_02","set":{"tx":1.3,"tz":-0.525}}` 把节点连同内部网络复制成新名字，再写入 `set` 里的参数值（最多 32 个，按 `set` 步骤同样的规则检查），一处摆放只占一步。复制件不带连线，需要时用 `connect` 接；复制 SOP 不会抢走显示标志。目标父网络要和源节点所在的网络同一类。源节点或它内部含有能执行代码的类型、外部 HDA 时，和新建一样需要主机开启许可。

返回值默认只有摘要：`count` 是步骤总数，`ops` 是每种操作的步数，`omitted` 是没有列出的步数，`steps` 只列出有话要说的步骤——有错误或警告的、存入的值和发送的值不一样的（表达式算出的值、展开后的路径文本、长文本的摘要）、没有运行创建脚本的 `create`。一批干净的摆放操作返回的 `steps` 是空的。要看每一步，传 `verbose=true`。

列出的 `set` 步骤带写入后的值。超过 200 个字符的文本只回传前 120 个字符、长度和 `sha256`，按存入的原文计算，与发送文本的 `sha256` 相同即写入无误。出错信息保持完整。

内置 `fireworks.trails` 模板可为 `Sop/python` 创建固定的烟花轨迹节点。自定义 Python、脚本回调和外部 HDA 等代码写入默认关闭。确需启用时，须由操作者在启动**目标 Houdini 进程**时设置 `HOUDINI_RESEARCH_ALLOW_CODE=1`。此类操作将目标路径和内容哈希登记到该窗口数据目录下的 `audit/graph-code.jsonl`。

每个工具在后台线程里执行，所以一次较长的实验或渲染不会挡住其他调用。取消一次窗口操作时，Houdini 还没开始处理的请求会被撤回；已经在处理的会在 Houdini 里做完，和超时的处理一样，之后先回读再决定是否重试。客户端的等待时间按操作和取样数调整。超时若显示可能已执行，先回读窗口网络、参数或结果再决定是否重试。桥接的 `bridge/orphans.log` 保留迟到请求的处理记录。

## 只展开本次实验需要的数据

- 查操作时，`domain_recipe()` 查看已注册领域和操作名，`domain_recipe(domain="mechanics")` 查看该域摘要，`domain_recipe(name="animation_gap")` 展开一个原始参数表。`domain_recipe(action="run",name="animation_gap",arguments={...})` 按该参数表执行。旧名可继续供已有客户端调用。
- 查经验时，先用 `knowledge(topic="水",kind="node",limit=3)` 取摘要。需要判断视觉差异时才按记录和序号取 `evidence`。查询指定窗口写下的记录和画面时，将相同的 `session_id` 传给 `knowledge` 和 `evidence`。[检索、索引和测速](knowledge-ci.md)
- 在当前箱体上做单参实验，可传 `node_lab(scope="live",action="sweep",node="/obj/BoxStudy/Panel",control="sizex",values=[1,2,3],witness="/obj/BoxStudy/OUT",frame=1,topic="modeling",session_id=id)`。对照命名变体用 `compare` 和 `variants`，测运动用 `motion` 和 `frames`。`capture=true` 才取视口帧，`camera` 可选。实验结束后恢复控制参数和原帧。
- 实验用几何指纹（`geometry_sha256`）判断输出有没有变化。普通的多边形几何体（没有分组、属性都是数字或文字）直接读取全部属性和连接关系，`geometry_scope` 是 `attributes`；实测 290 万点的模型一次测量 0.76 秒。含打包体、体积、曲面、分组或数组属性的几何体仍然整体序列化后再算，`geometry_scope` 是 `serialized`，每百万点要几秒，期间窗口会停顿。两种指纹的数值不能互相比较，也不能和旧记录里的比较。
- 研究磁盘上的 HIP 时使用默认 `scope="saved"`，传可信 `hip`。`compare`、`motion` 可以选择下游 `witness` 和 `renderer`（工程里的 Mantra 或 Karma 渲染节点，按节点自己的采样和分辨率出图；Karma 同一画面重复渲染逐像素一致，所以画面有没有变化照样按像素判断）。常用探索操作复用后台进程，重放验证使用全新进程。`HOUDINI_RESEARCH_WORKER=spawn` 可恢复逐次启动，`HOUDINI_RESEARCH_WORKER_IDLE` 和 `HOUDINI_RESEARCH_WORKER_TIMEOUT` 均以秒计。跨 Houdini 版本复测会保存 `conditions_changed`、两端版本及参数和几何的实际比对结果。

## 本机验收

在装有 Houdini 的 Windows 机器上，从仓库根目录的 PowerShell 执行。以下 `$pythonExe` 指向安装了项目依赖的外部 Python，`$hython` 使用 Houdini 自带 Python。

```powershell
$pythonExe = (Resolve-Path .\.venv\Scripts\python.exe).Path
$hython = & $pythonExe -c "from hlab.runtime import discover; print(discover().hython)"
$houdini = & $pythonExe -c "from hlab.runtime import discover; print(discover().gui)"

& $pythonExe -m tests.catalog_acceptance
& $hython -m tests.graph_query_native
& $hython -m tests.live_graph_guard_native
& $hython -m tests.window_save_native
& $hython -m tests.live_study_native
& $pythonExe -m tests.saved_study_native
& $pythonExe -m tests.runtime_native
& $pythonExe -m tests.karma_native
& $pythonExe -m tests.karma_materials_native
& $pythonExe -m tests.karma_runtime_native
& $pythonExe -m tests.karma_lighting_native
& $pythonExe -m tests.vantage_native
```

以下四项各自启动并关闭一个临时 GUI。依次执行可分别核对建网与选版、撤销历史、超时及并发顺序，以及建相机、长代码回传、存盘后用 Karma 渲染。无需打开个人工程。

```powershell
& $pythonExe -m tests.live_graph_acceptance $houdini
& $pythonExe -m tests.live_undo_acceptance $houdini
& $pythonExe -m tests.bridge_protocol_live $houdini
& $pythonExe -m tests.live_save_acceptance $houdini
```
