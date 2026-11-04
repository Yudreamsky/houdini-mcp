# 经验库检索与测试

`knowledge(topic="水")`、`knowledge(topic="雨")`、`knowledge(topic="water")` 和 `knowledge(topic="ripple")` 使用同一组主题。检索标题和摘要时，`query="种子"` 与 `query="seed"` 均可找到 Ripple 节点简历及其关联实验。双语别名集中存放在 [Skill 词表](../skills/houdini-research/references/topics.json)。每个完整输入先按词表展开，普通查询保留原有的大小写无关子串匹配。

各库的 `records/<id>/card.json` 仍是摘要真源，`details.json` 仅按需读取。数据目录内的 `knowledge.sqlite3` 使用标准库 SQLite FTS5，索引标题、摘要、主题和筛选字段。每次发布新卡都会写入索引，查询时只对发生变化的卡重读 JSON，同时识别外部添加、更新和删除。本机 ID 优先于同名示例。时间倒序使用新卡的 UTC `created_at`；旧卡仍按文件修改时间排序，时间相同时用 ID 确定翻页顺序。删除索引后，下次查询会重建；旧卡和示例库无需改写。

## 速度复测

在仓库根目录执行 `python -m tests.benchmark_storage`。脚本使用临时数据目录，通过正常写入入口生成 1000 张卡，再直接调用 MCP 的 `knowledge` 处理函数。统计范围不含客户端启动或 stdio 往返。

本机 Windows、Python 3.12.4 的一次复测里，写入后首次查询 25.0 ms，15 次热查询的中位数 15.0 ms、P95 为 16.6 ms。删除索引后，在操作系统仍缓存这些文件时，全量重建查询为 138.9 ms。另一份刚生成且从未索引的 1000 张 JSON 卡首次查询约 3.8 秒，耗时主要来自逐个打开文件。磁盘和文件缓存会影响重建时间。

## Windows CI

仓库的 [Windows unit tests](../.github/workflows/tests.yml) 在 push 与 pull request 上运行，矩阵使用 Python 3.11 和 3.12。每个测试作业将 `HOUDINI_RESEARCH_HOME` 指向 GitHub runner 的临时目录。

本地可用 `python -m pip install -e . numpy` 安装依赖，然后执行 `python -m unittest discover -s tests -p "test_*.py" -v`。这条命令包含检索边界、双语召回、索引重建、跨进程写入、并发与多库去重回归。`tests/*_native.py`、`tests/*_acceptance.py` 及其他真实窗口或渲染验收按对应脚本的说明，在配有 Houdini 的本机会话单独运行。

要验证真实窗口的建网、参数实验、Ctrl+Z 和并发请求，请使用对应的 GUI 或 hython 命令。[本机验收命令](live-graph.md#本机验收)
