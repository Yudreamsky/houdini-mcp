# 0.12：单个红管外抱接头接入三管

2026-09-21，Windows / Houdini 20.5.487 / Python 3.11。MCP0.12.0，22工具、6配方；实测经外部MCP SDK stdio，当前宿主原生Houdini工具发现未验证。桥接仍为0.1.0。

## 交付与范围

新增独立pipe_rack_coupled，将已验外抱接头嵌入照片三管变体的红管；原五个生成器保持字节不变。21个数值参数包含原19项和red_shell_width/red_clocking，joint_offset_1继续控制红管位置。固定单接头组合，不是任意局部替换工具或多接头列表。

默认161构件、19076点、18716面。HDA类型workai::pipe_rack_coupled::1.0.f1d4a24be854，几何SHA256为fead8f54845576e1ef6d4f116ea54fd6866cac845f1f153a581be6d4fceddff5。完整HDA嵌入算法，不依赖源码仓库。

## 实际核验

- 58项单测通过，覆盖逐件保持、角度/宽度联动、近邻U形件/横担侵入反例和支撑带参数拒绝。记录：evidence/v012-acceptance/unit-tests.txt。
- 独立hython加载实际保存的0.10照片样段，回读旧几何SHA f0b7052ea2af278d5ee6f2e8188c47a32e4903d7d34d22192d8b49a120363764。逐件原生面坐标/类型/Cd指纹比较：142件相同，2段红管内端改变，43个旧接头零件移除，17个新件加入；世界变换相同。记录：evidence/v012-acceptance/hom-02/report.json。
- 故意移动实际U形件或横担靠近接头，inspect均检出；改黑管一个面Cd只产生对应零件指纹变化；非法宽壳/站位预检拒绝且现有几何不变。脚本tests/coupled_rack_acceptance.py使用本地已保存基线，基线资产不随源码发布。
- 默认接头相对U形件、横担、其他邻件的AABB间距下界分别约324.0、310.5、167.1mm。这是局部包围盒的保守下界；交叠仅表示无法证明余量，不证明真实碰撞。10mm要求是视觉配方余量，不是施工净距或承载验证。
- GUI SDK完整流程：预检、创建/幂等、非法值/配方保护、联动、多视图、复位、HIP保存重开、无源码路径的独立HDA及Mantra通过。联动使用length3.6m、diameter_1 .4m、spacing_12 .65m、spacing_23 .60m、壳宽.12m、角度-35度、位置.15m；复位几何指纹一致。记录：assets/coupled-rack-v01/default-01/report.json及standalone.json。
- 完整Mantra图960×540，作业a5ab12c846a34fa58f01b8d60dc4a0dc；红管外侧近景1200×900，作业c5ebc4eab22147a2acd94bc0333094ac。实际查看完整端/顶/透视、联动顶视、隔离端/透视及近景，接头/最近U形件和横担可辨。近景有意裁掉远端；完整覆盖由总装图承担。技术脚本visual_review仍为pending，人工看图记录另存evidence/v012-acceptance/visual-review.json。

## 继承与限制

60个旧HIP/HDA文件哈希不变，sample/elbow/rack/reference/coupling五个生成器源码与操作前备份一致。继承其既有形体结果；旧五配方完整渲染、地图XPU和视频未重跑。本轮最后恢复原地图HIP第97帧，dirty=false；未留hython/husk/mantra后台进程。证据：evidence/v012-acceptance/artifact-verification.json、final-session.json及process-verification.json。

调用inspect时红接头在局部坐标复用半壳/孔/紧固件/通道检查。原rack measurement中的flange_radius在红管下为实际接头包络半径，并非红管仍有法兰。预检保留原保守法兰包络限制，另核壳宽与支撑站；不是精确全场景碰撞求解器。

照片尺寸、内部密封、背面构造和既有吊杆均为推定；壳体/凸耳保持独立相交网格，未做沟槽/键齿/螺纹/厂家规格。两根黑管保留原视觉模板；重复接头、上方型钢、风管及照片相机/磨损材质未重建。该局部候选不是全照片复刻或施工深化模型。

使用WORKAI经验E001/E006核完整空间与局部形体，E008按实际指纹继承。配套Skill新增局部装配参考，记录逐件指纹范围、世界变换与AABB结论边界。Skill结构验证通过。回退代码/Skill至76837d2c46bb9aee6cd386e39fd1af03dda9c84e或evidence/pre-v012-backup；先确认无渲染再重载服务。新旧HIP/HDA均保留独立。未修改全局配置或宿主记忆。

本页证据路径指本地验收工作区；照片、HIP/HDA、渲染图和运行凭据不随源码仓库发布。
