# 橙色外抱接头：独立样件

适用MCP0.11的external_coupling_sample；照片形体研究，不指定厂家型号。先区分本配方与pipe_rack_reference中的蓝体/双法兰模板，不能直接覆盖旧实例或把同一instance_id强行换recipe。

新ID明确选择external_coupling_sample；现有catalog/preflight/upsert/inspect/preview流程复用，不需要另一套建模工具。七个数值参数为length、diameter、wall、shell_width、joint_offset、clocking、segments。X为管轴，clocking单位度；接头绕轴旋转，两短管网格不旋转。外管端由length保持，内管端随joint_offset移动。壳体两侧各留80mm是此配方的视觉操作边界，不是施工标准。

19个稳定零件名包括pipe_left/right、housing_upper/lower、seal_envelope，以及lug/bolt/washer/head/nut。upper/lower指clocking=0的构件局部框架，不保证旋转后仍在世界上下。选择单个紧固点时从inspect读取精确名称；part_type过滤全部bolt不能代替选中某一侧的整组凸耳/紧固件。

几何验收使用实际网格逆转到接头局部坐标：核两短管轴线、内外径和端面，核半壳轴向/径向位置、开口间隙，核杆件穿过真实多边形孔并保有净隙、垫圈/螺母座面位置。另检查面投影到管截面后的最小半径，避免只看顶点最小半径却漏掉封堵中心的面。这个轴向贯通检查不等于任意方向全场景碰撞。

实际HOM中管轴偏移、半壳错位、螺栓脱孔三个反例已被检出；Python几何测试还覆盖密封包络错位和侵入流道。不同管径与旋转角实测，完整SDK保存重开/独立HDA通过。验证入口[0.11记录](../../../docs/V011-VALIDATION.md)。

照片只支持外壳、凸耳与可见紧固件的外形研究；背半对称、内部密封包络及全部数值均推定。凸耳与半壳是有意相交的独立网格，未做制造级一体铸件；管端沟槽、壳体键齿、真实密封截面及螺纹未建。不得把封闭正体积或流道贯通写成密封/承载/压力等级验证。

实际渲染发现：沿用上方主灯的下侧近景会让螺母区域过暗，技术渲染成功不足以说明细节清楚；先看图，再为检查视角增加补光，并保留前版。局部近景可以裁掉远端管段，但完整样段另有完整图。

0.11交付独立接头；0.12另增pipe_rack_coupled，将一个接头接入红管，见[局部装配与继承](coupled-rack.md)。原独立配方保持不变。多接头列表、任意类型局部替换尚未实现，不提前写为MCP能力。
