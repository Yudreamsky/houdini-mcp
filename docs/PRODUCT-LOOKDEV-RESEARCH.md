# 产品级灯光、材质与渲染：下一轮候选

后续实测：[首轮摄影机、GI 与单灯 A/B](LOOKDEV-TRIAL-V01.md)已完成。下面保留最初调研与未实施方向，实际验收以实测报告为准。

调研日期2026-09-22。用户明确要求两个子代理分别研究产品布光、Houdini材质与渲染；本文件为两份报告的合并判断。公开资料支持原理，以下灯位、材质和渲染方案仍需本机20.5.487验证，尚未作为稳定Skill配方。

## 当前问题与优先级

0.17已解决218件封装、层高联动与有效材质继承。检查图暴露了黑底仰视暗部不足、镀锌表面高光过亮，以及照片侧风管被遮挡的问题；不能只靠加灯或提高曝光掩盖它们。当前Mantra图作为冻结对照，先只改一盏补光的位置/朝向，再讨论材质细节及换渲染器。

## 可迁移原则

**光源也会成为金属表面看到的形状。** 优先控制反射的面积、位置、明暗过渡；宽柔光负责基础可读性，方向光塑造体积，黑白反光区域帮助区分平面。broncolor的产品案例展示了这类组合，但实拍灯具的尺寸、距离和功率不能直接照搬到本模型。[产品布光案例](https://broncolor.swiss/news/the-ultimate-product-photography-lighting-setup)、[黑色物体案例](https://broncolor.swiss/zh/news/how-to-sculpting-the-dark)

**材质按可见表层分类。** 本资产的建议解释是：裸露镀锌钢/法兰采用金属反射；完整红色漆层按非金属表面处理；蓝色橡胶仍有宽高光，不能做成无反射纯色或蓝金属。颜色、粗糙度、涂层及纹理尺度需要小样；单张照片不能给出精确物理值。[Standard Surface](https://www.sidefx.com/docs/houdini/nodes/vop/mtlxstandard_surface.html)、[Base参数说明](https://help.autodesk.com/cloudhelp/ENU/AR-Core/files/ac-shading/ac-surface-shaders/ac-standard-surface/arnold_user_guide_ac_standard_surface_ac_standard_base_html.html)

**先固定色彩链再评价明暗。** 记录OCIO配置、工作空间、显示变换、曝光、输出转换；保存线性EXR和明确显示转换的PNG。数据贴图不能误做颜色转换。展示PNG发白不单独证明EXR已经丢失高光信息。[Houdini色彩管理](https://www.sidefx.com/docs/houdini/solaris/ocio.html)

**先诊断噪声来源，再提高采样。** 根据镜面/漫反射通道定位问题；降噪保留原始输出，检查槽孔、垫块间隙和窄倒角有没有被抹平。LPE可分离灯光或路径贡献，但本机输出通道仍需实际接通。[Mantra LPE](https://www.sidefx.com/docs/houdini/render/lpe.html)、[Karma噪声](https://www.sidefx.com/docs/houdini/solaris/kug/noise.html)

## 第一个实验：单灯方向A/B

保持几何、材质、相机、主光、灯功率/尺寸、背景、曝光、色彩配置和采样相同。A用当前补光；B只改变该补光的位置与朝向，尝试让前后支架下表面可读，同时避开大面积镀锌平面的直接亮反射。

每版输出整图，并按同一坐标查看前站、后站、法兰倒角、镀锌横担四处局部。局部图只作分析，不重新美化渲染结果。判优看后站是否更可读、前站是否仍有层次、孔洞边缘/蓝垫空隙/倒角是否保留。以下属于失败：只把前站照白；黑管整体变灰；红色或蓝色失真；亮带吞没边缘；A/B改变了多个无法分辨的因素。

照片侧风管的空间遮挡另列问题。灯光能改善表面可读性，不能替代几何位置或机位核对。

## MCP与Skill各自升级

| 顺序 | MCP最小增量 | Skill应记录 |
|---|---|---|
| 1 | 扩展现有渲染预检，回读实际材质绑定/缺失依赖、相机、灯光、色彩和渲染器信息 | 区分绑定问题、布光问题、显示转换问题 |
| 2 | 用受管脚本保存/应用/复位单灯姿态，复用原渲染任务作A/B；有重复需要再抽接口 | 单变量比较步骤、四处验收位置、失败图例 |
| 3 | 材质小样和明确依赖打包；保存重开后再检查外观 | 金属/漆/橡胶分类和实测参数的适用范围 |
| 4 | 有依据时补AOV、降噪前后对照及设备/耗时日志 | 噪声定位及避免细节被抹掉的方法 |

下一轮先交付第一、二项的一次闭环，不同时搭建通用材质库或更换全部总装渲染器。

## Karma XPU边界

官方明确Karma XPU不支持Mantra/Karma CPU使用的传统VEX材质；现有材质路径不会因切换渲染器自动变成兼容网络。进入XPU前需要独立验证MaterialX材质、USD材料原语和实际绑定，先选金属法兰＋蓝垫＋红漆管的一小段，保留Mantra基准。[MaterialX](https://www.sidefx.com/docs/houdini/solaris/materialx.html)、[SOP Import](https://www.sidefx.com/docs/houdini/nodes/lop/sopimport.html)

20.5发布说明包含MaterialX1.38.10、XPU自适应采样、OIDN2.2，但在线通用文档目前显示Houdini22。新增节点、当前驱动要求、灯光/AOV行为不能直接当作20.5.487已支持；也不承诺本资产的GPU加速比例。[20.5 Karma更新](https://www.sidefx.com/docs/houdini/news/20_5/karma.html)

调研没有修改场景或参数；0.17当前验证的是Mantra与几何资产工作流，本文件的产品布光/XPU方案尚未实测。经过本机A/B后再把有效步骤与参数写入Skill，保留失败条件和来源。
