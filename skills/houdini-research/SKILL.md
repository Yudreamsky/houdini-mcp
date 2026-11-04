---
name: houdini-research
description: 在 Houdini 研发窗口比较节点参数、观察实际画面、保存手调配方或按效果检索实验经验。适用于使用 Houdini Research MCP 的节点实验和烟花选版。
---

先用 `knowledge(topic=目标)` 读卡片摘要，只展开本次用到的一两条 ID。检索支持 fireworks/烟花、particles/粒子、scatter/散点；water/水 和 fire/火 可保存经验，首版随附案例仅覆盖烟花。空结果保留未知。

- 研究节点、处理证据冲突、写数字简历时，读 [节点实验](references/node.md)。
- 多版比较、手动调参和跨会话复用时，读 [选版与复现](references/recipe.md)。

只讨论迭代方法时直接讨论。做实验前用 `session` 确认独立窗口和实际起点。窗口未启动时，通过已注册的 houdini_research 命令找到 run_mcp.py，用同一 Python 单独运行它旁边的 launch.py；空窗口用 `session(initialize=true)` 搭建实验台。阶段画面用 `observe`，时间和节奏用 `motion`，旧证据用 `evidence`。默认只回传一张对照图。超出可观测范围时，用 `learn` 登记具体缺口。
