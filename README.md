# Houdini Research MCP

本地 Windows 研发工具。独立 Houdini 窗口负责交互，MCP 返回图像并保存实验经验。支持 Houdini FX 20.5.487 的 Scatter 节点实验、程序化烟花轨迹，以及一组 Pyro 残烟与 Mantra 照明交互镜头。

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
