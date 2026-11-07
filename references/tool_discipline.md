> **打包说明**：本文件由 `03_工作流_workflow/00_系统工程规范与执行纪律.md` 转换生成（2 代，`references/tool_discipline.md`），**禁止直接修改，修改请改源**。
>

# 执行纪律与工具使用

> **本文件为 00 篇的抽取视图**：收录 §二 CLI 纪律、§五 子代理契约、§六 候选事实入口、§七 分析尺度契约；§一、§三、§四 见 `references/workflow.md`。

## 二、CLI 脚本调用与防呆纪律

WaveCycle 体系配备了高精度的标准化 Python 工具箱（位于 `scripts/`）。**本文所有 `scripts/...` 命令一律相对技能根解析**，技能根定义与唯一合法运行位置见 SKILL 第 1 节「执行根」；不得写成仓库相对路径（安装后不存在仓库构建目录这一层）。严禁任何执行代理“重复造轮子”或自行拼接不可靠的即兴数学逻辑。

### 2.1 脚本优先与“调用先读 `--help`”契约
1. **能调入库工具，绝不自写脚本**：极值提取用 `scripts/swings.py`，预检质检用 `scripts/preflight.py`，关键位扫描用 `scripts/key_levels.py`，规则复核用 `scripts/rule_check.py`，绘图用 `scripts/ew_chart.py`。
2. **强制查阅接口定义**：在首次调用任何工具或传递复杂参数前，必须先在终端执行 `python <脚本路径> --help` 确认最新支持的参数标志，严禁凭模糊记忆臆造命令行参数。

### 2.2 核心脚本传参标准与格式防呆

```
+---------------------------------------------------------------------------------------------------+
|                                 核心 CLI 脚本传参规范与防呆拓扑                                    |
+---------------------------------------------------------------------------------------------------+
|  [ preflight.py ]  --> 数据自检 + 道氏高低点 + 关键锚点 (默认 --compact 截断尾部 40 点防爆窗口)  |
|         |                                                                                         |
|  [ swings.py ]     --> 局部极值提取: --k 5/3/1 自适应多尺度; 格式输出: [索引, 日期, 极值类型, 价格] |
|         |                                                                                         |
|  [ key_levels.py ] --> 三类物理锚点: 摆动簇 (Pivots) + 筹码峰 (Clusters) + 道氏分水岭 (Dow)       |
|         |                                                                                         |
|  [ rule_check.py ] --> 冒号三段传参: --wave "标签:起点价:终点价" (支持自适应极值容差)            |
|         |                                                                                         |
|  [ ew_chart.py ]   --> 绘图引擎: --path "标签@索引" (单浪链拓扑连续性 + 端点唯一性校验)           |
+---------------------------------------------------------------------------------------------------+
```

#### 1. `scripts/rule_check.py`：冒号三段格式
调用波浪规则校验脚本时，波浪几何参数必须采用标准的冒号分隔三段格式：
```bash
python scripts/rule_check.py --wave "标签:起点价格:终点价格"
# 示例：验证大级别浪 1 推动
python scripts/rule_check.py --wave "[1]:2635.09:3174.27" --wave "[2]:3174.27:2689.70"
```
- **禁止格式**：严禁写成逗号分隔、空格分隔或以日期代替价格。
- **方向与价位自洽**：起点价格与终点价格必须严格反映行情波动的真实方向（上升浪终点高于起点，下跌浪终点低于起点）。

#### 2. `scripts/ew_chart.py`：单一连续浪链与端点索引映射
- **整数索引对齐**：`scripts/ew_chart.py` 内部基于 K 线数组的整数索引（Index `0` 到 `N-1`）进行几何渲染。
- **`--path` 单一浪链连续性契约**：传入 `--path` 的浪型路径必须是拓扑连续的折线链条。除起点外，每一段子浪的起点必须与前一段子浪的终点严格重合。
- **端点日期唯一性约束**：同一条折线路径中，各节点的日期序列必须单调递增，严禁出现时间回溯或同一日期重复绑定不同价位的矛盾。
- **分层独立出图**：大级别浪（无连字符，如 `(1)`、`[1]`）、第二层子浪（带单连字符，如 `1-1`）、第三层微观子浪（如 `1-1-1`）必须按层级独立配置参数，工具箱已设置硬拒绝门禁，跨层级混放进同一条 `--path` 将直接报错熔断！

#### 3. `scripts/preflight.py`：输出紧凑与全量切换（D40）
- **默认紧凑模式（Compact）**：为防止长周期 K 线数据（如上千根日线）导致 LLM 上下文爆炸，`scripts/preflight.py` 默认仅返回行情摘要、道氏关键高低点结构以及尾部 40 个摆动点（满足 95% 实战数浪场景）。
- **全量参数切换**：当且仅当需要回溯数年以上的历史超大级别母浪划分时，方可显式传入 `--no-compact` 参数拉取全量数据。


---

## 五、多 Agent 协同契约框架（Subagent Brief Frame）

在复杂分析任务中，主协调 Agent（Main Agent）常常需要派发细分子代理（如专门数微观浪的 `wave-3` 或分钟线微观探针）。为保证协同效率与上下文纯净，必须严格遵守以下契约。

### 5.1 子代理输入上下文隔离契约
主 Agent 在生成子代理 Prompt 时，必须将信息严格约束在“任务最小必要集”之内，严禁将全量无关知识库全文灌入子代理。

#### 子代理标准 Prompt 包装结构
```markdown
### 1. 任务背景与分析标的
- 标的名称与代码：[如 科创50 / 1B0688]
- 行情数据切片绝对路径：[必须提供 %TEMP% 下已完成列序重排的标准化 CSV]
- 待细分父浪标签与属性：[如 中浪 (3)，性质：驱动浪，起点与终点已知价格范围]

### 2. 分析时间窗口与极值基准
- 起点时间与价格：[YYYY-MM-DD / P_start]
- 终点时间与价格：[YYYY-MM-DD / P_end]
- 必须强制契合的三类技术锚点：[列出 key_levels 提取的该区间关键 Pivots]

### 3. 工作范围与绝对红线
- 任务：仅提取该父浪内部的次级波浪划分（5 浪或 3 浪）；
- 绝对禁止：子代理不评估大级别方向，不输出最终投资建议，严禁擅自改动父浪的起终点！
```

### 5.2 子代理输出标准结构化格式
子代理完成计算后，必须以结构化 Markdown 表格形式回传结果，严禁返回杂乱的口语化叙述：

```markdown
#### 子浪划分清单（Sub-Wave Breakdown）
| 序号 | 子浪标签 | 起点日期 | 起点价格 | 终点日期 | 终点价格 | 涨跌幅(%) | 浪型性质 | 完成状态 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 3-1 | 2026-02-05 | 802.10 | 2026-02-28 | 895.40 | +11.63% | 推动浪 | 确认完成 |
| 2 | 3-2 | 2026-02-28 | 895.40 | 2026-03-15 | 838.20 | -6.39% | 单锯齿 | 确认完成 |
| 3 | 3-3 | 2026-03-15 | 838.20 | 2026-04-10 | 972.50 | +16.02% | 延长推动 | 确认完成 |
| 4 | 3-4 | 2026-04-10 | 972.50 | 2026-04-25 | 920.00 | -5.40% | 平台形 | 确认完成 |
| 5 | 3-5 | 2026-04-25 | 920.00 | 2026-05-12 | 1015.30| +10.36% | 推动浪 | 确认完成 |

- **内部几何验证**：浪 3 长度 (134.30) > 浪 1 长度 (93.30)，且浪 3 绝非最短浪；浪 4 终点 (920.00) 远离浪 1 顶点 (895.40)，未发生重叠。硬性规则校验 100% 通过。
```

### 5.3 越权裁决防御机制
- **状态冻结**：若子代理在计算微观波浪时发现与父浪既定前提产生冲突（例如发现内部只能数成三浪调整，无法构成五浪推动），**子代理无权自行篡改父级标签**！
- **异常上报**：子代理必须在输出中明确标记 `【结构冲突异常上报】`，将微观矛盾原样回传给主协调 Agent，由主协调 Agent 在更高维度的“多重数浪推演流水线”中统一裁决是否升级替代方案。


---

## 六、候选事实批量入口（wave_facts / target_calc）

### 6.1 一次登记，多处复用

`wave_facts.py --csv <行情CSV> --data <候选JSON> --out <系统临时目录内绝对路径/facts.json>` 一次完成端点取价、层级契约、批量数值规则与双向目标，默认只打印异常摘要。`--format json` 仅在需要完整数据时使用，禁止把完整 JSON 与摘要重复送入上下文；`--scheme <方案名>`／`--path <浪路径>` 只展开局部明细，退出码仍检查全部方案。摘要默认每方案最多列 20 条问题，优先列违反项并披露省略数量；定点展开不截断该局部。

退出码：`0`＝未发现机械违反（仍可能缺证，不等于完整数浪通过）；`1`＝发现违反，须区分 Rule 反例与段数、登记或完成声明问题；`2`＝输入或调用错误。完整结果即使存在违反也写入 `--out`，供定位用；有违反的候选不得直接用于正式交付。

### 6.2 候选 JSON 顶层（version=1）

候选 JSON 与 `facts.json` 均为过程数据，放系统临时目录，不作为新增交付文件进入 `分析输出/`。顶层键：

| 键 | 类型 | 约束 |
| :--- | :--- | :--- |
| `version` | int | 必须为 `1` |
| `as_of` | string | 必填，信息截止日 `YYYY-MM-DD`；只使用该日及以前的数据 |
| `depth` | int | `3` 或 `4`；`2` 仅兼容旧局部机械输入，不能进入新报告。省略按 `3` |
| `schemes` | array | 非空；每项含 `name`、`degree`、`groups`，可选 `targets` |
| `analysis_scope` | object | 正式分析必填，见第 7 节；局部调试可省略，但不能直接交付 |

方案 `name` 非空且唯一，`degree` 非空。`analysis_scope` 是候选 JSON 的顶层键，不是方案内的键。

### 6.3 分组与端点

每组（`groups[]`）字段：

| 字段 | 类型 | 约束 |
| :--- | :--- | :--- |
| `path` | string | 根组为 `""`，子组为父浪路径如 `1`、`1-3`；不得重复，必须包含根组；组路径最多三层，端点可到第四层 |
| `pattern` | string | `impulse`／`diagonal`／`motive` → 1–5；`zigzag`／`flat` → A/B/C；`triangle` → A–E；`double_combination` → W/X/Y；`triple_combination` → W/X/Y/X2/Z；`unknown` 仅保留事实与缺证 |
| `completed` | bool | 必填；组完成声明是输入前提，不替代内部结构核验 |
| `k` | int | 正整数，省略按 `3`；各层可不同，但须与实际摆动事实一致 |
| `points` | array | 至少起点与一个终点，按时间顺序 |

每个端点 `points[]`：`label`（字符串；起点固定 `"0"`，其后按形态标签递增）、`index`（整数，`0` 起，指向原始 CSV 数据行）、`kind`（`H`／`L`）。**禁止填 `price`**，价格一律由 CSV 的 high/low 提取。第 2 个点起必须显式声明 `completed` 布尔值。三重联合的第二个 X 用 `X2` 作内部唯一标识，绘图显示仍为 `X`。

端点契约：索引递增、H/L 交替、浪长非零；子组起点须等于父浪起点，已完成子组终点须与父浪终点闭合。进行中组允许正确组成前缀，不能跳段或虚填尚未形成的末段。

```json
{
  "version": 1,
  "as_of": "2026-11-06",
  "depth": 3,
  "schemes": [{
    "name": "主方案",
    "degree": "Minor",
    "groups": [{
      "path": "", "pattern": "impulse", "completed": true, "k": 3,
      "points": [
        {"label": "0", "index": 10, "kind": "L"},
        {"label": "1", "index": 24, "kind": "H", "completed": true},
        {"label": "2", "index": 31, "kind": "L", "completed": true},
        {"label": "3", "index": 48, "kind": "H", "completed": true},
        {"label": "4", "index": 55, "kind": "L", "completed": true},
        {"label": "5", "index": 72, "kind": "H", "completed": true}
      ]
    }]
  }]
}
```

### 6.4 完成状态与内部证据

每个浪终点可登记：

```json
{
  "label": "3", "index": 48, "kind": "H", "completed": true,
  "completion_status": "completion_candidate",
  "completion_basis": "端点后已有反向推进；内部五浪尚待独立核验",
  "internal_structure": {"status": "pending", "basis": "仅检查到 k=3 摆动，未完成组成核验"},
  "parent_identity": {"status": "pending", "basis": "父浪级别尚待跨层对照"},
  "depends_on": {"path": "1-2", "basis": "前浪完成假设", "withdrawal": "前浪起点被击穿即撤销"}
}
```

- `completion_status` ∈ `completion_candidate`（完成候选）／`confirmed_complete`（确认完成）／`in_progress`（进行中）／`start_candidate`（启动候选）。
- `completed` 必须与状态一致：前两者为 `true`，后两者为 `false`。
- `completion_basis` 必填；`internal_structure` 与 `parent_identity` 各为 `{status, basis}`，`status` ∈ `supported`／`pending`／`conflict`。
- `confirmed_complete` 要求价格拐点已确认且上述两项均为 `supported`；`start_candidate` 必须登记 `depends_on` 的前浪路径、假设与撤销条件。

### 6.5 目标登记

`targets[]` 的 `base` 与 `anchor` 必须引用本方案已登记的浪路径；`anchor` 取该浪终点：

```json
"targets": [
  {"base": "1", "kind": "retracement", "ratios": [0.382, 0.5, 0.618]},
  {"base": "1", "kind": "projection", "anchor": "2", "direction": "up", "ratios": [1, 1.618]}
]
```

回撤不另设 `anchor`／`direction`，方向由基准推导；投射必须显式 `up`／`down`。只需独立计算时不跑 `wave_facts`，用 `target_calc.py --start <基准起价> --end <基准止价> --kind retracement`；投射另传 `--anchor <起算价> --direction up/down`，倍率用重复 `--ratio`。计算用线性价差，原始结果不舍入；摘要仅格式化显示，不用于边界判断。

### 6.6 输出与调用边界

完整结果含：截止日内行情指纹、各浪端点／价差长度／端点序号差／前浪长度比、各层机械检查、条件目标、已确认且声明完成段的实线绘图参数。每浪另有 `segment_extrema`（候选起止区间真实 high/low）与 `inspection`（观察区间、真实极值、k=5→3→1 各窗口实际摆动）。

未完成浪的观察区间延伸到行情截止日，不只停在暂定止点；完成浪扫描固定历史区间。分形先用完整截止序列计算再过滤到区间；不存在拐点时输出空数组，不编造。端点范围外出现极值只登记「区间极值复核」，不自动判 Rule 违反。普通推动复用 `rule_check` 数值接口；斜纹浪不套用重叠禁令。扫描事实不自动决定浪级、形态或完成状态。

`--out` 只允许系统临时目录内的绝对路径，且不得覆盖输入文件。行情、截止日、`k`、形态或端点改变时必须重算，不凭旧结果沿用通过状态。


---

## 七、分析尺度与逐浪覆盖契约（analysis_scope，D41）

### 7.1 候选输入与顶层字段

正式分析在候选 JSON 顶层增加 `analysis_scope`；`wave_facts` 用截止日内 CSV 生成 `waves`、`extra_checks` 与版本号，并立即校验。候选侧只提供框架解释与缺证登记，不手工填扫描事实。

顶层字段（输出固定为 `version=3`，输入不必提供）：

| 字段 | 类型 | 约束 |
| :--- | :--- | :--- |
| `version` | int | 固定 `3`（`analysis_scope.SCOPE_VERSION`）；旧报告状态可提取，正式渲染须用 CSV 重建 |
| `delivery_depth` | int | `3` 或 `4`，须与报告细分深度一致 |
| `inspection_depth` | int | 实际端点登记深度 `1–4`；必须等于覆盖记录最深层，不得虚报 |
| `profile` | string | `daily-year-month-day`（默认）或 `user-defined`；后者须 `source=user-request` 并填 `scope_basis` |
| `data_start` / `data_end` | string | CSV 实际起止日，`data_start < data_end` |
| `history_review` | string | 历史扫描说明：查过哪些区间、主要高低点与缺口 |
| `schemes` | array | 与候选方案逐一对应，不得重复或遗漏 |

候选侧实际输入：`profile`、`history_review`、`schemes`；其余字段由脚本生成。第一层框架至截止日不足 365 个自然日时，每个方案还须填 `short_scope_reason`（为何较早结构未能支持年尺度框架）与 `supplement`（补证要求）。365 日只是披露阈值，不是波浪 Rule。

### 7.2 方案元数据

每个 `schemes[]` 条目：

| 字段 | 约束 |
| :--- | :--- |
| `name` | 与候选 JSON 的方案名一致 |
| `framework_start` | 第一层首浪起点，须等于 `waves` 中第一条第一层浪的 `start` |
| `basis` | 第一层候选框架依据（前序结构与当前父级位置） |
| `review_condition` | 哪些新增结构会使框架重新评估 |
| `current_parent` | 当前第一层父浪路径，须为已登记的第一层浪 |
| `current_path` | 可选；当前浪实际路径，默认等于 `current_parent`，须在该父浪内已登记 |
| `fourth_layer_roots` | 交付 4 层必填：默认当前活跃第三层父浪；全树须列全部第三层父浪；空数组无效 |
| `position_candidates` | 可选；当前浪竞争解释数组，每项含 `path`、`status`（`candidate`／`supported`／`withdrawn`）、`basis`、`missing`、`withdrawal` |

`gaps[]` 是**候选输入专用**字段，逐项登记未展开或仅部分展开、且尚未到最深层的父浪：`path`、`state`（只允许 `in_progress`／`unresolved`）、`evidence`、`needed`、`review`。`wave_facts` 生成覆盖记录时会把它转换成 `waves` 的 `state`／`evidence`／`needed`／`review`，不会原样留在正式对象里。父浪已完整展开且子组首尾闭合时可不出现在 `gaps`；`gaps` 不得引用不存在或已到最深层的路径。

```json
{
  "profile": "daily-year-month-day",
  "history_review": "已扫描全部可得历史的主要高低点；列具体日期、结构依据及前序资料缺口",
  "schemes": [{
    "name": "主方案",
    "framework_start": "2024-09-24",
    "current_parent": "3",
    "current_path": "3-1",
    "basis": "第一层候选框架依据，列前序结构和当前父级位置",
    "review_condition": "哪些新增结构或补齐历史将使框架重新评估",
    "gaps": [{
      "path": "3-1", "state": "unresolved",
      "evidence": "该父浪日线已检查哪些 k 窗口及实际结构问题",
      "needed": "补该历史区间更细数据或重数父级；必须替换成真实检查",
      "review": {
        "reason": "resolution",
        "windows": [
          {"k": 5, "finding": "列该窗口真实价日与拐点不足的位置"},
          {"k": 3, "finding": "列缩小窗口新增的价日、候选组成及冲突"},
          {"k": 1, "finding": "列最细日线检查结果、规则反例或剩余分辨率限制"}
        ],
        "next_action": "finer_data"
      }
    }]
  }]
}
```

`review.reason` ∈ `ambiguity`（多种具体数法，另列至少两种 `alternatives`）／`resolution`（日线分辨率不足）／`structure_conflict`（结构反例待重数）／`ongoing`（实际进行中）；`next_action` ∈ `recount`（重数父级）／`finer_data`（补更细数据）／`wait`（等待后续）。`wait` 只用于 `ongoing`；已完成历史浪禁止 `wait`／`ongoing`／`in_progress`。

### 7.3 逐浪覆盖记录

`waves[]` 每项：

| 字段 | 约束 |
| :--- | :--- |
| `path` | 单层或父子路径，如 `1`、`1-1`、`2-A`；不得重复 |
| `start` / `end` | `YYYY-MM-DD`，须在第一层框架内且 `start < end` |
| `state` | `expanded`（子组已登记完成且闭合）／`in_progress`（部分展开／进行中）／`unresolved`（具体缺证／多解）／`leaf`（交付最深层）；`leaf` 只用于最深层 |
| `completed` / `confirmed` | 均为布尔值；`completed` 是分析者的完成声明，`confirmed` 只表示价格拐点已有后续反向摆动 |
| `completion_status` / `completion_basis` | 同第 6.4 节；`completed` 与状态必须一致 |
| `internal_structure` / `parent_identity` | 各为 `{status, basis}`，`status` ∈ `supported`／`pending`／`conflict` |
| `depends_on` | `start_candidate` 必填：前浪路径、假设、撤销条件 |
| `start_price` / `end_price` | 有限数值，取 CSV 含影线极值 |
| `inspection` | 实际扫描事实：`start`、`end`、`extrema`、`windows` |
| `evidence` | 非空；该浪的端点与结构依据 |
| `needed` | `in_progress`／`unresolved` 必填：补证或复核要求 |
| `review` | `in_progress`／`unresolved` 必填：`reason`、`windows`、`next_action` |

`inspection` 契约：

- `start` 等于该浪 `start`；`end` 在完成浪等于 `end`，在未完成浪等于 `data_end`（观察截止不等于浪终点）。
- `windows` 必须按 `k=5`、`3`、`1` 顺序登记三段实际摆动：`{k, pivots:[{index, date, price, kind}]}`；无拐点时为空数组。
- `extrema` 含区间真实 `high` 与 `low`：`{date, price}`，且 `high.price >= low.price`。

`review` 契约：

- `windows` 必须按 `k=5`、`3`、`1` 顺序逐项写 `finding`，只写「尚未形成唯一序列」不构成检查。
- `ambiguity` 须列至少两种 `alternatives`；`resolution` 须说明具体分辨率限制。
- 已走完父浪跨度 ≥15 根日 K（或日历 ≥30 天）时，禁止以 `resolution` 逃避细分，必须展开子浪。

`expanded` 要求：子浪非空、首尾与父浪闭合、全部子浪 `completed=true`。父子与同层区间必须连续，子浪不得越出父浪。

### 7.4 四层与额外检查

- `inspection_depth` 是实际登记到的最深层，必须与 `waves + extra_checks` 的最大路径深度一致。
- 交付 4 层时，只有 `fourth_layer_roots` 指定的分支要求第 4 层；其余分支仍停在 3 层。落在要求深度之外的内部检查对象放入 `extra_checks`（结构同 `waves`），不得混入正式覆盖层。
- 四层分支路径必须已登记，且层数不超过第三层；默认取当前活跃第三层父浪，用户要求全树时才列全部第三层父浪。

### 7.5 报告与图表绑定

- `wave_facts` 生成的 `analysis_scope` 原样并入报告 `data.json`；两个报告生成器从同一对象渲染 `{{分析尺度与覆盖}}`，不得手工改短框架、极值或删除不便解释的父浪。
- 正式全景图必须传 `--scope-file <归档>/临时文件/data.json`；`--start` 等于 `framework_start`，禁止 `--last` 裁掉长期框架；所有已采用历史段（含完成候选）的层级端点须进入对应层 `--path`。未完成段由 scope 自动派生虚线，不得手画未来终点。
- 逐浪表分别显示候选价日、观察区间、摆动确认、完成声明、细分状态、真实极值与窗口检查，不合并成「未形成浪」。