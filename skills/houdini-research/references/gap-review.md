# 从一次受阻的操作提出改进

先确定场景是否满足操作前提。例如支承接点错开 50 毫米时，先修正接点。若目标是给已有父级的曲柄追加关节，而现有工具只接收无父级的零件，就能用这个零件复现一项工具限制。单参结果与预测不符时，先核对控制是否生效、观察的输出和帧是否正确。

**留下能重做的观察。** 工具已经返回缺口 ID 时，用 `knowledge(key=缺口ID)` 读详情，复用这个 ID。只有人工绕行或没有现成 ID 时，先按能力关键词查 `knowledge(kind="gap", query=关键词)`，再用 `improvement` 的 `request.action="report"` 记录稳定的能力键、主题、预期、实际结果和最短复现步骤。按情况选择 `missing_operation`、`workaround` 或 `unexplained_result`。若返回 `prior_resolution`，先比较上一次修复时的条件。

**把建议写成可验收的改动。** 用 `request.action="propose"`，传入 `gap`、`change`、`acceptance` 和手里的观察或实验 ID 列表 `sources`。在曲柄案例中，可建议在原父级与曲柄之间插入中立关节。验收时重新打开工程，逐帧对比前后 97 帧的世界姿态，再把新关节转 5°，检查新旧驱动是否都有效。

向使用者说明原操作在哪一步受阻、证据是什么、建议怎么验。建议可用 `knowledge(kind="improvement", status="proposed")` 找回。实际修复并用原例取得独立复测证据后，才用 `learn(kind="gap", status="resolved", ...)` 关联原缺口与复测结果。
