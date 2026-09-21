# 渲染与预览经验

适用：MCP 0.4起，本机Houdini20.5.487实测。完整范围见仓库README及docs/V04-VALIDATION.md。

- `preview_asset_views` 是GUI几何检查，显色/线框/头灯不等于真实材质验收。查看完整对象及隔离系统，不能只凭一张透视图宣布无缺漏。
- `render_frames` 从保存的当前HIP和显式HDA依赖创建后台快照；提交成功只是取得job_id。用status确认终态，再用get_render_preview取得验证哈希的PNG。
- Mantra支持既有ifd+COP2流程。Karma XPU适配器只接受已验证的发光地图 `workai::indonesia_glow_map::2.0`，不接受管道样段；不能偷偷用Unlit替代金属物理材质并称其通过。
- preview/final只是采样档位。GPU硬件枚举不证明渲染参与，XPU每帧实际OptiX贡献在gpu_evidence。速度比较需要相同画面目标，并计入USD转换与启动成本。
- Houdini20.5地图Beauty AOV需正确的LPE和driver属性类型；旧样片曾生成非空黑EXR。像素告警有意义，但有意黑帧可以正常完成；非有限像素应失败。
- 同一request_id不允许改变渲染器、质量或输入。取消在帧边界执行，husk20.5主动停止可能返回1；只有明确停止回执且已开始帧都完成才按取消处理。不能把任意退出1解释成成功。
- 续渲保留父作业，校验输入和PNG/EXR哈希，复制有效帧；损坏帧单独补渲。worker退出但husk尚活跃时，先等待/检查，不能并发重试造成两份写入。
- 输入文件、失败日志和艺术效果结论各有证据；升级工具不要求重渲没有改变的既有成片。
