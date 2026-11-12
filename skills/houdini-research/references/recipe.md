# 选版、手调与复现

这里的操作（compare、adjust、motion、session、recipe）都在 `fireworks` 域里，只对烟花实验台有效，用 `domain_recipe(action="run", name=操作名, arguments={...})` 调用。

A 球形、B 下垂、C 延迟分叉是设计起点。compare 用相同时间点并排观察，并恢复原来的画面帧和控制值。展示返回的图后让用户选择；需要判断节奏时，对候选 adjust 后再 motion。当前输出是视口预演。

用户选择后应用选中的 preset。让人手动调时停在可见窗口，等对方说调好了，重新读 session 并与手调前回读比较。直接 recipe(action="save",title=...,reason=...) 捕获当下的节点图；此时重新套 preset 会覆盖人的改动。偏好由对方表达，无明确选择时把示例标成测试基线。

新对话按目标或题材检索 recipe 摘要。找用户选版用 status=user_selected；test 是验收数据，baseline 是候选。用 query 搜标题和摘要，用 next_offset 继续翻页。仅在真实人工选版时保存 origin=user_selected。选定 ID 后先 replay，核对 verified、帧和参数，然后只传 adjust(changes=...)。基础 B 的 second_delay=0 表示二次爆关闭；要提前已有二次爆，先确认父版该值大于零。观察原版与修改版，认可后保存子版本，key 传父 ID。对照需同机位；外部相机改动需重新核对。首版支持随附独立节点图，其他版本及外部引用需另行验证。
