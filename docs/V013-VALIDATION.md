# 0.13：黑管双接头与连续管段

2026-09-21，Windows / Houdini20.5.487 / Python3.11。MCP0.13.0，22工具、7配方，桥接0.1.0；本轮通过外部MCP SDK stdio实测，当前宿主没有原生Houdini工具。

## 交付范围

新增独立pipe_rack_repeated，在原三管外抱接头候选的前景pipe3增加第二套蓝色组件，保留原第一套、红管、中间黑管和支架。原右管段缩短，新增中段，形成三段连续空心管。不是复制接头后仍保留一根贯穿其内部的重复管道。

参数共22个，新增second_joint_offset_3，默认X=.98m；第一套由joint_offset_3控制，默认X=.12m。固定双接头、第二套位于第一套右侧。端部80mm、两硬件包络间80mm、支撑旁10mm均为视觉配方约束。照片提供重复连接线索，默认数量和间距均为有边界的推定，不是现场实测或总数判定。

默认205构件、22372点、21900面。HDA类型workai::pipe_rack_repeated::1.0.147b4aa0a610，几何SHA256为7688e42276c77e4032818f6329ae29fe32d55abc52824dcc7e8e19d6e1e93068。原六份生成器保持不变，现有实例不隐式迁移；新ID另存候选。

## 实际核验

- **64项单测通过**：既有58项加局部继承、第二接头移动、四组支撑覆盖、中段缺失/错移、非法站位/端部/相互间距以及蓝体/横担错移。见evidence/v013-acceptance/unit-tests.txt。
- **真实保存基线对比**：独立hython读取0.12保存的HIP，旧几何SHA fead8f54845576e1ef6d4f116ea54fd6866cac845f1f153a581be6d4fceddff5不变。160个原构件的面位置/类型/Cd一致，世界变换一致；仅pipe3_pipe_right改变，增加middle及43个第二接头零件，无退役件。见evidence/v013-acceptance/hom-02/report.json。
- **真实反例**：中段错移20mm、第二蓝体错移20mm、第二套螺杆错移300mm、横担朝接头错移380mm和中段缺失均检出。三类非法参数预检拒绝且不改当前几何。第二接头从.98改至1.10m，只有第二套零件及middle/right变化，复位指纹恢复。脚本tests/repeated_rack_acceptance.py依赖本地已存基线，资产不随源码发布。
- **实际轴向覆盖**：三段范围约[-1.4,.076]、[.164,.936]、[1.024,1.4]m；两间隔由蓝体填充，端面衔接误差在浮点容差内。两横担分别处于left和middle管身区间。第二接头对选定支撑/第一接头邻件的AABB间距下界约262.7mm；此为保守下界，包围盒交叠不等于实际网格碰撞。
- **GUI SDK全流程通过**：预检/创建/幂等、非法值及配方保护、参数联动、复位、多视图、HIP保存重开、无源码路径独立HDA及Mantra。联动length4.4m、diameter_3 .32m、spacing_23 .58m、second_joint_offset_3 1.10m；支撑由2组增至4组并核实际承托管段。见assets/repeated-rack-v01/default-01/report.json和standalone.json。
- **完整渲染已查看**：960×540，Mantra作业ef077f33479443999b827b96f0d65bd6。端视/顶视/完整透视和联动顶视确认三根管、前景双接头及支撑覆盖。技术脚本visual_review保留pending，实际看图另记，不以PNG存在宣布照片还原。

## 最终近景、继承与会话

1200×900双接头近景作业64505ad99448453282c6fb3cbd6b35e2完成并实际查看；双接头、其中间管段和最近U形件/横担可辨。另核pipe3整段与最近横担的隔离顶视/透视，取景不代替实体检查。最终几何指纹不变；evidence/v013-acceptance/detail-balanced-report.json与visual-review.json保留调用和看图证据。

65个旧HIP/HDA与六个旧生成器源码字节不变，见artifact-verification.json。继承原已验形体；旧六配方完整渲染、XPU/视频未重跑。final-session.json确认恢复原地图第97帧且dirty=false，工具22/配方7；process-verification.json无hython/husk/mantra残留。Skill结构验证通过。

## 修复与限制

首轮HOM在隔离接头复用旧检查器时遗漏support_style=u_bolt_v1，使检查器使用旧中心高，误报管径和螺栓圈；没有移动模型去迎合误报。传入正确约定后重跑HOM通过，失败日志保留evidence/v013-acceptance/hom-01.log，成功为hom-02。几何生成器未因此改变。

重复接头检查核实际管段范围/轴线/内外半径、两个蓝体/法兰/管端接口，并分别复用孔拓扑和螺栓跨法兰检查。支撑数量及孔隙检查之外，补了完整横担轴向宽度落在唯一管身区间的检查；不是支撑间距规范或承载验证。

蓝色连接件仍是未识别产品的外观模板，照片可见的外缘凸部/台阶尚未细化；上方型钢/角码、吊顶风管、厂家内部机构、沟槽/键齿/螺纹和磨损未建。当前是固定双接头案例，没有任意接头列表、通用管网、碰撞系统或装配动画。

使用WORKAI经验E001/E006核完整空间与可见目标、E008按逐件指纹继承；Skill在局部装配参考内补充连续管段、轴向承托及隔离检查坐标约定。回退至89abd8119e31f18a4fbb7cae0ed0ff7b74926619或evidence/pre-v013-backup；确认无渲染后重载MCP，旧HIP/HDA保留独立。未修改全局配置或宿主记忆。

证据路径为本地验收目录。用户照片、HIP/HDA、渲染图、运行凭据不随源码仓库发布。
