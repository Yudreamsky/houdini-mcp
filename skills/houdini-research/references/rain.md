# 水面案例索引

| 用户想改什么 | 从哪里开始 |
|---|---|
| 波纹太高、太弱，或换种子后形态变了 | 波高查 `knowledge(topic="水", kind="node", query="波高与位移")`；种子查 `query="固定源时随机种子"`。按来源 ID 取实验读数。 |
| 想让下一滴落下后，两组水环再交叠 | 查 `knowledge(topic="水", kind="interaction", query="交叠")`，核对接触帧、波前和已有水波的位置。候选里前两滴分别在第 10、25 帧接触，适合用第 38 帧检查交叠。 |
| 沿用上一版，只改一项 | 用 `knowledge(topic="水", kind="scene_recipe", query="错峰")` 找候选，再用 `node_lab(action="restore", key=配方ID)` 核对。用 `variant` 保存子版，`frame` 配合 `/out/RAIN_BEAUTY` 看实际渲染。 |

该 HIP 别名为 `rain`。整片水面的控制节点是 `/obj/RAIN/ART_DIRECTION`；单独研究第二组波纹时选 `/obj/RAIN/Wave_2`。要从某个配方换到另一个控制节点，用 restore 返回的 HIP 路径作为 variant 的 hip，指定新的 node；以 `/obj/RAIN/Reflected_sky_and_shore` 作为最终画面的几何检查节点。需要在 Houdini 里看时间线时，单独运行 `python launch.py --shot rain`。

案例使用厘米、24 fps、0.055 倍物理时间和 Ripple SOP 的有限波包。对照传播速度前先换算时间。此案例的测量适用于程序化水面，FLIP 镜头需单独验证。
