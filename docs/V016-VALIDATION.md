# 0.16：三套独立垫块与六片法兰倒角

2026-09-22。Windows / Houdini20.5.487 / MCP0.16.0，22工具、10配方。用户接受首套独立橡胶垫和轻倒角后继续下一步；本轮推广到另外两套既有接头，不补造隐藏内部密封。

## 变化与不变域

新增pipe_rack_all_pads，默认三套各8个独立rubber_pad，共24块、226件。共享pad_radius_ratio按各管直径缩放，pipe2使用自己的轴线/标高/接头位置，pipe3第二套使用second_joint_offset_3。

对实际保存的0.15基础HDA，210件面位置/part_type/Cd不变，删除pipe2_gasket、pipe3_joint_b_gasket，增加16垫块。对上轮已倒角成品，206件保持，另外四片法兰外缘改变；原第一套两片法兰与8个垫块均不变。对象世界变换一致。

基础HDA：workai::pipe_rack_all_pads::1.0.905a5350eb2d。31012点、30540面；几何SHA f1d42f7463c5902b944a6c15ffaa7f0c9706c9c82e3b72ff2e78b3a8105cd239。

收尾后32740点、32268面，几何SHA 3da34d0ac0957bf37d5149929fc1defb0a6b6cd67ae131baa03db86b31e478e9。六片法兰统一1.5mm宽度参数、3段圆弧外缘处理；孔壁/内圈面不变。倒角是HIP中的原生SOP层，独立HDA只交付基础几何，不混淆两者。新增N属性采用上一轮修复方案，220个非倒角件的法线在同一基础流前后逐项相同。

## 验证

- 79项单元测试通过，覆盖三套各自的垫/螺杆偏移，漏垫、多余垫、旧蓝环回归，以及不同管径/标高/孔数/半径组合。
- fresh hython读取真实保存成品比较上述逐件差异，核基础及六片倒角总装。每套原生垫块偏轴20mm和末套缺块均拒绝；非法邻距预检拒绝。两黑管径.30/.32m、间距.65m、垫半径比例.12联动通过，恢复默认指纹一致。
- 检查读取实际零件网格，按三套已知前缀映射到单套孔/接触检查；不生成虚拟蓝环来满足接口检查。另核全局24块覆盖、每套真实管端及法兰位置、支撑所属管段及邻件关系。
- 外部MCP SDK stdio预检/创建/幂等/非法值/配方保护、联动/复位、多视图、HIP保存重开、独立HDA验证通过。本宿主无原生Houdini MCP工具，不冒充原生Codex集成。
- 收尾HIP在无仓库src路径的fresh hython中重开并cook，指纹一致；实际检查六片法兰绑定flange_steel、24块垫绑定accept_rubber。
- Mantra完整1200×800作业d3d805652fdc4adfb813da9f16fbfa2c；三接头近景1200×900作业35c00ae23a6f44fa91a62d658ce96b03。基础端/顶/联动视图和新增两套垫块隔离视图另存。
- 九份旧生成器及其嵌入HDA源码指纹不变；86旧HIP/HDA字节保留。旧视频与XPU未重跑。Skill更新并通过结构验证，未改全局配置或缓存。

本地证据：evidence/v016-acceptance下unit-tests.txt、hom-01/report.json、artifact-verification.json、finish-report.json、standalone-finished.json、visual-review.json、final-session.json；assets/all-pads-rack-v01/default-01下report.json、instance.json、standalone.json及图像。照片和二进制资产不进入源码仓库。

## 限制、经验与下一步

独立橡胶垫和隔振用途来自用户；三处位置、垫块圆柱外形、孔径、88mm轴向长度和倒角大小是视觉模型假设。全部三套内部流道/密封连接明确未建，不能宣称工程密封或隔振性能。上方型钢、连接角码、照片材质与环境仍未完成。

采用E001/E006逐套核完整/透空范围和真实材质/法线，E008按原件指纹继承首套。多套推广需要校验每套自己的轴线、尺寸和孔关系；正例一套通过不能代表其他套。后续先选一个有参考依据的剩余构件，隐藏节点须补充资料；纯外观微调优先复用现有SOP层，不持续增加配方分支。

回退代码/Skill至9e11d521b64a66f560cadb1604348d9c7a9f9b49或evidence/pre-v016-backup；打开旧assets/flange-bevel-v02/after.hip即可回看上轮。新旧资产不覆盖。原GUI地图恢复第97帧、dirty=false。
