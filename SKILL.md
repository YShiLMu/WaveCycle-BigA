---
name: wavecycle
description: 观复（WaveCycle）· 艾略特波浪数浪叠加道氏/江恩/蜡烛图交叉验证：声明级别、主备数浪、失效价位、八因子概率排序、报告与交易计划；A 股用 a-stock-data 取数。
---

# Elliott Wave 分析（Elliott Wave Analysis）

按 Frost & Prechter《Elliott Wave Principle》的框架分析市场，并以道氏理论（前提层）、江恩理论（验证层）与日本蜡烛图（信号层）交叉验证。四层分层：**道氏管"更大级别方向"（用比目标高一层级的指数判定：个股→大盘+板块、板块→大盘；绝不用道氏判标的自身；大盘标的本身不用道氏），波浪管"标的自身浪型"（结构与数浪），江恩管"什么时候到"（时间与价位验证），蜡烛图管"转折是否确认"（K 线信号）**；优先级铁律：**波浪 Rule > 道氏 > 江恩 ≈ 蜡烛图**（见 `references/rule_conflicts.md`）。先声明级别，再数浪、校验、排序、输出；禁止在正文重新定义术语或规则，唯一权威见 `references/`。

## 1. 输入准备与数据获取

- 分析 A 股：先调用 `a-stock-data` skill 获取指定级别与时间范围的行情（日 K/周 K/月 K 均可），再开始数浪；其他市场：以用户提供的数据或图表为准。
- 标的代码核验：取数前必须锁定代码；用户仅提供名称（未给代码）时，先请用户补充代码再取数；名称有歧义（一名称对应多代码）时不得自行猜测，由用户确认（见 `references/data.md`）。
- 取数协议唯一权威：按 `references/data.md` 执行"函数映射 → 参数默认值 → 统一 CSV 输出 → 降级链"；**协议源文件见 `references/data.md`**，`references/data.md` 由其转换生成（仅编号/路径口径不同），修改必须改源。
- 复权口径（默认目标与可执行路径）：长周期/大级别默认目标后复权（hfq），短中期可前复权（qfq）；mootdx `bars()` 为不复权原始价，无除权除息数据时**不得自行计算 hfq**，自动降级为腾讯 fqkline 前复权并披露 qfq，禁止声称 hfq；报告【1 分析前提】数据基准必须披露复权方式 + 数据源 + 截至时间三项（见 references/data.md 第 2 节）。
- 无论数据来源，先提取**极端价位（含影线）序列**：所有摆动点、失效价位、边界与比率计算一律以含影线的最高/最低价为准，不以收盘价替代（见 references/rules.md R20）。
- 数据不足或无法确认内部子浪时，如实说明并保守处理（见 references/guidelines.md G12），不得编造后续行情。
- **环境自检**：首次使用或更换机器后，运行 `scripts/smoke_test.py` 验证 pandas / matplotlib / 中文字体可用且三个脚本（key_levels / ew_chart / embed_report_images）主流程跑通；自检失败先修环境，再出图与内嵌。

### 1.1 与 a-stock-data 的交接规则（Handoff Rules）

两 skill 同时触发时，**只读** a-stock-data 的「端点路由速查」与「K 线相关章节」（§1.1 `tdx_client()`、§1.2 `tencent_quote()`、§1.3 `baidu_kline_with_ma()`、备用源 K 线行），**禁止整篇加载其 SKILL.md（3000+ 行）**；它只管取数与防封，取数口径与全部分析规则（规则/校验/概率/报告/复权/自检）以本 skill 为准，协议见 `references/data.md`，返回的原始数据不构成任何数浪结论。取数后先按 workflow 第 1 步数据自检，不通过即退回重取或降级标注，禁止带病数浪。

## 2. 核心约定（必须遵守）

- **分析级别（Degree）优先**：数浪前必须声明分析级别；不谈级别的数浪无效（见 references/rules.md R22；references/terminology.md 1.2.1）。
- **Rule 与 Guideline 严格区分**：Rule 违反即数法无效；Guideline 违反只降概率并说明理由（见 references/rules.md 与 references/guidelines.md 前言）。
- **主备方案**：任何分析必须给出主方案 + 至少一个替代方案，每个方案独立标注失效价位（见 references/rules.md R24）。
- **概率排序有依据**：按八因子评分——Guideline 命中数、结构完整度、斐波那契共振、道氏趋势一致性、江恩价格共振、江恩时间共振、蜡烛图信号、失效价位距离，并标注共振状态（三共振/双共振/单信号/背离）（见 references/guidelines.md G21、G26），不空谈概率。加权总分、排名、共振标签与仓位闸门结论可用 `scripts/score.py` 计算（0–2 分制，权重与闸门口径同 G21/G26/G27）。
- **术语统一**：使用「中文（English）」格式，例如 推动浪（Impulse）、替代方案（Alternate Count）。

## 3. 分析流程（5 步，对应 `references/workflow.md`）

### 第 1 步 分析市场

读取数据 → **分析前提三件套必跑 `scripts/preflight.py` 单入口**（`--csv/--source/--fq` 一次产出：数据自检表+四要素（D28，data_check 不通过即终止禁止带病数浪）→ 摆动点/行索引+道氏状态读数（D30，3 点判 2 点定+DO4 事实，翻转裁决仍按 D22/DO5 由模型）→ 三类锚点（D27/R32）；也可单独跑 `scripts/data_check.py`、`scripts/swings.py --dow`、`scripts/key_levels.py`）→ 判定趋势方向（**道氏口径先行**：按**高一层级指数**（个股→大盘+板块、板块→大盘，见 `references/dow.md`）的高低点结构输出"道氏趋势状态"（牛市/熊市/震荡）+ 指数互证核对，再与波浪结构判定对照）→ 选择并声明分析级别 → 提取技术分析锚点（前高前低、跳空缺口、多日未破压力/支撑位三类由脚本产出；趋势线由模型基于脚本摆动点连线并披露端点——作为数浪与失效价位的锚，见 `references/rules.md` R32）（见 `references/workflow.md` 第 1 步）。摆动点与 CSV 行索引用 `scripts/swings.py` 产出（分形 Pivot、`--weekly` 周线聚合供道氏判定、`--fib` 斐波比率、`--chart-args` 输出 ew_chart 可粘贴的 `--pivot` 参数串），道氏周线判定与 ew_chart 索引定位均以它为准，禁止手写临时脚本重复计算。道氏状态只做数浪先验倾斜，不否决任何数法。

### 第 2 步 数浪

找主要摆动 → 按**细分深度**（D37/R35）展开：**交互式必询**"全部（3 层）/默认 2 层"并登记来源，**未确认并登记前不得出图/出报告**；非交互式（仅显式批处理/定时/CI）默认 2 层并披露；**硬性下限 ≥ 2 层**（每个大级别浪都要展开第 2 层子浪，禁止裸大级别）；层级用 1-2-3-4-5 / A-B-C / 1-1 / 1-1-1，端点取 swings 含影线极值 R20，深度在报告【1 分析前提】披露（细则见 `references/workflow.md` 第 2 步 2.4b）→ 枚举主备数法 → 逐条执行 Rule Check（**数值规则 R5/R6/R7/R17/R29 必跑 `scripts/rule_check.py`**，端点价取 swings 极端价位，违反退出码 1，见 `references/defaults.md` D31；形态类规则由模型核对）→ 执行 Guideline Check → 标注失效价位 → 概率排序（见 `references/workflow.md` 第 2 步；检查表见 `references/checklists.md`）。

### 第 3 步 验证数浪

结构自洽 → Rule 复核 → Guideline 复核 → 失效价位验证 → 输出完整性检查；**只验证，不修改数法**（见 `references/workflow.md` 第 3 步）。

### 第 4 步 生成报告

按 8 章节结构输出两份交付文档（`分析报告.md` 由 `scripts/gen_report_md.py --data data.json` 渲染、`网页报告.html` 由 `scripts/gen_report_web.py --data data.json` 渲染，模板不进上下文，data.json schema 见本文 §9.3）；归档文件夹与标准文件名由 `scripts/init_archive.py` 创建（命名唯一权威），输出重定向为标准文件名。
报告与网页归档到 `<项目根目录>/分析输出/<标的名称_代码_YYYYMMDD_HHMM>/`（归档规范见本文第 5 节「输出归档」）。
生成后运行 `scripts/embed_report_images.py <归档文件夹>`，自动把 `图表/` 下 PNG 转 base64 内嵌进 .md 与 .html（md 在查看器不支持 data URI 时可用 `--md-keep-absolute` 回退绝对路径并注明），**机械校验须退出码 0，另须 PNG 目检与净文本语义复核**（交付文档内嵌 base64 后达 MB 级，使用 extract_report_state.py --text 避免整读图片数据，见 `references/workflow.md` 第 4 步第 2.3 节）。
网页报告由 `scripts/gen_report_web.py --data data.json` 渲染 `assets/网页报告_web_report.html`（`{{字段}}` 全部替换、表格按列头生成，图区 2 个图片占位符由 `scripts/embed_report_images.py` 注入 base64），禁止从零重写 HTML、禁止手工填占位符；非模板生成判"不通过"（自检硬项见本文第 6 节，字段清单与骨架见本文第 9 节）。

**K 线图 + 浪型标注**：用 `scripts/ew_chart.py` 为每个方案各绘**一张全景图**（默认 2 张；单方案防御 1 张；第 3 方案不出图；禁止主备混叠，R23）；起画点取该方案**最大分析级别**的第 1 浪起点（`--start` 标定，不得取当前操作级别子浪起点），子浪按细分深度用**多条 `--path`** 叠加（默认 2 层须铺满每个大级别浪的第 2 层子浪，禁止裸图），输出用 `--out-auto "<图表目录>|主方案|全景"`；图标题含级别与时间范围（R22）、失效价位红虚线注规则编号（R19/R20）。**完整绘图规范唯一权威见 `references/workflow.md` 第 4 步第 2.1 节**；PNG 保存后解码检查并目检；报告用 extract_report_state.py --text 提取净文本复核，避免整读图片数据。

### 第 5 步 更新数浪

失效优先 → **失效触发判定必跑 `scripts/invalidation_check.py`**（把上一份报告第 5 章失效价位清单与最新 CSV 交给它，输出是否触发/首次触及日/确认窗口状态，禁止重读 CSV 人工比价，见 `references/defaults.md` D29）→ 触发条件判定（H1–H4 硬性触发 / S1–S3 软性触发）→ 主备方案状态维护 → 概率重排 → 写入变更日志（见 `references/workflow.md` 第 5 步）。

### 最小可执行示例（假设数据）

场景：上升趋势第 4 浪位置（假设数据），当前价格 197。

1. 声明级别：日线中浪 Intermediate，第 (4) 浪回调中（见 `references/terminology.md`；references/rules.md R22）；
2. 枚举：主方案"平台形（Flat）"A-B-C 3-3-5 vs 替代"三角形（Triangle）"A-B-C-D-E（见 `references/patterns.md`）；
3. Rule Check：逐条检查 R14（3-3-5）、R28（三变体分类）与 R15/R27（三角形结构与子浪），任一违反即方案失效（见 `references/rules.md`；`references/checklists.md`）；
4. Guideline Check：检查 G1 交替（第 2 浪陡直、第 4 浪横向），命中 +1，只参与排序不裁决合法性（见 `references/guidelines.md`）；
5. 标注失效价位：主方案跌破 C 浪终点后连续 2 根收盘未收回即失效；替代跌破三角形下边界（趋势线）且不回抽即失效——价位按极端价位精确标注（见 references/rules.md R20）；
6. 概率排序：按 Guideline 得分、结构完整度、斐波那契共振、道氏一致性、江恩共振、失效距离计算加权总分并标注共振状态，输出主备排序与升级条件（见 `references/workflow.md` 第 2 步；references/guidelines.md G21、G26）。

## 4. 参考资料导航（按需加载，禁止一次全读）

| 场景 | 读取文件 |
| --- | --- |
| 术语/标注/级别含义 | `references/terminology.md` |
| 合法性判断（Rule） | `references/rules.md` |
| 概率性规律（Guideline） | `references/guidelines.md` |
| 形态识别与常见错误 | `references/patterns.md` |
| 比率目标与共振 | `references/fibonacci.md` |
| 蜡烛图（K 线形态库与信号确认） | `references/candlestick.md` |
| 逐条校验清单（含蜡烛图信号） | `references/checklists.md` |
| 工作流细节与交接格式（按子步读取，行号见 workflow.md 头部目录） | `references/workflow.md` |
| 项目默认口径（须披露的量化约定） | `references/defaults.md` |
| A 股数据获取协议（函数映射、默认参数、CSV 契约、降级链） | `references/data.md` |
| 执行纪律与工具使用（防呆：列序重排/CLI 参数/输出读取/时间戳单一来源） | `references/tool_discipline.md` |
| 规则冲突与形态边界裁决 | `references/rule_conflicts.md` |
| 道氏理论（趋势方向前提层、DO 信号、指数互证口径） | `references/dow.md` |
| 江恩理论（时间/价位验证层、GN 信号、共振判定） | `references/gann.md` |
| 网页报告输出 | 由 `scripts/gen_report_web.py` 读取模板渲染，**AI 不读该模板** |

> **打包转换约定**：`references/` 与 `assets/` 均由仓库 01–05 源文件转换生成（仅编号与路径口径不同）；维护性章节（转换规则、验收清单等）不打包，打包版文件头注明完整版见源；修改必须改源，禁止直接修改打包版。

## 5. 模板与输出（assets）

**每次分析只交付两个文档**：`分析报告_<标的>_<代码>_<时间>.md`（按 `assets/分析报告_report.md` 模板，交易计划/失效价位/更新跟踪分别并入第 6/5/8 章）与 `网页报告_<标的>_<代码>_<时间>.html`（由 `scripts/gen_report_web.py` 渲染 `assets/网页报告_web_report.html`，禁止从零重写）。两份文档的主备方案、失效价位、概率排序、简洁总结、关键价位表必须一致；**不再生成**独立交易计划/失效追踪/变更日志/日线 CSV/独立 PNG。

**归档（必须遵守）**：统一归档到**当前项目根目录** `分析输出/<标的名称_代码_YYYYMMDD_HHMM>/`（`scripts/init_archive.py` 创建，命名唯一权威；Windows 禁止冒号，如 `科创50_1B0688_20260809_1522`）；文件夹内只放上述两份文档，浪型图 PNG 生成到 `图表/` 子目录、由 `embed_report_images.py` 内嵌 base64，**内嵌后 `图表/` 与 PNG 原图永久保留、禁止清理**；同一标的更新写回原文件夹，确需重开时新建带新时间戳文件夹并在旧报告第 8 章登记去向。

**模板与工作底稿**：`assets/` 下模板一律**不加载进上下文**（由脚本读取）；`每日复盘/失效追踪/交易计划` 三个 md 仅作内部工作底稿，产出不进 `分析输出/`、不作为交付物。

## 6. 校验与报告规范

- 每个候选数法必须给出 Rule Check 与 Guideline Check 结果表（格式见 `references/checklists.md`）。
- 报告必须声明级别、不混用标注、失效价位精确到具体价位（见 references/rules.md R20、R22、R23）。
- 概率表述用"大概率 / 倾向于 / 通常"，禁止"必然 / 一定 / 绝对"（见 references/guidelines.md 前言）。
- 假设数据必须显著标注；后续走势未发生时如实标注，禁止编造。
- 网页报告必须由模板生成：校验模板头部特征注释（"波浪理论网页报告模板"）与结构标记（`class="pano-img"` 等）齐全、无 `{{字段}}` 残留；非模板生成判不通过。
- 交付文档使用 `scripts/extract_report_state.py --text` 提取净文本进行语义复核；机械渲染与图片解码须通过生成器和内嵌脚本校验，PNG 另行目检。更新先恢复内嵌状态，再用 `scripts/invalidation_check.py --from-report --include-structural` 检查失效条件。

## 7. 禁止事项

- 禁止把 Guideline 升格为 Rule，或把 Rule 降格为 Guideline；
- 标准模式禁止只给单方案；单方案防御须披露原因并强制观望；
- 禁止写模糊失效价位（如"附近""左右"）；
- 禁止在正文重新定义术语或规则（唯一权威在 `references/`）。

## 8. 输出结构（简明分析说明 → 浪型图 → 8 章节）

两份交付物同源自一份 `data.json`。按以下顺序组织：

1. **简明分析说明**（唯一摘要，置于第 1 章之前）：由顶层 `简明分析说明` 渲染成 4 行（主方案 / 小级别 / Neely / 总结），**只写主方案**——主备双方案由正文【3 替代方案】承接（R24）；字段见 §9.3。
2. **浪型标注图**：主方案与替代方案各一张全景图（默认 2 张、单方案防御 1 张），由 `ew_chart.py` 绘制、`embed_report_images.py` 内嵌；标注要求见 §3 第 4 步与 R19/R20/R22/R23。
3. **8 章节正文**：分析前提 → 主方案（含数浪表 + Neely 参考）→ 替代方案 → 概率排序与理由 → 失效价位清单 → 交易计划建议 → 风险提示 → 更新与跟踪；全部由同一份 data.json 渲染。

## 9. 两种使用环境（网页报告生成）

网页报告的唯一合法来源是 `assets/网页报告_web_report.html` 模板；正式报告仅由生成器输出，必须保留模板头部特征注释与结构标记。

### 9.1 可读写文件的 Agent（主路径）

用 `scripts/gen_report_web.py --data data.json` 渲染（网页唯一生成入口）：AI 只写 `data.json`（顶层 `fields`+`tables`+`简明分析说明` 结构化纯数据，schema 见本文 §9.3），脚本读 `assets/网页报告_web_report.html` 完成全部 `{{字段}}` 替换、5 张表格生成与简明分析说明渲染后输出到 stdout，**重定向只捕获 stdout（`> 文件名`），切勿加 2>&1**（脚本的 `[OK]/[NEXT]` 提示走 stderr，加 2>&1 会把日志混进交付文档第一行），重定向为 init_archive 打印的标准文件名（**模板不进上下文**）；图区 2 个图片占位符保留给 `scripts/embed_report_images.py` 注入 base64 → 校验模板头部特征注释与结构标记齐全、无 `{{字段}}` 残留（脚本已内置）。禁止从零手写 HTML 结构，禁止在非模板文件上填充，禁止绕过 gen_report_web 手工填占位符。

### 9.2 纯对话型 AI（无文件工具）

无文件读写或无法执行报告生成器时，按 9.4 提供参考级文字解释；不能重建 HTML 后冒充正式模板生成结果。

### 9.3 模板字段清单（与 `assets/网页报告_web_report.html` / `assets/分析报告_report.md` 一一对应，由 report_common.py 校验；data.json 按顶层 `fields`+`tables`+`简明分析说明` 提供）

- **文本字段（13，report_common.py 的 PAGE_FIELDS）**：`{{分析日期}}`、`{{分析级别}}`、`{{收盘价}}`、`{{主方案说明}}`、`{{主方案失效}}`、`{{替代方案}}`、`{{概率说明}}`、`{{概率结论}}`、`{{交易计划}}`、`{{风险提示}}`、`{{更新跟踪}}`、`{{数据来源}}`、`{{生成时间}}`；标题与页头的 `{{标的名称}}`、`{{标的代码}}` 取自 data.json 顶层。
- **简明分析说明（对象，由脚本渲染成 4 行）**：顶层 `简明分析说明` 含 `大级别浪`、`小级别浪`、`neely得分`、`neely强度`、`结论`、`端点:[{价, 日}, …]`（末项=终点）；渲染为「主方案：大级别X浪，价/日→价/日-…（最后一个为终点）／小级别：目前处于…，点位日期和上面一样／Neely：得分…，强度（保留评级正负号，未知写待确认）／总结：目前…」。
- **Neely字段边界**：`neely得分`摘录有依据的功率评级，不是各脚本结果相加；类型／完成方向／压缩对象缺证时写“待确认”，不能填0代替未知。0是中性评级、无固定回撤比例；`neely强度`与参考表说明完成方向、位置、原文条款和观察截止，不并入八因子。
- **表格占位符（5，report_common.py 按 TABLE_FIELDS 列头生成）**：`{{分析前提表}}`、`{{主方案数浪表}}`、`{{neely参考表}}`、`{{八因子表}}`、`{{失效价位表}}`；data.json `tables` 内每表为 `list[dict]`，键与列头一一对应（分析前提→项/内容；主方案数浪→浪/端点/结构/说明；neely参考→脚本/输出/意义；八因子→因子/主方案/替代方案；失效价位→方案/类型(规则失效/结构失效/观察位)/失效价位/方向(break-down/break-up)/规则依据/触发后果——方向列必填，`invalidation_check.py --from-report` 零推断依赖；两个模板 `{{失效价位表}}` 外侧带 `INVALIDATION-TABLE` 锚点，渲染与内嵌时脚本强制校验）。
- **图区图片占位符（2，由 `scripts/embed_report_images.py` 注入 base64，禁止手工填路径）**：`{{主方案全景图路径}}`、`{{替代方案全景图路径}}`。

> 注：模板头部注释里的「字段名/表名」只是通用说法，不是可填充字段；实际可填充字段为上列文本字段(13) + 简明分析说明对象 + 5 个表格占位符 + 2 个图片占位符。

### 9.4 无脚本/无绘图环境（降级交付）

无 Python 运行环境或仅有截图时，仅提供显著标记的“参考级解释”，列出缺失数据和未执行检查，不进入正式报告流水线，不宣称通过 R32/R35，不给执行仓位。待数据与工具齐备后重跑完整流程。

报告输入须填写“报告模式”（标准 / 单方案防御）；防御模式须有“单方案原因”。两个生成器自动内嵌版本化状态；更新先用 `scripts/extract_report_state.py` 恢复结构化输入，并用 `--text` 复核无图片的正文。失效监控需加 `--include-structural` 同时检查结构条件。
