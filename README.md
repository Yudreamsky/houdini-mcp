# Houdini Research MCP

本地 Windows 研发工具。独立 Houdini 窗口负责交互，MCP 返回图像并按领域保存实验经验。在 Houdini FX 20.5.487 上已验证 Ripple、Scatter、火星轨迹和 Pyro 残烟照明。

## 雨滴击水与通用节点实验

运行 `python launch.py --shot rain` 可打开随附的水面工程。[前后对照](examples/rain/before-after.mp4)、[四次画面](examples/rain/iterations.jpg)、[定稿候选](examples/rain/rain.mp4) 与 [可编辑 HIP](examples/rain/Rain.hip) 使用同一机位。工作单位为厘米，24 fps，以 0.055 倍物理时间作慢动作观察。水面使用 Ripple SOP 叠加有限波包，亮带为根据表面法线构造的天空倒影，水滴使用折射材质。没有运行 FLIP。

在新对话查 `knowledge(topic="水",kind="node")`，只有需要验证结论时才展开来源。通用工具 `node_lab` 在独立进程中读取可信的已保存 HIP，支持别名 rain、afterglow 或绝对路径。

- `nodes` 列直接子节点，`inspect` 按 query、limit、offset 筛选真实 SOP 参数。
- `sweep` 可先写 prediction，再指定节点、一个未绑定的数值参数、2–5 个值、固定帧和领域 topic。可选 renderer 指向 Mantra ROP。读取 experiment 卡看测量，用 evidence 按序号取单张真实帧。
- `replay` 重开相同 HIP 重跑实验。按点序比较 P 和存在的三分量浮点 Cd；拓扑统计检查点数及图元数。保留原始哈希，差异按每个坐标的最大绝对误差判定，几何容差为最大轴跨度的千万分之一、下限为 1e-7 场景单位，颜色为 1e-6。这个结果不证明全部属性或拓扑连接完全一致。
- `variant` 指定控制节点、changes、用途 note、topic 和输出 witness SOP，写成独立的 HIP 并登记 scene_recipe。只改变传入的数值，保留当前版本。用 `restore` 查验证读数及输出，再用 `frame` 查看该版本的实际渲染。独立打开候选可用 `python launch.py --hip 完整路径`。

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
& 'C:/Program Files/Side Effects Software/Houdini 20.5.487/bin/hython.exe' hlab/afterglow_build.py "$env:USERPROFILE/.houdini-research/shots/afterglow"
```

第 11 帧柳枝起爆，第 49 帧第二发点亮残烟。缓存只含第一发产生的烟，Mantra 通过爆心及四个随火星移动的点光源照亮体积。镜头目录中的 `Afterglow.hip` 通过 `$HIP/cache` 引用缓存，可整体复制。DIRECTION 节点提供烟密度、二发光强和余照衰减时间。工作方法见 [残烟镜头](skills/houdini-research/references/afterglow.md)。

## 启动

在本仓库根目录，使用外部 Python 3.11+ 创建环境并安装依赖。Houdini 使用其内置 Python。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe launch.py
```

可用 `launch.py --houdini <houdini.exe路径>` 指定程序。启动器只给新窗口添加会话路径。MCP 客户端配置 stdio 命令为外部环境的 python.exe，参数为 `-m` 和 `hlab.server`，工作目录指向本仓库，或先在该环境执行上述安装。将 `skills/houdini-research` 作为配套技能使用。

`HOUDINI_RESEARCH_HOME` 可指定本地数据目录，启动器和 MCP 应用同一绝对路径。默认目录是用户主目录下的 `.houdini-research`。窗口独立于 MCP 客户端，关闭窗口即可结束桥接。每个数据目录同时绑定一个研发窗口。仓库 `examples/fireworks` 随附真实对照图、短片和只读样例库，新写入的证据进入个人数据目录。可用 `knowledge` 分页筛选标题与状态，`evidence` 只调取指定的原始帧。

## 第一个工作流

1. `session(initialize=true)` 在空研发窗口初始化专用网络。打开 SCATTER 或 TRAILS 即可看到实际参数。
2. `experiment(control="npts",samples=[32,96,192],frame=36)` 回传逐档视口对照，并恢复起点。通过 `knowledge` 查摘要和证据。若测试输出完全相同，实验自动留下待查缺口。
3. `compare()` 查看同机位 A/B/C；`adjust(preset="B")` 后可在 Houdini 手调，`motion()` 查看连续帧。数值调节支持点数、种子、松弛迭代、主爆帧、速度、阻力、重力、尾长、二次爆延迟与色调。
4. `recipe(action="save",title="...",reason="...")` 保存当前网络快照。新客户端检索该配方，`recipe(action="replay",key="...")` 校验版本、参数和该帧的几何指纹，在新节点中恢复。原版与分支可并存。
5. 用 `learn` 添加有来源的节点简历、缺口、项目偏好和复用记录。检索水、火可定向找到以后录入的卡片。新建记录默认只存在本机。

修改工作区或发布配置请遵守使用者的协作约定。本工具仅在专用研发窗口内工作，可信的本地知识目录中含可执行的 Houdini 节点快照。
