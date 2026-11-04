# 力学推理与节点实验

把反馈落到一个可观察量和时段，再写出成立条件。例如“烟花落得假”可以先检查爆开后的水平速度和下落后段的竖直速度。在静风、质量和线性阻力系数恒定的模型里，水平速度衰减，竖直速度趋近终端值。火星可能在到达这个值之前熄灭。

随附阻力实验用 `node_lab(action="inspect", hip="sample:ember-motion/Ember-drag-study.hip", node="/obj/EMBER_MOTION/Drag_on_whole_velocity", query="drag")` 定位。用同一节点的 `sweep` 固定初速、重力和帧，只改变 drag。开始前填 prediction（如“第 73 帧，增大阻力会缩短水平飞行距离”）、expect_change 和 topic。比较实际位移。要判定是否接近终端速度，另看多个时刻的速度读数；单帧位置不能独立证明速度收敛。

在其他已保存的 HIP，先用 `nodes` 查当前网络的直接子节点，`inspect` 按名称或标签筛参数。用 `sweep` 比较 2–5 个不同值；需要画面时指定 Mantra ROP，用 `evidence` 取一帧。结果与预期冲突时，优先做能区分原因的对照；用 `replay` 重开同一 HIP 验证几何读数。

## 原烟花实验台

先找同节点类型、同版本和相近输入条件的 node 卡，通过来源 ID 打开需要的 experiment。烟花窗口的 `experiment` 开放 Scatter 2.0 的 npts、seed、relaxiterations，以及 TRAILS 的有限控制。这里的参数边界属于实验台，seed 在本台只扫描整数。

用 experiment 选择不同的 2–7 个值，每次改变一个参数。固定帧、输入和机位。对照图与实际回读配对。点数对点数，seed 对位置分布；只看点数无法评价 seed。发现相同输出时优先查激活条件或换帧，检查返回的 gap。对于模拟，应另验证缓存重置和时间依赖；此首版为解析轨迹。

learn(kind="node",status="observed") 写清节点类型、版本、参数、测过的范围和结论的边界，链接实际实验 ID。独立跑第二轮、核对相同输入和结论后才标 reproduced。条件变化或冲突追加卡，保留原始事实和来源。技术事实与项目审美分别写入 node、preference。复用后添加 reuse 卡；遇到工具缺口，记录最小复现、对当前任务的影响和下一个便宜的验证。
