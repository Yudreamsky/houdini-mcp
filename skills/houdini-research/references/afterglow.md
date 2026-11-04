# 第二发照亮残烟

这个镜头有独立的可见窗口。需要操作时，在项目根目录单独运行 `python launch.py --shot afterglow`。用 `afterglow(action="state")` 读当前三个控制值，或用 `knowledge(topic="afterglow",kind="shot")` 按记录找版本。

第 11 帧是柳枝起爆，第 49 帧是第二发。四个运动光源取样第二发火星的实际位置及亮度。烟属于第一发的 Pyro 缓存。若要核对受光，固定烟和火星，把 flash 在零与父版实际值之间比较。用 frame 看固定帧，用 clip 看最多 30 帧的连续短片。frame 和 clip 都走 Mantra，判断照明时优先用这些返回的渲染。

- “再短一点”若承接上一轮对余照的反馈，用 revise 的 changes 单独减小 duration。单位是帧，表示光强的衰减时间。保留粒子寿命和烟缓存。
- “烟退回 A，第二发保留 C”用 revise(key=C, smoke_from=A, note=用户的意图)。烟组包含渲染密度 smoke，二发光组包含 flash 和 duration。没有 key 时沿用现场读到的值。可用 flash_from 单独借用另一版的二发设置。
- “烟往左飘”涉及模拟速度场，当前滑块只调烟的显影浓度。需要重新模拟并验证新缓存，再进入照明比较。
- 在窗口里手调 DIRECTION 后，用 revise(note=...) 保存当下读数。向用户展示候选前可先做 frame(frame=53)，需要判断“什么时候隐去”时用 clip(start=46,end=69)。确认选版以人的实际反馈为准。
