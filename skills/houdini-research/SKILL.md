---
name: houdini-research
description: 使用 Houdini Research MCP 研究节点参数、根据运动规律诊断特效、比较烟花或雨滴涟漪的实际画面，以及保存和复现手调配方。
---

先按效果用 `knowledge(topic="水")` 或 `knowledge(topic="烟花")` 读摘要，再展开与当前问题相关的证据。空结果保留未知。

- 诊断火星减速、终端速度，或要把运动预期变成单参实验时，读 [力学推理与节点实验](references/node.md)。
- 调雨滴落点、波纹传播或水环交叠，读 [水面案例索引](references/rain.md)。
- 多版比较、手动调参和跨会话复用时，读 [选版与复现](references/recipe.md)。
- 第二发照亮残烟、缩短余照或只回退某一部分时，读 [残烟镜头](references/afterglow.md)。

只讨论方法时直接讨论。已保存 HIP 的节点研究用 `node_lab`。操作原烟花实验台前用 `session` 确认窗口与起点；需要建台时单独运行注册服务旁的 launch.py，在空窗口用 `session(initialize=true)` 初始化。默认只回传当前判断需要的画面。
