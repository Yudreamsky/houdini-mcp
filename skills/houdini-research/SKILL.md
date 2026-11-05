---
name: houdini-research
description: 使用 Houdini Research MCP 搭建和检查节点网络，按层级组织场景、做参数实验、比较画面、复现配方，并用实操证据记录能力缺口。
---

先按任务用 `knowledge(topic="水")`、`knowledge(topic="烟花")` 或 `knowledge(topic="mechanical-animation")` 读摘要，选中记录后才取详情或画面。空结果保留未知。

建立可复用资产、查找复杂场景中的部件或判断修改影响时，先读 [场景组织总则](references/scene-organization.md)，再按任务选建模、机械、特效或镜头分支。采用“项目摘要 → 资产索引 → 部件接口 → 局部几何”的读取顺序，核对摘要适用的工程版本与帧。已有工程先建旁车索引，结构迁移另行确认。

- 要在可见窗口施工，先从 `window_session(action="list")` 选已有窗口，把 `id` 作为 `session_id` 传给通用工具。用 `node_types` 查实际类型，`graph_read` 小页读当前网络，需要对照时取 `snapshot`。改动放进有名称的一批 `graph_edit`，用 `cook`、`capture` 或 `diff` 核对交付。
- 要探测任意 SOP，在所选窗口用 `node_lab(scope="live", action="sweep")`，也可按命名变体 `compare` 或指定帧 `motion`。只研究磁盘上的 HIP 时用 `scope="saved"`。需要判断下游画面再选见证节点、相机或渲染器。
- 要找专用操作，`domain_recipe(domain="mechanics")` 只列该域摘要，`domain_recipe(name="animation_gap")` 展开这一项的参数。按 `action="run"` 传名称和参数。旧版参考内的操作名可以这样调用。

- 诊断火星减速、终端速度，或要把运动预期变成单参实验时，读 [力学推理与节点实验](references/node.md)。
- 调雨滴落点、波纹传播或水环交叠，读 [水面案例索引](references/rain.md)。
- 多版比较、手动调参和跨会话复用时，读 [选版与复现](references/recipe.md)。
- 第二发照亮残烟、缩短余照或只回退某一部分时，读 [残烟镜头](references/afterglow.md)。
- 用 Karma 试渲、调采样和降噪或保存出图预设时，读 [Karma 试渲与调参](references/render.md)。
- 操作被工具能力卡住、必须写临时脚本绕过，或单参实验与预测不符时，读[缺口评审](references/gap-review.md)。

只讨论方法时直接讨论。建立原烟花实验台需要空的主研发窗口，确认该窗口后用 `fireworks` 域的 `session(initialize=true)` 初始化。默认只回传当前判断需要的画面。
