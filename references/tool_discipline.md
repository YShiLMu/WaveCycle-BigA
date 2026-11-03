> **打包说明**：本文件由 `01_知识库_knowledge/19_执行纪律_tool_discipline.md` 转换生成（仅编号与路径口径不同），**禁止直接修改，修改请改源**；维护性章节不打包，完整版见源文件。
>

# 执行纪律与工具使用（Tool Discipline）——防呆操作规范

> **定位**：把"分析者在调用脚本 / 处理数据时容易踩的坑"固化成明文纪律。本文件只讲**怎么调、怎么判断、怎么防呆**，不定义波浪规则（那是 `references/rules.md` / `references/guidelines.md`）与数据获取协议（那是 `references/data.md`）。
>
>
> **总原则**：能用已入库脚本就别写临时脚本；能数值校验就别肉眼比对；**参数格式以第 2 节「参数快照」为准**，按表调用报错时才跑 `--help` 或读源码（`--help` 仍为最终权威）。

## 1. 数据与列序（最高优先级——一次错、全错）

- 落盘 CSV 前**强制按契约列序重排**：`df = df[["date", "open", "high", "low", "close"]]`，不依赖数据源原生列序（腾讯 `fqkline` / 港股 / 美股返回 `date,open,close,high,low`——**close 在 high 之前**，与契约相反）。
- **契约列序 = `date,open,high,low,close`**；`data_check.py` 的表头契约校验的是"**列名序列精确匹配**"（D28）：**列序错位判"不通过"并整体退出码 1**，禁止带病数浪——绝不能让"按列名读的自检通过、而按位置读的 swings 静默错读"。
- 数据基准【1 分析前提】必须披露三项：**复权方式 + 数据源 + 截至时间**（见 `references/data.md` 第 2 节）。

## 2. CLI 调用纪律（先读 `--help` / 源码，再调用）

- 新脚本**第一次调用前先 `--help` 或读 `parse_*` 源码**，确认参数格式，不要凭记忆猜（记忆最不可靠）。
- `rule_check.py --wave` = **action=append、冒号三段 `标签:起点价:终点价`**（勿用 `@` 或空格分隔）；`--dir up/down` 缺省按第 1 浪起点→终点自动镜像。
- `ew_chart.py`：`--waves` 只认**整数索引**；`--start` 才认**日期 或 整数索引**；`--path` 用 `标签@索引` 或 `标签:索引:索引…`；同名参数可多次传。
- **一条 `--path` = 一个连续浪链**：不同大级别 / 层级浪要拆分多条 `--path` 传；**同一条浪链内各子浪端点日期必须唯一**（重复日期会被 swings 明确报错）。
- `swings.py`：`--path "标签@日期,…"` 把日期转成索引串（须为 swings 含影线极值，R20）；首点即起画点；给 `ew_chart --path` 用。
- `preflight.py` 默认 compact（D40）：swings 只打最近 40 个摆动点、key_levels 前高/前低簇封顶 30 条，省略行数见输出披露行；要全量时显式 `--no-compact`（或 `--tail 0` / `--key-levels-args "--max-levels 0"`），**不要凭记忆假设输出是全量**。

### 2.1 参数快照（build 自动生成，禁止手改）

> 下列参数名由 build 从各脚本 `--help` 自动抓取（防漂移）；**取值格式与含义见各脚本 `--help`**，第 2 节已列出最易错的几条。

<!-- CLI-PARAM-TABLE-BEGIN -->
- **`ew_chart.py`**：`-h` `--csv` `--out` `--out-auto` `--title` `--waves` `--invalid` `--level` `--current` `--fib` `--last` `--start` `--gann` `--gann-auto-scale` `--gann-index` `--font-scale` `--theme` `--path` `--channel` `--pivot` `--scope-file` `--scheme`
- **`swings.py`**：`-h` `--csv` `--k` `--start` `--end` `--weekly` `--chart-args` `--tail` `--path` `--dow` `--fib`
- **`key_levels.py`**：`-h` `--start` `--end` `--csv` `--shadow-ratio` `--trend-threshold` `--window` `--swing-k` `--cluster-tolerance` `--recent` `--gap-band` `--max-levels`
- **`preflight.py`**：`-h` `--csv` `--source` `--fq` `--metadata` `--require-metadata` `--k` `--start` `--end` `--weekly` `--tail` `--no-dow` `--no-key-levels` `--key-levels-args` `--compact` `--no-compact`
- **`rule_check.py`**：`-h` `--wave` `--dir`
- **`score.py`**：`-h` `--scheme`
- **`wave_facts.py`**：`-h` `--csv` `--data` `--out` `--format` `--scheme` `--path`
- **`target_calc.py`**：`-h` `--start` `--end` `--kind` `--anchor` `--direction` `--ratio` `--format`
- **`minute_slice.py`**：`-h` `--code` `--freq` `--anchor-date` `--anchor-ts` `--anchor-kind` `--daily-csv` `--k` `--out-dir`
<!-- CLI-PARAM-TABLE-END -->

## 3. 输出读取纪律

- `gen_report_md.py` / `gen_report_web.py` 的 `[OK]/[NEXT]` 提示**走 stderr**；重定向只捕获 stdout（`> 文件名`），**勿加 `2>&1`**（会把日志混进交付文档第一行）。
- 长输出（`swings` / `key_levels` 的摆动点全表）定位关键字用 **`tail` / `grep -A`**，勿用 `head` 盲截（path 转换串在输出末尾）。
- `rule_check.py` 退出码 **1 = 存在"违反"**，须按 R19 判方案失效；脚本只输出数值事实，形态类规则由模型核对。

## 4. 防呆与单一来源

- **时间戳单一来源**：用 `init_archive.py --print-stamp` / `--print-dir` 回显取值，**勿再 `date` 两次**；保证 `data.json.时间戳 == 文件夹名时间戳 == 报告文件名时间戳` 三处一致。
- 浪端点取 `swings` **含影线极端价位**（R20），禁止用收盘价替代；斐波比率**现算**，禁止心算。
- 浪型图 PNG **出图后必须目检**（浪段标注、分析级别、失效价位红虚线、中文渲染、主备不混叠）。
- **别自写临时取数 / 探测脚本**；必须自写时先按 §1 列序重排，且对关键结果交叉校验后再用。

## 5. 环境与依赖（首次 / 换机）

- 首次或换机后跑 `smoke_test.py` 验证 pandas / matplotlib / 中文字体可用。
- **中文字体探测的正确写法**（勿用 `set.update(字符串)`——那会把字符串拆成单字符，导致永远 miss）：
  ```python
  from matplotlib import font_manager
  names = {f.name for f in font_manager.fontManager.ttflist}
  ok = "Microsoft YaHei" in names
  ```

## 6. 数浪出图呈现规范（浪级配色与进行中段）

- **第一层（大级别）线 = 白色**：大级别浪（1-2-3-4-5、A-B-C）用 `ew_chart.py --path` **无连字符**标签（如 `1`、`2`、`A`）绘制，呈白色。
- **第二层（子浪）线 = 绿/青**：子浪细分用 `--path` **带连字符**标签（如 `1-1`、`2-a`）绘制，呈绿/青。
- **第三层线 = 橙色；第四层线 = 黄绿色**：默认深色图第四层用亮黄绿 `#B8F000`，浅色图用深黄绿 `#4D7C0F`；第四层实线、未完成虚线、箭头与图例共用独立层级色，不复用K线颜色。
- **`--waves` 不作白/绿分层**：此参数仅用于无scope的工具调试，其up/down方向色（青／蓝）不承担首层白／次层绿约定；正式图各层一律用已绑定scope的`--path`，已采用历史段实线；未完成段由scope生成层级色虚线。
- **候选与进行中段画法**：方案采用的历史段（含完成候选）实线；启动候选与进行中段用层级色虚线。线型不代表完成或归属确认，证据状态另留Markdown。未完成仅列观察点与截止日，禁止预标未发生的第4/5子浪或完整内部结构（references/rules.md R34、09 D39）。
- **分钟图型（60m/30m/15m，分钟分形层）**：用 `ew_chart.py --out-auto "<图表目录>|<方案>|60m"`（图型∈{全景,60m,30m,15m}，naming.py 为命名权威）出图；**分钟图型免 `--scope-file`（分钟层不进 analysis_scope），浪标签用 `--path`，端点索引来自 `minute_slice.py` 分钟切片 CSV 上 `swings.py` 的摆动点定位**；全景图型仍强制绑定 scope。分钟图组与日线全景同组交付（标准 8 张/防御 4 张/未启用分钟层 2 张，缺张 embed 判错），未启用分钟分形层时分钟图位由 embed 替换为降级说明。

## 7. 候选事实批量入口（wave_facts / target_calc）

### 7.1 一次登记，多处复用

`wave_facts.py --csv <行情CSV> --data <候选JSON> --out <系统临时目录内绝对路径/facts.json>` 默认只打印异常与缺证摘要；完整结果供脚本读取。`--format json`只在需要完整数据时使用，禁止把完整JSON和摘要重复加载。`--scheme <方案名> --path <浪路径>`展开局部明细，退出码仍检查全部方案。默认每方案最多列20条问题，优先列违反项并披露省略数量；按路径展开时不截断该局部。

候选JSON顶层键：`version:1`、`as_of:"YYYY-MM-DD"`（信息截止日）、`depth:3或4`、`schemes:[...]`；`depth:2`仅兼容旧局部机械输入，不能进入新正式报告。每个方案含`name`、`degree`、`groups`及可选`targets`。这里的depth只检查已选深度的覆盖，不替代D37/R35的用户确认与来源登记。

每组含：`path`（根组为空串，子组为父浪路径如`1`、`1-3`）、`pattern`、`completed`（明确布尔值）、`k`（正整数，省略为3）、`points`（按时间顺序）。每点含`label`、`index`、`kind`（H/L）；起点标签固定`0`，后续每个浪终点还须明确`completed`。索引从0起，指向原CSV数据行；不填price，脚本取high/low。各层可使用不同k，但须登记；端点确认只使用截止日内数据，不用后来数据回填。

支持的pattern及直接组成：`impulse`／`diagonal`→1–5；`zigzag`／`flat`→A/B/C；`triangle`→A–E；`double_combination`→W/X/Y；`triple_combination`→W/X/Y/X2/Z。X2仅是第二个X的内部唯一标识，绘图参数显示为X；不能把这个标识当作新增形态。`unknown`仅保留事实与缺证。进行中组允许正确的组成前缀，不能跳段或虚填尚未形成的末段。完成声明是输入前提，摆动确认不等于内部结构完成。

以下只示意根组和目标登记；实际应补齐各父浪的下一层组，并使用真实摆动索引：

```json
{
  "version": 1,
  "as_of": "2026-02-06",
  "depth": 3,
  "schemes": [{
    "name": "主方案", "degree": "Minor",
    "groups": [{
      "path": "", "pattern": "impulse", "completed": true, "k": 1,
      "points": [
        {"label": "0", "index": 1, "kind": "L"},
        {"label": "1", "index": 11, "kind": "H", "completed": true},
        {"label": "2", "index": 15, "kind": "L", "completed": true},
        {"label": "3", "index": 19, "kind": "H", "completed": true},
        {"label": "4", "index": 23, "kind": "L", "completed": true},
        {"label": "5", "index": 27, "kind": "H", "completed": true}
      ]
    }],
    "targets": [
      {"base": "1", "kind": "retracement", "ratios": [0.382, 0.5, 0.618]},
      {"base": "1", "kind": "projection", "anchor": "2", "direction": "up", "ratios": [1, 1.618]}
    ]
  }]
}
```

新增子组`path:"1"`时，points起点须与根组第1浪起点一致；已完成子组终点须与该父浪终点闭合。其直接子浪自动获得`1-1`等路径。targets的base和anchor必须引用本方案存在的浪路径；anchor取该浪终点。回撤不另设anchor/direction，方向从基准推导；投射必须明确up/down。

### 7.2 输出边界与调用纪律

完整结果含截止日内行情指纹、各浪端点／价差长度／端点序号差／前浪长度比、各层机械检查、条件目标、方案已采用历史段（completed=true）的实线绘图参数。每浪另有segment_extrema（候选起止区间真实high/low）和inspection（观察区间、真实极值、k=5→3→1各窗口实际摆动）。已声明完成的浪扫描固定历史区间；未完成浪扫描至行情末日，不能停在暂定止点。分形先用完整截止序列计算再过滤到区间，起止锚点另保留；不存在拐点时输出空数组，不编造。端点范围外极值列“区间极值复核”，要求重查端点／简单调整／组合结构，合法越界另解释，不自动判Rule违反。普通推动复用rule_check数值接口；楔形不套R7。扫描事实不自动决定浪级、形态或完成状态。

退出码0=未发现机械违反，仍可有“待核对／待确认”；1=发现违反，须看rule和basis区分Rule反例与段数、登记或完成声明问题；2=输入或调用错误。完整结果即使有违反也会保存，供定位；不得将有违反的候选参数直接用于正式交付。图形参数按连续历史采用区间拆链，未完成段另按R34处理；图标题、失效线、深度来源、PNG目检仍遵守原流程。评分及报告表格的自动衔接不在本批范围内。

只需独立计算时用`target_calc.py --start <基准起价> --end <基准止价> --kind retracement`；投射另传`--anchor <起算价> --direction up/down`，倍率用重复`--ratio`。计算用线性价差，原始结果不舍入；摘要仅格式化显示，不用于边界判断。目标合法范围、共振去重、适用位置和时间比率仍按08文件核对。

候选JSON和facts.json均为过程数据，放系统临时目录；不能作为新增交付文件进入分析输出。后续取价与计算复用同一结果，不重新手抄端点。行情、截止日、k、形态或端点改变时重新计算，不凭旧结果沿用通过状态。

## 8. 分析尺度与逐浪覆盖契约（analysis_scope，D41）

### 8.1 候选输入：只补框架解释与缺证

日线默认先扫描多年历史，第一层年尺度→第二层月尺度→第三层日尺度；时间尺度仅为项目观察约定，不能据时间自动命名浪级或否定短促子浪。D37仍决定2/3层及确认来源，已明确的用户答复直接复用。其他观察尺度仅用户明确要求时设置profile=user-defined、source=user-request，并填scope_basis；不能为了绕开长期框架而自行选择。

正式分析在第7节候选JSON顶层增加以下analysis_scope元数据。此例仅示意字段，日期和解释必须替换为当次证据；主备各登记一项，不固定第一层起点为案例答案：

```json
{
  "profile": "daily-year-month-day",
  "history_review": "已扫描全部可得历史的主要高低点；列具体日期、结构依据及前序资料缺口",
  "schemes": [{
    "name": "主方案",
    "framework_start": "2024-09-24",
    "current_parent": "3",
    "basis": "第一层候选框架依据，列前序结构和当前父级位置",
    "review_condition": "哪些新增结构或补齐历史将使框架重新评估",
    "gaps": [{
      "path": "3-1",
      "state": "unresolved",
      "evidence": "该父浪日线已检查哪些k窗口及实际结构问题",
      "needed": "补该历史区间更细数据或重数父级；以下示例必须替换成真实检查",
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

每个未展开或仅部分展开、且尚未到本次最深层的父浪必须各填gaps：path为实际父浪路径，state只允许in_progress（进行中）或unresolved（缺证／多解）。evidence、needed解释实际问题，review.windows须按k=5、3、1逐项列finding，与脚本生成的inspection摆动事实相互核对；仅写“尚未形成唯一序列”不构成检查。review.reason：ambiguity=多种具体数法（另列至少两种alternatives及支持／冲突）、resolution=日线分辨率不足、structure_conflict=结构反例待重数、ongoing=实际进行中。next_action：recount=重数父级、finer_data=补该区间更细数据、wait=等待后续；wait只用于ongoing，completed=true的历史浪禁止wait/ongoing/in_progress。已完成且子组端点闭合可不填gap；未完成子组即使止点重合仍须留具体缺证。gaps不能引用不存在的父浪或最深层浪。

每个方案的framework_start须与其根组起点一致；current_parent须指向真实第一层浪。第一层框架至截止日不足365个自然日，还须填short_scope_reason（为何较早结构未能支持年尺度框架，包括已核验的前序）与supplement（补证或复核要求）。不能只写“候选”“有限历史”。365日是项目覆盖披露阈值，不是波浪Rule，不要求每浪都跨一年。

### 8.2 事实输出与报告输入

wave_facts从截止日内CSV生成analysis_scope的version=3、data_start/data_end及每个方案waves；元数据的gaps转换为逐浪覆盖记录。报告data.json顶层直接使用该完整analysis_scope，不能手工改短框架、极值或删掉不便解释的父浪。候选JSON仍为version=1，两个版本属于不同对象。旧报告状态仍可提取，但正式重新渲染须用CSV重建版本3；局部候选可不传该字段用于调试，不能直接交付。

完整对象保留在临时facts.json，合并到临时报告data.json时由脚本读JSON并复制字段；模型只读取异常摘要和必要的局部明细，不把整个覆盖树重复加载后再手抄。候选端点或截止日改变时重新生成，不能只改报告里的日期。

完整waves每项：path、start/end（实际候选划分价日）、start_price/end_price、completed（候选区间结束声明，不等于确认完成）、confirmed（后续反向摆动确认）、pivot_confirmation（identified/window/confirmed/opposite）、completion_status、completion_basis、internal_structure、parent_identity、depends_on、inspection、state及evidence。内部与父级证据分别为status=supported/pending/conflict和非空basis。completion_status为completion_candidate（completed=true，候选区间已结束）、confirmed_complete（completed=true，转折及内部／父级证据均支持）、in_progress或start_candidate（completed=false）。启动候选depends_on含同组前浪path、basis假设及withdrawal撤销条件，前浪只须候选结束，不能据此升级确认完成。实线用于本方案采用的历史区间（completion_candidate/confirmed_complete且completed=true）；start_candidate/in_progress虚线。不能据线型升级任何证据状态。pattern保存该浪已登记内部组的浪型，component_pattern保存其父组形态；无内部组时细型为unknown，网页只能标方案要求的候选类型。expanded仅表示候选完整子组已登记并闭合；leaf仅表示达到适用交付深度。未完成inspection观察至data_end；候选转折、阶段极值和观察截止分别展示，不显示确定终点。

简明分析说明不再手填端点数组；大级别价日从主方案第一层waves生成，小级别价日从current_parent的直接子浪生成。未完成浪显示“暂定止点，未完成”，已声明完成仍称“完成终点候选”，不给尚未发生的浪日期，不无条件写“最后一个为终点”，不复用大级别日期冒充小级别日期。

Markdown由该对象生成 `{{分析尺度与覆盖}}`，保留历史扫描、第一层框架、摆动确认、扫描事实、依据与补证、当前定位等完整明细。HTML只显示四项分析前提（细分深度、观察截止、道氏、图例）及主备方案四列（浪、起止点、浪型、是否细分）；不展示或折叠放入这些检查明细。网页新占位符为网页分析前提、网页主方案、网页替代方案；两份报告内嵌状态仍保存同一完整对象。内嵌状态保存该对象以供续做。从零重跑独立核验历史，不锁定旧数法；续做若改变框架，在报告第8章列新旧起点与证据。

### 8.3 正式图表绑定

使用 `ew_chart.py --csv <行情CSV> --scope-file <系统临时目录内报告data.json> --start <第一层framework_start> --out-auto "<图表目录>|主方案|全景"` 并传同方案多条逐点标签--path。--out-auto必须提供scope-file；普通--out若用于正式图也必须传scope-file与--scheme。CSV起止及影线价须与scope匹配，追加未来行情按scope截止日截断；--start等于第一层起点，禁止--last裁掉框架。全部方案采用的历史端点须在对应层级--path出现；根组首点0，每个子组首点父路径-0；未完成区间隔断实线时，后续已采用历史段另开同层链，首点0对应该段已登记起点，第一层框架起点0仍须单独保留。正式图不接受另填--waves/--pivot绕开状态；启动候选及进行中段从scope自动派生层级色虚线，并说明暂定止点及观察截止，不画未来终点。

每层单独--path，起点／层级／端点检查只是机械门槛，图表仍须目检。任何缺证都按实际区间登记，不硬补第三层；不把检查记录齐全等同于三层全部确认。

### 8.4 三／四层与额外证据

候选depth默认3、可用4；2仅兼容旧局部机械输入，不能进入新正式报告。正式scope.version=3，delivery_depth与报告3/4一致，inspection_depth为实际登记端点的最大层数（1至4），不把缺证冒充已经达到目标深度。每方案fourth_layer_roots默认空数组=全范围；四层指定分支时填真实第一至第三层父浪路径，其他分支仍按三层覆盖。三层交付必要的第四层检查及四层范围外补证保留在extra_checks，不能静默删除；waves用于交付树，两者合并核对父子关系。局部计算和补细周期不能自动确认整个祖先链。

point可显式登记completion_status与上述证据。未登记新状态时，旧completed=true仅转换为完成候选，同时保留原端点／反向摆动严格检查，不自动获得结构支持；显式completion_candidate允许待确认转折，但须仍符合实际价格规则。confirmed_complete证据不足立即报错。start_candidate必须登记前浪依赖及撤销条件。候选JSON仍version=1；旧REPORT-STATE-v1可恢复，其内部旧scope须重新生成后交付。

当前浪定位可在每方案position_candidates登记对象数组，每项含path、status（candidate／supported／withdrawn）、basis、missing、withdrawal；path必须指向该方案实际浪段。它用于显式比较不同级别解释，不能替代实际结构扫描。当前分支可登记current_path（必须在current_parent内）；不填时只能显示父浪，不能凭最后一个标签推导唯一当前浪。
