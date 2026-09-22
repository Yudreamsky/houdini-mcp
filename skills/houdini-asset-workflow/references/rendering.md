# 渲染与预览经验

适用：MCP 0.18，本机Houdini20.5.487实测。新增能力与边界见 [0.18验证](../../../docs/V018-RENDER-WORKFLOW.md)；旧地图生命周期仍保留。

- `preview_asset_views` 是GUI几何检查，显色/线框/头灯不等于真实材质验收。查看完整对象及隔离系统，不能只凭一张透视图宣布无缺漏。
- `render_frames` 从保存的当前HIP和显式HDA依赖创建后台快照；提交成功只是取得job_id。用status确认终态，再用get_render_preview取得验证哈希的PNG。
- Mantra支持既有ifd+COP2流程。默认XPU路线保留发光地图 `workai::indonesia_glow_map::2.0`；物理资产需显式传 `xpu_surface`，支持单帧polygon及受限无贴图Principled→MaterialX standard_surface。材质、面光数值是近似映射，不能称Mantra像素等价；不能用Unlit替代金属。GPU实测覆盖矩形面光，点光仅实现和参数验证。
- preview/final只是采样档位。GPU硬件枚举不证明渲染参与，XPU每帧实际OptiX贡献在gpu_evidence。速度比较需要相同画面目标，并计入USD转换与启动成本。
- Houdini20.5地图Beauty AOV需正确的LPE和driver属性类型；旧样片曾生成非空黑EXR。像素告警有意义，但有意黑帧可以正常完成；非有限像素应失败。
- 同一request_id不允许改变渲染器、质量或输入。取消在帧边界执行，husk20.5主动停止可能返回1；只有明确停止回执且已开始帧都完成才按取消处理。不能把任意退出1解释成成功。
- 续渲保留父作业，校验输入和PNG/EXR哈希，复制有效帧；损坏帧单独补渲。worker退出但husk尚活跃时，先等待/检查，不能并发重试造成两份写入。
- 输入文件、失败日志和艺术效果结论各有证据；升级工具不要求重渲没有改变的既有成片。

## 调采样：先局部，再全图

1. `preflight_render`/`render_frames` 的 `sampling` 覆盖quality。Mantra例：`{"pixel_samples":[4,4],"min_rays":1,"max_rays":16,"noise_threshold":0.005,"sample_lock":true,"seed":0}`；min/max必须同时给，其他省略值继承场景，像素采样省略则用quality。XPU仅 `{"pixel_samples":64}`。看返回的saved_sampling、每帧effective_settings，不能把HIP保存值当作实际任务值。
2. `region=[left,top,right,bottom]` 是完整分辨率下左上原点像素框，右/下边界不含。固定相机、width/height与区域，只换采样。Mantra用camera crop，XPU用USD dataWindowNDC；输出仍是全尺寸画布，区域外透明/黑。区域选够上下文，过滤和降噪在边界附近可能不同；不要把小图放大当成相同像素密度。
3. 两档完成后 `compare_render_jobs(job_ids=[...],frame=1)`，输入必须同HIP/HDA/依赖、相机路径、区域、诊断配置、随机seed及渲染器。返回显示空间MAD噪声代理、相邻MAE与计时；纹理/边缘会污染MAD，MAE不是误差真值。不要自动宣布收敛。XPU区域与全图噪声不保证逐像素一样。
4. 调参后新request_id；同ID换参拒绝。续渲只从父任务冻结输入创建子任务；新v6请求还验证manifest摘要，旧任务兼容不补造历史证据。诊断文件缺失/损坏也会使对应帧重渲。

本轮C3 192×128、区域[48,32,144,112]，2×2→4×4实测15.66→32.70秒，局部代理2.81→1.12；只说明这块低分辨率样本，不能代替960×640原图收敛判断。先前9×9整图43分钟不是推荐默认。

## 相机和面光

`lookdev_rig(action="apply",name="product",settings=...)`创建独立owner子网，三盏面光key/fill/rim、三个透视机位hero/reference/detail；apply可局部改，capture返回可复用settings，inspect只读。`restore`传`settings={"restore_token":token}`，当前指纹不匹配则拒绝，避免覆盖人工后改。保存重开后token仍可用。旧灯保持，渲染前应明确哪些实际贡献，避免叠加九盏历史灯。

灯光字段：position/target/size/intensity/exposure/color/enabled；相机：position/target/focal_mm/aperture_mm/resolution。单位米，Y朝上，局部-Z朝目标。默认强度2/1/1只是设计起点，不能直接叫产品级预设；暗图先排查转换错误，再调功率。用长面主光控制金属反射宽度，补光保留暗部层次，窄面轮廓光显倒角；逐盏变化并核相机、材质、曝光不变。先放大法兰/孔/蓝垫，再决定是否提高功率。

## 物理XPU、颜色与诊断

- `xpu_surface={"light_paths":[...],"excluded_object_paths":[...],"excluded_light_paths":[...]}`精确声明选入与排除；asset_path必须是目标SOP。其他开启的灯、显示几何未交代会拒绝。检查导出报告的218件身份、逐面材质、P/N/Cd、世界变换；单张渲染不能替代几何完整性验收。
- 当前只验单帧、不透明polygon、透视/正交，无贴图/置换/透射/SSS/coat等。不会迁移Mantra全部渲染深度参数；关闭DOF和运动模糊。源数值按Linear Rec.709传递，husk `--ocio 0`，不能擅自叫ACEScg。先确认源工作空间适合这条路线。
- 保留既有COP显示链。本样段源是Linear Rec.709→ACES SDR/sRGB，预乘Alpha先除后乘。不要直接把线性EXR写成PNG当成正确显示，也不要对已显示变换的图重复变换。
- `diagnostics={"aovs":["direct_diffuse","indirect_diffuse","direct_specular","indirect_specular"],"denoise":true}`输出独立通道EXR/PNG和OIDN版本。`get_render_preview(variant="raw"/"denoised"/AOV名)`只返回记录且哈希通过的图片。黑通道可以合法；四反射通道不一定覆盖发光、透射和体积的beauty。
- OIDN是本机原生beauty-only空间降噪，无albedo/normal引导或时域保证；原EXR/PNG保持。检查法兰亮边、槽孔、螺纹、小垫块间隙，降低颗粒和降低细节都会减小梯度；不能凭统计下降通过美术验收。反光形状不对，应改材质粗糙度/灯形与方向，不能只加采样或降噪。

## 本轮发现的转换陷阱

Houdini面的绕序必须在USD显式标为leftHanded。直接保留P/N/Cd还不够：默认rightHanded会让本样段的蓝胶与管面异常暗。已用同灯/材质/机位、仅切换orientation的原生XPU对照确认因果；修复恢复蓝色和漫反射。检查几何面方向与authored N的一致性；不能凭球体样片或GPU贡献100%宣布完整资产通过。保留暗图、排查记录和修复后图，勿把转换缺陷固化为高曝光预设。
