# 0.15：逐螺栓独立橡胶缓冲垫

2026-09-22，Windows / Houdini 20.5.487 / Python 3.11。22工具、9个配方。用户确认照片蓝色构件为每根螺栓独立的橡胶缓冲垫，属于隔振法兰部件；0.14连续凸缘蓝体解释撤回。历史几何检查结果不证明旧构造正确。

## 本轮范围

新增pipe_rack_isolated，新ID交付；只纠正前景pipe3第一套。移除pipe3_gasket，新增8个pipe3_pad_XX，part_type=rubber_pad。总212件、25252点、24780面；与实际保存的0.14基线相比，204原件的面位置、类型、Cd和对象变换不变。八份旧生成器及其嵌入源码不变，保留75份旧HIP/HDA字节。

HDA类型workai::pipe_rack_isolated::1.0.7de8ffab3e15，几何SHA为09eb09013c95fe4d3fd728bae8b096918e7742d4754cec4f1eec528a57d66ddb。

共23个数字参数，新pad_radius_ratio范围.06–.16、默认.14。pad半径/螺栓数需满足块间分离，另核中央管孔投影及邻管最大包络。16螺栓时默认半径被拒绝，已验较小半径.10。组合约束是视觉配方条件，不是工程标准。

## 实际验证

- 74项单元测试通过，包含6/7/8/16螺栓、不同管径/垫块半径、非法组合及缺块/错位/堵孔/断连/恢复连续蓝体负例。
- fresh hython打开实际保存0.14基线，创建新HDA。独立选出原生垫块、螺杆和接触法兰，核单连通、闭合/面向/体积、真实内孔环与螺杆轴线/跨度及两侧接触，然后核总装。默认两两垫块投影外包圆净距下界约57.682mm，杆孔最小投影净隙约4.172mm；均非工程要求。
- 实际HOM中轴向移20mm、偏轴20mm、缺垫块、堵孔、恢复旧连续蓝体均拒绝。半径更新只改变8块；复位指纹恢复。非法组合预检不改变几何。
- 外部MCP SDK stdio经过只读预检/创建/幂等/配方保护/非法值/联动/复位/多视图/HIP保存重开；本宿主未发现原生Houdini MCP工具，不冒充原生Codex调用。
- 独立hython在无仓库src路径环境加载交付HDA，重建指纹相同。原GUI地图恢复第97帧且dirty=false。
- Mantra完整图960×540作业fbcc6c86124d4260b158311ca446cd81；接头近景1200×900作业698570bb12b3450898647bad105b1e91。渲染HIP在受管理HDA之后用Material SOP将rubber_pad实际绑定至单独principledshader，rough=.85、reflect=.12；绑定断言通过，HDA本身未解锁。
- 实际查看完整渲染、端/顶视、联动顶视、独立垫块端/透视和总装近景：8个独立通孔垫块，近景有明确块间空域。金属法兰仍有多边形棱面，未达照片质感。橡胶材质为视觉近似。

本地证据：evidence/v015-acceptance下的unit-tests.txt、hom-01/report.json、artifact-verification.json、visual-review.json、detail-balanced-report.json、final-session.json、skill-validation.txt；资产目录assets/isolation-rack-v01/default-01下的report.json、instance.json、standalone.json和图像。用户照片及二进制资产不进入源码仓库。

## 边界和经验

独立垫/隔振用途由用户识别；圆柱垫、倒角、孔径及88mm轴向长度是推定。原管端及法兰位置保持不动；移除旧蓝环后，内部流道与密封连接明确未建，没有虚构套筒来伪造连续性。承压、密封、隔振性能未验证。其余两套蓝色件仍是待纠正的旧模型。

采用E001/E006核应有实体与空域、真实面材质及可见形体；E008用逐件指纹继承204原件，不重复旧XPU/视频。Skill同步撤回连续蓝体解释，保留“外部空域不等于穿孔”的实测经验。仅修改仓库Skill，不改全局配置、缓存或宿主记忆。

回退：源码/Skill可用06f52262bf2517702e3ecfb99684fd169ac17f02或本地evidence/pre-v015-backup；旧HIP/HDA均保留。回退只恢复旧版本，不代表撤销用户的构造纠正。后续优先根据反馈完善单套，再推广另外两套；隐藏连接需依据后续资料。
