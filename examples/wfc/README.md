# WFC 二维模块布局基础版

先求解合法模块布局，再由 Houdini 构建几何。`wfc_layout` 不修改场景、不要求 Houdini 窗口运行；这里的迷宫几何例子另外使用 Houdini 自带的 `hython`。所有命令从仓库根目录执行，`python` 指已安装本项目依赖的外部 Python。

## 按需发现和调用

```python
domain_recipe(domain="procedural-modeling")
domain_recipe(name="wfc_layout")
domain_recipe(action="run", domain="procedural-modeling", name="wfc_layout", arguments={
    "columns": 2, "rows": 1, "seed": 4,
    "tiles": [{"name": "panel", "west": "joint", "east": "joint",
               "south": "edge", "north": "edge"}]
})
```

上述是 MCP 调用示意。直接调用旧工具名 `wfc_layout` 也保留，但默认工具列表只显示 15 项；WFC 和 Karma 分属 `procedural-modeling` 与 `render`，按需展开。

| 参数 | 含义 |
| --- | --- |
| `columns`, `rows` | 正整数，总格数 1–256。坐标从零开始，返回的 `layout[0]` 为最下面一行。 |
| `tiles` | 1–64 种模块，每种有唯一 `name`、四个字符串接口 `west/east/south/north`，以及可选正有限 `weight`（默认 1）。 |
| `cells` | 可选的 `{x, y, allow: [模块名]}` 列表；一个名字锁定一格，多项约束取交集。 |
| `edges` | 可选对象，同时给出四个边界接口标签；不传时外边界不受限制。局部门洞等例外可用边界格的 `cells` 表达。 |
| `seed` | 随机种子，默认 0。 |
| `connected_socket` | 可选的通路标签，要求所有格通过该标签连通。 |
| `loop_free` | 默认 `false`；启用时必须给 `connected_socket`，要求连通图为树。 |

相邻接口用字符串严格匹配。权重影响选择概率，不保证最终模块数量或面积比例。旋转模块须显式列成不同模块及对应接口；这版不推断旋转、三维拼接或结构受力。

返回值含 `seed`、模块名矩阵 `layout` 和 `stats`。`decisions` 是尝试的分支数；`backtracks` 是失败后回退的次数；`propagated_removals` 统计局部接口传播删除的候选，包含失败分支，不包含全局连通/无环筛选直接删除的候选。

冲突会报告格坐标，或报告通路断连、强制成环。搜索超过 10,000 次决策会报告预算用尽；这表示本次搜索未完成，不等于证明规则无解。局部接口匹配本身不保证全局可达，迷宫样例同时开启连通和无环约束。

## 重跑迷宫与立面

以下运行器启动一个新的 **MCP 客户端进程**，通过 `domain_recipe` 生成布局。它不启动 Houdini，不修改个人经验库。输出必须是新路径；重复验收时换目录或文件名。

```powershell
python examples/wfc/run.py maze --seed 4 --output .research/wfc-demo/maze.json
python examples/wfc/run.py facade --seed 3 --output .research/wfc-demo/facade-B.json
python examples/wfc/run.py facade --seed 99 --lock-from .research/wfc-demo/facade-B.json --lock-columns 6 --output .research/wfc-demo/facade-D.json
```

- 迷宫为 13×11 格，西侧入口在 `(0,1)`、东侧出口在 `(12,9)`；应有 143 个可达格、142 条内部连接和唯一出口路径。种子 25、4、7 的回溯次数分别为 8、4、2，路径步数为 24、44、54。
- 立面为 12 开间、两层带。第三开间固定门与门头；双跨模块必须成对，竖向设备通道必须上下对应。D 锁定 B 左侧六开间，右侧重新求解；跨过锁定边界的成对模块仍须匹配。

JSON 保存完整 `request`、`result` 和求解器文件的 `solver_sha256`。复现需要相同的有序规则、种子、求解器代码和兼容的 Python 运行时；只保存种子不能重现任意未来版本。改变模块顺序、权重、约束或算法都可能改变结果。验收时保留整个 JSON 和使用的仓库提交。

`rules.py` 的 `maze_request()`、`facade_request()` 可直接用来构造 `arguments`；`maze_metrics()` 根据实际布局独立检查接口与连通性。

## 可选：生成可调参数的 Houdini 迷宫

```powershell
$hython = & python -c "from hlab.runtime import discover; print(discover().hython)"
& $hython examples/wfc/build_houdini.py .research/wfc-demo/maze.json --output .research/wfc-demo/Maze.hip
```

生成器在全新的后台场景中构建并保存，不改当前 GUI 工程，并拒绝覆盖已有 HIP。它校验输入 JSON 与当前求解器代码一致，然后将求解器、规则及几何代码嵌入 Python SOP。因此生成的 HIP 移到另一台兼容的 Houdini 上仍可自行求解，不需要原仓库路径。

在 `/obj/WFC_MAZE` 调节 `seed`、`pitch`、`wall_height`、`wall_thickness`。种子重新生成通路，尺寸参数驱动实际墙体和底板。格网 X 向对应场景 X，格网 Y 向对应场景 -Z，场景 Y 向上，几何尺寸为米。`OUT_MAZE` 是输出，`Maze_camera` 是查看全局的相机。示例为基础墙体几何，未附材质、渲染或碰撞解算；立面样例目前交付规则和布局。

需要打开查看时，使用已有窗口入口 `window_session(action="open", session_id=选定窗口ID, hip=生成的绝对路径)`，或执行 `python launch.py --hip .research/wfc-demo/Maze.hip`。现有工程有未保存修改时先处理保存。

## 验收

```powershell
python -m unittest tests.test_wfc tests.test_wfc_domain tests.test_catalog -v
python -m unittest discover -s tests -p "test_*.py" -v
python -m tests.wfc_native --output-dir .research/wfc-native-run-1
```

前两项不需要 Houdini；第三项需要已安装且可用的 Houdini。第三项通过全新 MCP 客户端生成布局，构建 HIP 后在另一个 `hython` 中重载，改三个种子，并改变间距和墙高。每组在两种高度、三个横向位置向各格四边发射射线，共检查 3,432 条射线，确认几何中的墙和通路与布局一致；不会进行 GPU 渲染或打开窗口。

验收目录保留 `maze.json`、`Maze.hip` 和 `native-verification.json`。普通单测中有一项其他领域的原生 Houdini 测试会在外部 Python 下跳过，不能据此声称该项已验证。
