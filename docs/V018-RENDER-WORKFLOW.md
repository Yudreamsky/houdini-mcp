# 0.18 渲染工作流

本轮将五项已批准能力接入同一条 MCP 渲染链。24工具；几何生产基线仍为0.17的218件双层总装，10个生成配方不变。Houdini20.5.487、Windows、RTX4090实测。

## 接口

`preflight_render`和`render_frames`增加四个可选参数，保留旧调用：

| 参数 | 范围 |
|---|---|
| sampling | Mantra: pixel_samples=[x,y]、min_rays/max_rays成对、noise_threshold、sample_lock、seed；XPU: pixel_samples整数 |
| region | [left,top,right,bottom]，完整分辨率、左上原点、右下边界不含 |
| xpu_surface | 明确asset_path SOP和light_paths；其他开启灯/显示对象列excluded_light_paths/excluded_object_paths |
| diagnostics | 四个固定反射AOV名与denoise布尔值；默认空，不增加诊断成本 |

Mantra像素轴1–32、rays1–4096；XPU像素样本1–4096。这是输入界限，不是推荐预算。自定义采样优先于quality；未给的ray参数继承场景，未给像素样本沿用preview/final。实际ROP回读在每帧`effective_settings`和job目录`effective_####.json`，XPU保留husk命令及每帧设备统计。

新增`lookdev_rig(action,name,settings)`和`compare_render_jobs(job_ids,frame)`。前者管理独立owner子网，不改旧灯；后者拒绝不同场景、区域、后端、诊断配置和随机seed的比较，只允许采样变化。`get_render_preview`新增variant：raw、denoised或四AOV名。

```python
# 合并进既有HIP/ROP/COP/HDA参数；先preflight，再提交。
sampling = {"pixel_samples": [4, 4], "min_rays": 1, "max_rays": 16,
            "noise_threshold": 0.005, "sample_lock": True, "seed": 0}
region = [48, 32, 144, 112]  # 本次192x128验收区域；实际项目按完整分辨率选区。
diagnostics = {"aovs": ["direct_diffuse", "indirect_diffuse",
                        "direct_specular", "indirect_specular"], "denoise": True}
```

`lookdev_rig`接受lights.key/fill/rim的position/target/size/intensity/exposure/color/enabled及cameras.hero/reference/detail的position/target/focal_mm/aperture_mm/resolution。capture.settings可以再次apply；apply返回restore_token，restore传`settings={"restore_token":token}`。人工改过后指纹不匹配会拒绝。默认灯强度是探索起点，未标定成品曝光。

## 原生与真实MCP核验

本机宿主未发现原生工具，使用真实MCP Python SDK stdio，而非直接Python调用冒充MCP。证据均在本地`evidence/render-upgrade-v018/`，不入GitHub。

- `sdk-report.json`：24工具；C3两档实际Mantra局部渲染、比较、四AOV、原生OIDN；rig创建、捕获、改单灯、冲突保护回退、保存重开；完整管架XPU任务完成。
- C3区域：192×128完整画布，[48,32,144,112]；2×2/1–4与4×4/1–16，noise0.005/seed0锁定。Mantra调用15.66/32.70秒，MAD代理2.81/1.12，相邻显示MAE4.12/255。不是960×640画质结论，也不是无偏误差。
- `diagnostics/roi/verification.json`：Mantra128²及XPU256×144独立ROI。EXR displayWindow保持，dataWindow精确收缩；区域外零，像素坐标不变。Mantra同参数区域内RGB/Alpha误差0；XPU低采样仍有随机差，最优位移(0,0)。不是事后裁图。
- `rig/report.json`、`rig/rollback-report.json`：保存重开、手动冲突、外来占位、无效参数、单灯变动、注入半写失败后的恢复。旧rig恢复精确指纹，新rig失败后删除自己创建的子网。
- `xpu/native-verification.json`：完整218件、175356点/175088面、P/Cd/构件身份/世界矩阵及五套逐面材质绑定；已实现受限Principled→MaterialX standard_surface。五材质球lit/dark真实渲染，关灯后RGB精确0，OptiX贡献100%，不是Unlit。
- `diagnostics/verified-03`及`diagnostics/xpu-verified`：两后端四通道和OIDN；原始EXR/PNG哈希保持，source COP恢复，用户已有AOV保留，同名不同LPE拒绝。四反射通道在小球例合成接近beauty，不泛化到发光/透射/体积。
- `xpu/map-regression`：旧地图适配器源码不改，256×144/16spp/97帧真实XPU回归，OptiX100%、非黑有限像素及尺寸通过，原HIP/HDA保持。

真实总装检查发现并修复了一个球体测试未暴露的缺陷：Houdini面的顺序导到USD时遗漏`leftHanded`，蓝胶与管面异常暗。`xpu/winding-ab/result.json`在同灯/材质/机位240×160、8spp下，只改orientation，蓝胶和漫反射恢复；直接漫反射均值由0.0000659变为0.070219。不是靠增加灯功率解决。最终导出新增所有面的Newell几何法线与authored N方向审计；175086可比面无反向，两个非零角点N平均相消的面单独报告，保留原几何。真实零N仍拒绝。隐含相机crop也不再默默忽略。

最终`sdk-final-report.json`：480×320、32spp法兰特写，已看原始与降噪两图；蓝色独立垫块、间隙和法兰亮边可读。job `111267fccda64145b7c346bd8153be93`，OptiX4090贡献100%；USD导出45.01秒、husk进程56.58秒、worker总108.18秒。这不是与Mantra同材质/同分辨率的提速比较。降噪软化细碎反射与螺栓纹理，原图保留；灰管反光形状仍可继续做美术改进。

115项自动测试通过，Skill结构验证及项目链接文件哈希通过；真实SDK拒绝布尔采样、布尔区域坐标、未知预览变体及不兼容比较，场景仍保持已保存。完整证据索引`acceptance-summary.json`和`visual-review.json`。原0.17总装、C3试拍、高采样HIP及HDA源指纹保持。

新请求v6包含manifest摘要。worker、重复请求、resume校验冻结记录；诊断缺文件/缺字段/大小或SHA变化使该帧失效，子任务复制全部原图、AOV、降噪及日志。旧请求兼容原机制，不能把新摘要保证追溯到旧记录。摘要防止意外篡改，不是防恶意本机用户的安全边界。

## 适用边界

物理XPU只支持显式选定的单帧polygon资产、无贴图不透明Principled子集、透视/正交与矩形面光/点光。GPU样片覆盖面光，点光尚无专项视觉验收。其他开启灯和显示几何必须显式排除；不支持纹理、置换、透射、SSS、coat或任意材质图。材质与灯光数值近似映射，不保证与Mantra像素/光度等价；不复制Mantra全部GI深度设置，DOF/运动模糊关闭。

源颜色数值采用Linear Rec.709、husk关闭额外OCIO变换，再用既有COP完成ACES SDR/sRGB及预乘Alpha处理。不能把源数值重新解释为ACEScg。OIDN仅beauty空间降噪，无albedo/normal辅助或时域保证；统计梯度下降混合去噪与细节损失，需要看倒角、孔边和垫块间隙。

UI与生产资产保持单一写入，GUI最终恢复地图97帧、无未保存修改。采用E005/E006/E008：确认真实材质绑定、看原生输出、保留失败图和回退证据。五项功能验收不等于产品级灯光美术最终验收。

## 回退

本轮前源代码基线`902c81e5f54c320e27316a1f5b01e264359c4fed`；源代码zip、原Skill及状态在`evidence/render-upgrade-v018/backup`及`previous-state.md`。候选HIP在独立证据目录，生产HIP/HDA不覆盖。需要撤回代码时由该commit另建工作树或取指定文件，不用破坏性reset；Skill恢复备份。项目MCP配置和全局Codex配置未变。
