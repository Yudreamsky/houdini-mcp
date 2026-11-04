# Houdini Research MCP

这个项目让创作者用自然语言和 AI 一起在 Houdini 里做镜头。Houdini 提供可观察的画面和可测量的工程，Skill 帮助 AI 按需找到相关经验。遇到拿不准的节点，做对照实验；遇到现有工具做不到的操作，留下能重做的案例，推动下一次改进。[设计理念](DESIGN.md)

## 给 Claude Code 接入

在装有 Houdini 的 Windows 电脑上克隆本仓库。在仓库根目录的 PowerShell 执行以下命令。需要 Python 3.11 或更新版本，Houdini 的本机验证版本为 20.5.487。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$pythonExe = (Resolve-Path .\.venv\Scripts\python.exe).Path
$mcpEntry = (Resolve-Path .\run_mcp.py).Path
claude mcp add --scope local --transport stdio houdini-research -- $pythonExe $mcpEntry
claude mcp get houdini-research
```

看到 `Connected` 后，在同一个目录启动 Claude Code。若 Houdini 安装路径不同，注册时在 `--transport` 前加入 `--env "HOUDINI_EXE=完整的houdini.exe路径"`。其他本地 stdio 客户端也可使用上面的 Python 绝对路径作为 command、入口文件绝对路径作为唯一参数。[Claude Code 的 MCP 接入说明](https://code.claude.com/docs/en/mcp)

连接后可以用塔吊案例做一次实测。

> 用 Houdini MCP 查机械领域的净距测量配方。工程用 sample:mechanisms/Climbing-support-transfer.hip，上件用 /obj/CLIMBING_STUDY/New_section，下件用 /obj/CLIMBING_STUDY/Cart。量第 1379 到 1454 帧的 Y 向净距，最低要求 0.228 米，告诉我测了多少帧和最小净距。

预期结果为 76 帧全部通过，最小净距约 0.230 米。此检查在后台读取已保存工程。需要看窗口时可从仓库根目录执行 `.\.venv\Scripts\python.exe launch.py --hip .\examples\mechanisms\Climbing-support-transfer.hip`。

查机械案例用 `knowledge(topic="mechanical-animation", kind="mechanism_test")`，取回卡片后按 ID 展开证据。仓库附有[四个可编辑机械工程和演示](examples/mechanisms)、[实测数据](examples/mechanisms/verification.json)及[渐进式经验 Skill](skills/houdini-research/SKILL.md)。

### 在现有窗口建模

先用 `window_session(action="list")` 找到目标窗口。将它的 `id` 传给 `graph_read` 浏览网络，用 `node_types` 查安装的节点类型，再用 `graph_edit` 一次建节点、连线和设参。`cook` 给出几何读数，`capture` 返回当前场景的视口截图，`diff` 比较改动前后的连线、参数和标志。默认工具列表共 15 项。烟花、残烟和机械的专用操作按领域展开，旧工具名仍可直接调用。[建模示例、准入与验收](docs/live-graph.md)

`domain_recipe(action="catalog",domain="mechanics")` 只列机械操作及摘要，`domain_recipe(name="animation_gap")` 才返回该操作的完整参数。调用时传 `action="run"`、`name`、`arguments`。水、火、机械等经验用 `knowledge` 筛选摘要，再取相应记录和画面。[双语检索和 Windows 测试](docs/knowledge-ci.md)

### 让 Claude 在施工中发现缺口

遇到已有工具不能表达的操作、临时脚本绕行，或单参实验与预测矛盾，先检查相关工具及证据。已有父级的 OBJ 再次交给 `mechanical_rig` 时，MCP 会在错误中附上缺口 ID 和本次观察 ID，保存可重放的参数。节点实验也可返回缺口 ID。接点错位或尺寸超限等正常拒绝，应先修正场景。

没有自动返回 ID 时，用 `knowledge(kind="gap", query=能力关键词)` 查重，再用 `improvement` 的 `request.action="report"` 记录稳定的能力键、主题、预期、实测和最短复现步骤。`signal` 可选 `missing_operation`、`workaround`、`unexplained_result`。同一能力键复用同一缺口 ID，不同复现场景分别保存观察。确认需要改进时，用 `request.action="propose"` 传 `gap`、最小改动 `change`、可判断成败的复测 `acceptance`，以及已有的证据 ID 列表 `sources`。

建议保存在本机经验库。下次用 `knowledge(kind="improvement", status="proposed")` 查摘要，按 ID 展开验收条件。修复后用原例重测，拿到独立证据再用 `learn(kind="gap", status="resolved", ...)` 关联。向 GitHub 提交议题或补丁由使用者单独决定。

### 跟踪一项正在运行的解算或 XPU 渲染

`fx_watch(action="register",manifest=清单绝对路径)` 登记本机作业并返回 job ID。用 `status` 查每阶段的实际帧数，用 `wait` 传入上次的 cursor 等待变化（单次最长 45 秒），重新连接后用相同 ID 继续。XPU 阶段需要日志中出现 Saved Image 且输出文件存在并非空；若有 receipt，会同时检查退出码。渲染剩余时间是该阶段最近已写帧间隔的估计。指定 events 后可按部件名查询真实断裂帧与相对于触顶的时间。

```json
{"title":"Impact","stages":[{"name":"Bullet","kind":"solve","first":1,"count":409,"log":"solve.log","result":"motion.npz","receipt":"solve-exit.json"},{"name":"close","kind":"xpu","first":67,"count":99,"step":1,"log":"husk.log","receipt":"render-exit.json"}],"events":{"path":"events.json","fps":120,"origin":78}}
```

路径相对于清单。解算日志用 `F 78 ...` 或 `DUST 60 ...` 标记采样进度。作业包装器实际退出后原子写入形如 `{"exit_code":0}` 的 receipt。每次运行使用自己的日志、输出与回执。events 文件是包含 frame 和 pair（两个部件名）的记录数组。

本地 Windows 研发工具。独立 Houdini 窗口负责交互，MCP 返回图像并按领域保存实验经验。在 Houdini FX 20.5.487 上已验证 Ripple、Scatter、火星轨迹和 Pyro 残烟照明。

## 雨滴击水与通用节点实验

运行 `python launch.py --shot rain` 可打开随附的水面工程。[前后对照](examples/rain/before-after.mp4)、[四次画面](examples/rain/iterations.jpg)、[定稿候选](examples/rain/rain.mp4) 与 [可编辑 HIP](examples/rain/Rain.hip) 使用同一机位。工作单位为厘米，24 fps，以 0.055 倍物理时间作慢动作观察。水面使用 Ripple SOP 叠加有限波包，亮带为根据表面法线构造的天空倒影，水滴使用折射材质。没有运行 FLIP。

在新对话查 `knowledge(topic="水",kind="node")`，只有需要验证结论时才展开来源。通用工具 `node_lab` 默认在后台读取可信的已保存 HIP，支持别名 rain、afterglow 或绝对路径。`scope="live"` 在选定窗口做 `sweep`、`compare` 或 `motion`，结束后恢复参数和时间。实时实验可指定下游 `witness`。已保存 HIP 的 `compare` 和 `motion` 也可指定下游输出，并可选择 Mantra ROP 获取实际渲染。[窗口与实验参数](docs/live-graph.md)

- `nodes` 列直接子节点，`inspect` 按 query、limit、offset 筛选真实 SOP 参数。
- `sweep` 可先写 prediction，再指定节点、一个未绑定的数值参数、2–5 个值、固定帧和领域 topic。可选 renderer 指向 Mantra ROP。读取 experiment 卡看测量，用 evidence 按序号取单张真实帧。
- `replay` 重开相同 HIP 重跑实验。按点序比较 P 和存在的三分量浮点 Cd；拓扑统计检查点数及图元数。保留原始哈希，差异按每个坐标的最大绝对误差判定，几何容差为最大轴跨度的千万分之一、下限为 1e-7 场景单位，颜色为 1e-6。这个结果不证明全部属性或拓扑连接完全一致。
- `variant` 指定控制节点、changes、用途 note、topic 和输出 witness SOP，写成独立的 HIP 并登记 scene_recipe。只改变传入的数值，保留当前版本。用 `restore` 查验证读数及输出，再用 `frame` 查看该版本的实际渲染。用 `python launch.py --hip 完整路径` 在已有工程窗口打开候选。需要另开窗口时加 `--new-window`。

示例 `node_lab(action="sweep", hip="rain", node="/obj/RAIN/Wave_1", control="height", values=[0.018,0.045,0.09], frame=38, renderer="/out/RAIN_BEAUTY", topic="water", prediction="固定输入与帧，点位移 RMS 与波高成正比")`。

本案例的验收数据见 [水波检查](examples/rain/verification.json)。另有一个 [火星阻力实验](examples/ember-motion/Ember-drag-study.hip) 并排保留旧运动律与完整线性阻力模型，测量见 [速度读数](examples/ember-motion/observations.json)。风速、重力和阻力系数均可在节点上编辑。

## 先推理，再迭代画面

1. 把意见落到可观察的时段和量。例如“下落越来越假”可先检查火星末段的速度；“落点像贴上去的”可看接触前水面是否已动。
2. 写下适用条件和预期，再做单参对照。火星诊断采用静风、恒质量和线性阻力，水平初速度随时间衰减，重力和阻力共同决定下落极限。雨滴案例以深水小振幅近似估计波包群速度，并单独记录播放慢速。有关近似见 [Open University 线性阻力](https://www.open.edu/openlearn/ocw/mod/resource/view.php?id=71617) 和 [MIT 重力及毛细波](https://web.mit.edu/fluids-modules/waves/www/material/chap-3.pdf)。
3. 实验开始前可给 `sweep` 传 `expect_change`。MCP 比较被观测节点的点位置、三通道点颜色、点数和图元数，以及可选渲染图像的像素。与预测不符时登记 gap，已预期的稳定结果正常保存。
4. 发生矛盾时先换一个能区分原因的对照。实测单一指定波心、源尺寸为零时，改变 Ripple 的种子仍会改变点高度。在零波高条件重跑，才能进一步判断。可在经验库搜索 `knowledge(topic="water",query="种子")`，查到正例、负对照及修订过的结论。

## 第二发照亮残烟

安装 `pip install -e ".[afterglow]"`。在本机使用已烘焙的项目时执行 `python launch.py --shot afterglow`。全新机器可先在仓库根目录执行以下 PowerShell 命令生成 HIP 和逐帧烟缓存。

```powershell
$hython = & .\.venv\Scripts\python.exe -c "from hlab.runtime import discover; print(discover().hython)"
$library = & .\.venv\Scripts\python.exe -c "from hlab.storage import home; print(home())"
& $hython hlab/afterglow_build.py (Join-Path $library 'shots/afterglow')
```

第 11 帧柳枝起爆，第 49 帧第二发点亮残烟。缓存只含第一发产生的烟，Mantra 通过爆心及四个随火星移动的点光源照亮体积。镜头目录中的 `Afterglow.hip` 通过 `$HIP/cache` 引用缓存，可整体复制。DIRECTION 节点提供烟密度、二发光强和余照衰减时间。工作方法见 [残烟镜头](skills/houdini-research/references/afterglow.md)。

`window_session(action="list")` 列出受管窗口。取返回的 id，传给 `state` 或 `open` 的 session_id；`open` 另传 hip 的绝对路径。窗口有未保存修改时，切换请求返回 `unsaved_changes` 和当前路径。

## 启动

在本仓库根目录，使用外部 Python 3.11+ 创建环境并安装依赖。Houdini 使用其内置 Python。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe launch.py
```

可用 `launch.py --houdini <houdini.exe路径>` 指定程序。启动器只给新窗口添加会话路径。MCP 客户端配置 stdio 命令为外部环境的 python.exe，参数为 `-m` 和 `hlab.server`，工作目录指向本仓库，或先在该环境执行上述安装。将 `skills/houdini-research` 作为配套技能使用。

`HOUDINI_RESEARCH_HOME` 可指定本地数据目录，启动器和 MCP 应用同一绝对路径。默认目录是用户主目录下的 `.houdini-research`。窗口独立于 MCP 客户端，关闭窗口即可结束桥接。每个数据目录同时绑定一个研发窗口。仓库 `examples/fireworks` 随附真实对照图、短片和只读样例库，新写入的证据进入个人数据目录。可用 `knowledge` 分页筛选标题与状态，`evidence` 只调取指定的原始帧。

## 机械与烟花的领域配方

有闭环、穿绳或支承交接时，使用 `mechanism(hip, spec, output, topic)`。只填写当前机构对应的 spec，结果另存为与源文件同目录的 HIP，传 topic 可留存复测记录。

- `fourbar` 用两个固定销、三根活动杆长、初始装配侧和曲柄角度关键帧驱动平面四连杆。可将同级的三个刚性 OBJ 依次绑定为曲柄、连杆、摇杆。支点使用所选网络的 XY 坐标。生成前会检查整段角度是否经过不可达位形或死点。
- `reeving` 将卷筒圈数、有效半径和两股或四股承载绳换算为吊钩行程，同时生成对应穿法的可见绳路。正转收绳。可接到模型已有的吊钩下放量和卷筒角度通道，模型穿法须与所选倍率匹配。计算假设绳拉紧、卷绕半径固定。
- `transfer` 为载荷指定按帧顺序接手的支承，以及每对构件各自局部坐标中的接点。交接按同一时刻的世界姿态保持偏移，并检查两接点的三维距离。改变原支承轨迹或交接时刻后，重新构建以更新交接偏移。结果验证几何运动，受力、油压和结构强度另行求解。

多级机械绑定用 `mechanical_rig`。在已保存的 HIP 中选择同一 OBJ 网络内还没有变换父级的几何对象，先列父级再列子级。例如缸体选 `fixed`，活塞杆以缸体为父级选 `slider/y`，支脚以活塞杆为父级选 `slider/x`。转轴用 `hinge`。各关节在绑定帧传世界坐标支点，轴向会随后继承父级旋转。可为每个活动关节传行程范围 `limits` 和线性关键帧 `keys`，绑定帧的驱动值须为零。返回的新 HIP 与原工程同目录，可在各个 `JNT_` 控制器的 Angle 或 Travel 参数调节。已有的物体变换动画默认会阻止重绑，传 `replace_motion=true` 才会在副本中以新关节动画替换选定物体的变换曲线。适用范围为每个子件只有一个驱动父级的刚性运动链。

检查保存工程中的机械动画时，用 `animation_gap` 对两个几何 OBJ 或 SOP 沿世界轴逐帧量净距。传入 `hip, upper, lower, start, end`，默认 Y 轴，帧段含两端。净距等于前者最低投影减去后者最高投影，使用场景单位。可指定 `minimum` 或 `maximum`，返回极值和首次越界帧。缺少几何的帧单列，无法判为通过。两个构件即使横向错开也能测到轴向间隔，因此三维碰撞须另行验证。可传 `topic` 保存证据，再用 `knowledge` 检索。

下列烟花操作可通过 `domain_recipe` 的 `fireworks` 域发现。原有自动化仍可使用下列调用名。

1. `session(initialize=true)` 在空的主研发窗口初始化专用网络。打开 SCATTER 或 TRAILS 即可看到实际参数。
2. `experiment(control="npts",samples=[32,96,192],frame=36)` 回传逐档视口对照，并恢复起点。通过 `knowledge` 查摘要和证据。若测试输出完全相同，实验自动留下待查缺口。
3. `compare()` 查看同机位 A/B/C；`adjust(preset="B")` 后可在 Houdini 手调，`motion()` 查看连续帧。数值调节支持点数、种子、松弛迭代、主爆帧、速度、阻力、重力、尾长、二次爆延迟与色调。
4. `recipe(action="save",title="...",reason="...")` 保存烟花网络快照。`recipe(action="replay",key="...")` 在全新后台进程核对参数和几何，并在主研发窗口的新节点中恢复。Houdini 版本改变会记录 `conditions_changed`、新旧版本和实际比对结果。原版与分支可并存。
5. 用 `learn` 添加有来源的节点简历、缺口、项目偏好和复用记录。检索水、火可定向找到以后录入的卡片。新建记录默认只存在本机。

实时操作限定在已登记的研发窗口。后台研究可单独读取可信 HIP。个人经验库中的配方可以包含会执行的 Houdini 节点，回放时选择可信来源。
