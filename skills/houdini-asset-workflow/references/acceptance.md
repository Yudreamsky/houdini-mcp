# 参数预检与可复用验收

适用MCP0.7起的配方验收；0.9新增pipe_rack_sample，0.10新增pipe_rack_reference，0.11新增external_coupling_sample，0.12新增pipe_rack_coupled，当前六个配方。运行版本以ping为准，工具调用成功与ready/验收通过分别判断。

## 参数调整

`list_procedural_assets`给出数值类型、单参数边界及constraints。每条组合约束有id、相关字段和比较方式，调用者无需从报错猜规则。0.9多字段右侧使用terms系数字典加offset，旧right/scale继续有效；预检返回计算后的limit。约束是配方可用范围，不是工程规范。

`preflight_asset_instance(instance_id=..., parameters={...})`对已有实例合并当前参数，并自动识别recipe；新实例默认直管，新弯头须指定recipe。ready=false时先读errors中的code、fields、actual、limit，修正整组输入。人工编辑、动画/锁定通道、归属或配方版本问题不可通过删表达式、解锁或覆盖元数据来绕过。

预检不创建节点、不安装/编译HDA、不设置参数或主动cook；不因此承诺几何、碰撞或渲染成功。ready=true返回的是当前状态下的计划，未锁定场景。upsert会重新读取并校验，期间有人改动场景时以新结果为准。

照片配方另检查接头与支撑站重叠，catalog.validation_notes说明这一额外检查。它在声明式约束之后执行，不能把constraints列表当作该配方所有规则的完整表达；失败时一并读取错误消息。

元数据校验与写入共用prepare；嵌入几何的原validate仍再次校验。本轮合约声明放在独立模块，避免只改说明就改变既有HDA指纹。添加约束时同步测试声明与实际几何校验器的一致性。

## 可复用脚本

从仓库根目录运行 `scripts/accept_asset.py --help`。外部Python需安装本仓库MCP依赖，`--hython`指向对应Houdini版本。完整命令示例见仓库README；脚本路径相对仓库根目录。

必填：`--recipe`、`--expected-hip`（GUI当前已保存、无未保存修改的文件）、`--output`（尚不存在的新目录）、`--hython`。可选 `--parameters` / `--update` 是JSON文件；未指定update时使用该配方已验的加长/加粗样例。加 `--render` 才执行一帧Mantra渲染。

脚本会临时切换当前GUI场景，适用于用户已批准的验收工作，运行期间不要同时编辑该Houdini会话。它核对expected-hip与保存状态，独立建样段、只读预检、创建、自动识别更新、反例拒绝、多视图、复位、打包HDA/HIP、重开，再调用 `scripts/verify_hda.py` 在独立hython中重建。finally恢复原HIP/帧并核干净状态与原文件指纹。它不保证恢复所有UI面板布局。

脚本退出后读report.json，检查passed、source_unchanged、restored_session；请求了渲染时再检查job_id、render_warnings和实际PNG。`visual_review`故意保留pending，技术脚本不能自己宣布美术合格。由实际看图的操作者另存review记录，不把全黑告警的宽容策略当作视觉通过。

输出目录已存在时拒绝覆盖。失败保留报告和日志，不在原目录反复重试；先查error和当前GUI状态。渲染超时只请求取消，不声明已停止，先用get_render_status确认终态/进程状态，再决定重跑。脚本不会自行发布GitHub、安装Skill或修改客户端配置。

每次普通小改根据受影响逻辑选择样例和必要保护测试。0.7两配方全流程源于共享解析/脚本同时改变；0.9主要跑新三管配方，保留旧算法指纹，并核旧直管/弯头只读检查及幂等更新。不能把历史全流程报告写成本轮重跑。

0.10照片配方独立跑完整流程；旧三配方生成源码保持原指纹，并实测旧三管检查与几何指纹。精确构件隔离另用tests/part_views_acceptance.py核选择、节点显示/渲染状态恢复及源几何不变。技术验收后仍须看PNG，尤其检查细长支架是否被裁切；透视留白不代表几何缺失。
