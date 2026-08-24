---
name: wavecycle
description: 观复（WaveCycle）· 技术分析融合版——在 Elliott Wave（艾略特波浪理论）数浪之上叠加道氏理论（趋势前提）、江恩理论（时间/价位验证）与蜡烛图（K 线信号确认）交叉验证：声明分析级别、数浪、按 Rule 与 Guideline 校验、给出主备方案与独立失效价位、八因子概率排序与共振状态、输出报告与交易计划。A 股行情可用 a-stock-data 获取，其他市场需用户提供数据或图表。
---

# Elliott Wave 分析（Elliott Wave Analysis）

按 Frost & Prechter《Elliott Wave Principle》的框架分析市场，并以道氏理论（前提层）、江恩理论（验证层）与日本蜡烛图（信号层）交叉验证。四层分层：**道氏管"更大级别方向"（用比目标高一层级的指数判定：个股→大盘+板块、板块→大盘；绝不用道氏判标的自身；大盘标的本身不用道氏），波浪管"标的自身浪型"（结构与数浪），江恩管"什么时候到"（时间与价位验证），蜡烛图管"转折是否确认"（K 线信号）**；优先级铁律：**波浪 Rule > 道氏 > 江恩 ≈ 蜡烛图**（见 `references/rule_conflicts.md`）。先声明级别，再数浪、校验、排序、输出；禁止在正文重新定义术语或规则，唯一权威见 `references/`。

## 1. 输入准备与数据获取

- 分析 A 股：先调用 `a-stock-data` skill 获取指定级别与时间范围的行情（日 K/周 K/月 K 均可），再开始数浪；其他市场：以用户提供的数据或图表为准。
- 标的代码核验：取数前必须锁定代码；用户仅提供名称（未给代码）时，先请用户补充代码再取数；名称有歧义（一名称对应多代码）时不得自行猜测，由用户确认（见 `references/data.md`）。
- 取数协议唯一权威：按 `references/data.md` 执行"函数映射 → 参数默认值 → 统一 CSV 输出 → 降级链"；**协议源文件见 `01_知识库_knowledge/10_数据获取协议_data.md`**，`references/data.md` 由其转换生成（仅编号/路径口径不同），修改必须改源。
- 复权口径（默认目标与可执行路径）：长周期/大级别默认目标后复权（hfq），短中期可前复权（qfq）；mootdx `bars()` 为不复权原始价，无除权除息数据时**不得自行计算 hfq**，自动降级为腾讯 fqkline 前复权并披露 qfq，禁止声称 hfq；报告【1 分析前提】数据基准必须披露复权方式 + 数据源 + 截至时间三项（见 references/data.md 第 2 节）。
- 无论数据来源，先提取**极端价位（含影线）序列**：所有摆动点、失效价位、边界与比率计算一律以含影线的最高/最低价为准，不以收盘价替代（见 references/rules.md R20）。
- 数据不足或无法确认内部子浪时，如实说明并保守处理（见 references/guidelines.md G12），不得编造后续行情。
- **环境自检**：首次使用或更换机器后，运行 `scripts/smoke_test.py` 验证 pandas / matplotlib / 中文字体可用且三个脚本（key_levels / ew_chart / embed_report_images）主流程跑通；自检失败先修环境，再出图与内嵌。

### 1.1 与 a-stock-data 的交接规则（Handoff Rules）

两个 skill 同时触发时，按以下顺序执行，并把 a-stock-data 的读取范围限制到最小：

1. **只读章节清单**：取数时只读 a-stock-data 的「端点路由速查」与「K 线相关章节」——§1.1 `tdx_client()`（`.bars()`）、§1.2 `tencent_quote()`、§1.3 `baidu_kline_with_ma()`、「备用源速查 & 降级策略」K 线行（全历史/分钟）。**禁止整篇加载其 SKILL.md（3000+ 行）**；研报、信号、资金面、新闻、公告、打板、期权、舆情等章节本 skill 不需要，一律不读。
2. **职责边界**：a-stock-data 只管取数与防封（mootdx 库烂尾、BESTIP bug、东财限流、降级实现）；波浪规则（references/rules.md）、校验（references/checklists.md）、概率经验（references/guidelines.md）、报告（assets/）、复权口径与数据自检（references/data.md、references/workflow.md）一律以本 skill 为准；a-stock-data 返回的原始数据不构成任何数浪结论。
3. **触发顺序**：先按 `references/data.md` 取数协议调用 a-stock-data → 取回数据后按本 skill 数据自检清单校验（references/workflow.md 第 1 步「数据自检」）→ 通过后再进入数浪流程；任一自检"不通过"退回重新取数或降级标注，禁止带病数浪。
4. **口径唯一权威**：取数口径（函数映射、参数默认值、CSV 输出契约、复权默认与披露、降级链）以本 skill 的 `references/data.md` 为唯一权威；a-stock-data 只提供数据端点，不定义分析口径。

## 2. 核心约定（必须遵守）

- **分析级别（Degree）优先**：数浪前必须声明分析级别；不谈级别的数浪无效（见 references/rules.md R22；references/terminology.md 1.2.1）。
- **Rule 与 Guideline 严格区分**：Rule 违反即数法无效；Guideline 违反只降概率并说明理由（见 references/rules.md 与 references/guidelines.md 前言）。
- **主备方案**：任何分析必须给出主方案 + 至少一个替代方案，每个方案独立标注失效价位（见 references/rules.md R24）。
- **概率排序有依据**：按八因子评分——Guideline 命中数、结构完整度、斐波那契共振、道氏趋势一致性、江恩价格共振、江恩时间共振、蜡烛图信号、失效价位距离，并标注共振状态（三共振/双共振/单信号/背离）（见 references/guidelines.md G21、G26），不空谈概率。加权总分、排名、共振标签与仓位闸门结论可用 `scripts/score.py` 计算（0–2 分制，权重与闸门口径同 G21/G26/G27）。
- **术语统一**：使用「中文（English）」格式，例如 推动浪（Impulse）、替代方案（Alternate Count）。

## 3. 分析流程（5 步，对应 `references/workflow.md`）

### 第 1 步 分析市场

读取数据 → 判定趋势方向（**道氏口径先行**：按**高一层级指数**（个股→大盘+板块、板块→大盘，见 `references/dow.md`）的高低点结构输出"道氏趋势状态"（牛市/熊市/震荡）+ 指数互证核对，再与波浪结构判定对照）→ 选择并声明分析级别 → 找主要摆动并提取技术分析锚点（关键结构位：前高前低、跳空缺口、多日未破压力/支撑位三类由 `scripts/key_levels.py` 脚本产出；趋势线由模型基于脚本摆动点连线并披露端点——作为数浪与失效价位的锚，见 `references/rules.md` R32）（见 `references/workflow.md` 第 1 步）。道氏状态只做数浪先验倾斜，不否决任何数法。

### 第 2 步 数浪

找主要摆动 → 枚举主备数法 → 逐条执行 Rule Check → 执行 Guideline Check → 标注失效价位 → 概率排序（见 `references/workflow.md` 第 2 步；检查表见 `references/checklists.md`）。

### 第 3 步 验证数浪

结构自洽 → Rule 复核 → Guideline 复核 → 失效价位验证 → 输出完整性检查；**只验证，不修改数法**（见 `references/workflow.md` 第 3 步）。

### 第 4 步 生成报告

按 8 章节结构输出分析报告，复制 `assets/分析报告_report.md` 填写（见 `references/workflow.md` 第 4 步）。
报告与网页归档到 `<项目根目录>/分析输出/<标的名称_代码_YYYYMMDD_HHMM>/`（归档规范见本文第 5 节「输出归档」）。
生成后运行 `scripts/embed_report_images.py <归档文件夹>`，自动把 `图表/` 下 PNG 转 base64 内嵌进 .md 与 .html（md 在查看器不支持 data URI 时可用 `--md-keep-absolute` 回退绝对路径并注明），校验通过才交付（见 `references/workflow.md` 第 4 步第 2.3 节）。
网页报告复制 `assets/网页报告_web_report.html` 模板填充生成（`{{字段}}` 全部替换，图区 4 个图片占位符由 `scripts/embed_report_images.py` 注入 base64），禁止从零重写 HTML；非模板生成判"不通过"（自检硬项见本文第 6 节，字段清单与骨架见本文第 9 节）。

**K 线图 + 浪型标注**：获取行情数据后、报告定稿前，用 `scripts/ew_chart.py` 为主方案与替代方案各绘制**两张图——全景图 + 放大图**（默认共 4 张；极端情况仅 1 个合法方案时防御性输出主方案 2 张，由 `scripts/embed_report_images.py` 2 图模式内嵌、替代方案图区标记不适用；第 3 个方案只文字呈现不出图；禁止主备混叠，见 `references/rules.md` R23）：全景图覆盖完整数据范围（数据起点不得擅自截断，图注标注"起点至最新"），只标注大级别结构（1-2-3-4-5 / A-B-C / W-X-Y）与大级别失效价位；放大图用 `--last N` 截取尾部区间（默认最近 250 根，或按用户指定），标注子浪编号（①②③ 或 i-iii）、支撑/阻力、失效价位与当前价格，建议 `--font-scale 1.2–1.4` 保证子浪标注清晰。图标题含分析级别与时间范围（`references/rules.md` R22）；浪段标注按 R23；失效价位红色虚线并注明规则编号（R19、R20）。图表用高清输出（dpi ≥ 150）。PNG 只用于嵌入交付物，保存后必须验证文件存在且可渲染（自检清单见 `references/workflow.md` 第 4 步第 2.1 节）。

### 第 5 步 更新数浪

失效优先 → 触发条件判定（H1–H4 硬性触发 / S1–S3 软性触发）→ 主备方案状态维护 → 概率重排 → 写入变更日志（见 `references/workflow.md` 第 5 步）。

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
| 工作流细节与交接格式 | `references/workflow.md` |
| 项目默认口径（须披露的量化约定） | `references/defaults.md` |
| A 股数据获取协议（函数映射、默认参数、CSV 契约、降级链） | `references/data.md` |
| 规则冲突与形态边界裁决 | `references/rule_conflicts.md` |
| 道氏理论（趋势方向前提层、DO 信号、指数互证口径） | `references/dow.md` |
| 江恩理论（时间/价位验证层、GN 信号、共振判定） | `references/gann.md` |
| 网页报告输出 | `assets/网页报告_web_report.html` |

> **打包转换约定**：`references/` 与 `assets/` 均由仓库 01–05 源文件转换生成（仅编号与路径口径不同）；维护性章节（转换规则、验收清单等）不打包，打包版文件头注明完整版见源；修改必须改源，禁止直接修改打包版。

## 5. 模板与输出（assets）

**交付物规范（每次分析只交付两个文档）**：

- 归档位置：`<项目根目录>/分析输出/<标的名称_代码_YYYYMMDD_HHMM>/`（`<项目根目录>` 以运行时工作区根目录为准；归档规范见本文第 5 节「输出归档」）；
- **分析报告_<标的>_<代码>_<时间>.md**：按 `assets/分析报告_report.md` 模板输出；交易计划（第 6 章）、失效价位（第 5 章）、更新与跟踪（第 8 章）内容完整并入，不再单独成文件；浪型图由 `scripts/embed_report_images.py` 自动 base64 内嵌（文档自包含）；查看器不支持 data URI 时回退绝对路径引用 `分析输出/<文件夹名>/图表/<PNG>` 并注明（见 references/workflow.md 第 4 步第 2.3 节）；
- **网页报告_<标的>_<代码>_<时间>.html**：复制 `assets/网页报告_web_report.html` **直接填充**生成（所有 `{{字段名}}` 替换为本次分析数据；图区保留 `{{主方案全景图路径}}` 等 4 个图片占位符，由 `scripts/embed_report_images.py` 注入 base64，禁止手工填路径；单方案防御模式时替代方案图区由脚本标记为不适用），禁止从零重写 HTML 结构；
- 两份文档中主备方案、失效价位、概率排序、简洁总结、关键价位表必须一致。

**不再生成**：独立交易计划.md、失效追踪.md、变更日志.md、日线 CSV、独立 PNG——浪型图仅作内嵌素材存于该文件夹 `图表/` 子目录。

- `assets/分析报告_report.md`：第 4 步报告输出时复制填写（**交付文档**）；
- `assets/网页报告_web_report.html`：生成分析报告时，复制该模板，填入数据与简洁总结后交付网页（浪型图占位符由 `scripts/embed_report_images.py` 注入 base64；**交付文档**，含主备方案标签页与末尾总结，见 `references/workflow.md` 第 4 步输出结构）；
- `assets/每日复盘_daily_review.md`、`assets/失效追踪_invalidation.md`、`assets/交易计划_trade_plan.md`：**仅作内部工作底稿**（盘中草稿、跨周期失效跟踪、仓位草稿），产出**不进入 `分析输出/` 归档、不作为交付物**；需要交付的内容分别并入分析报告.md 对应章节（交易计划→第 6 章、失效价位与更新跟踪→第 5/8 章、复盘更新→第 8 章）。

模板不加载进上下文；交付文档复制到归档文件夹填写，工作底稿复制到临时/工作目录填写、不进入 `分析输出/`。

**输出归档（必须遵守）**：所有分析输出统一归档到**当前项目根目录** `分析输出/`（即运行本次分析的工作区根目录，禁止写入技能安装目录或系统目录）。**一次分析 = 一个独立子文件夹**，命名 `标的名称_代码_YYYYMMDD_HHMM`（本地时间 4 位；Windows 文件夹名禁止冒号，如 `科创50_1B0688_20260809_1522`）；文件夹内**只放两个交付文档**（分析报告_*.md 与 网页报告_*.html），浪型图 PNG 仅存于 `图表/` 子目录作内嵌素材；**不生成**原始行情 CSV、独立的失效追踪、交易计划、变更日志文件（内容分别并入报告第 5/6/8 章）。同一标的的后续更新写回原文件夹；确需从头重开时新建带新时间戳的文件夹，并在旧文件夹分析报告.md 第 8 章登记去向。

## 6. 校验与报告规范

- 每个候选数法必须给出 Rule Check 与 Guideline Check 结果表（格式见 `references/checklists.md`）。
- 报告必须声明级别、不混用标注、失效价位精确到具体价位（见 references/rules.md R20、R22、R23）。
- 概率表述用"大概率 / 倾向于 / 通常"，禁止"必然 / 一定 / 绝对"（见 references/guidelines.md 前言）。
- 假设数据必须显著标注；后续走势未发生时如实标注，禁止编造。
- 网页报告必须由模板生成：校验模板头部特征注释（"波浪理论网页报告模板"）与结构标记（`class="pano-img"` 等）齐全、无 `{{字段}}` 残留；非模板生成判不通过。

## 7. 禁止事项

- 禁止把 Guideline 升格为 Rule，或把 Rule 降格为 Guideline；
- 禁止只给单方案；
- 禁止写模糊失效价位（如"附近""左右"）；
- 禁止在正文重新定义术语或规则（唯一权威在 `references/`）。

## 8. 输出结构（简明分析 → 浪型图 → 简洁总结）

**三份输出物关系**：`分析报告.md` 是完整正文——简明分析说明置于第 1 章之前（开篇摘要），浪型图嵌入【2 主方案】【3 替代方案】章节，简洁总结位于全文末尾；`网页报告.html` 是同一内容的快捷查看版（页头 → 简明分析 → 主备方案图标签页 → 简洁总结），不新增分析结论；简明分析说明与简洁总结在每份交付物中各出现一次。

按以下顺序输出，便于快速查看与决策：

1. **简明分析说明（3–5 段以内，禁止长篇展开）**：
   - 标的、周期与声明的分析级别（见 references/rules.md R22）；
   - 主方案与替代方案各用一句话描述（见 references/rules.md R24）；
   - Rule 校验结论：说明哪条规则决定取舍（例如"第 4 子浪与第 1 子浪重叠，违反 R7，故不标普通推动浪，改用楔形假设"）；
   - Guideline 概率排序依据：主备评分、共振状态标签与失效距离（见 references/guidelines.md G21、G26）。
2. **浪型标注图（放在总结之前）**：主方案与替代方案各两张图（全景 + 放大，默认共 4 张；极端情况仅 1 个合法方案时防御性 2 张——主方案全景 + 放大；工作流输出约定，见 references/workflow.md 第 4 步第 2.1 节）；每张图只用 Python（matplotlib）绘制 K 线再叠加浪型标注，保存 PNG 后由 `scripts/embed_report_images.py` 自动转 base64 内嵌进 .md 与 .html（自包含交付；md 在查看器不支持 data URI 时可回退绝对路径；脚本 `scripts/ew_chart.py`；内嵌校验见 references/workflow.md 第 4 步第 2.3 节）；标题含级别与时间范围（见 references/rules.md R22）；浪段标注不混用（见 references/rules.md R23）；每段浪注明形态类型；失效价位红色虚线 + 规则编号（见 references/rules.md R19、R20）；标出支撑/阻力与当前价格。
3. **简洁总结（所有内容最后，≤15 行）**：严格按以下格式，每字段 1–3 句话：

   **标的【代码】（【名称】），截至【日期】收盘【价格】。**

   **核心判断：**【当前处于哪个浪、什么形态、方向倾向】
   **当前关键形态：**【关键结构特征与依据，如子浪重叠、三角形类型】
   **备选方案：**【一句话 + 确认/证伪价位】
   **概率与仓位：**【共振状态标签 + 主备评分与失效距离结论 + 仓位建议（含闸门结果），如"双共振，轻仓试探（2–3 成）"】
   **关键价位：**【上方突破观察：……；下方防守：……】
   **核心方法论启示：**【本次数浪体现的 Rule/Guideline 设计逻辑，一句话】

总结禁止复述完整分析过程，只给结论、关键价位与仓位；概率表述用"大概率/倾向于/通常"，禁止"必然/一定/绝对"（见 references/guidelines.md 前言）。

## 9. 两种使用环境（网页报告生成）

网页报告的唯一合法来源是 `assets/网页报告_web_report.html` 模板；按运行环境分两种生成方式，任一方式都必须保留模板头部特征注释与结构标记。

### 9.1 可读写文件的 Agent（主路径）

复制 `assets/网页报告_web_report.html` 为 `网页报告_<标的>_<代码>_<时间>.html` → 替换全部 `{{字段}}`（清单见 9.3）→ 图区 4 个图片占位符由 `scripts/embed_report_images.py` 注入 base64 → 校验模板头部特征注释与结构标记齐全、无 `{{字段}}` 残留。禁止从零手写 HTML 结构，禁止在非模板文件上填充。

### 9.2 纯对话型 AI（无文件工具）

无文件读写能力时，按 9.3「模板字段清单」+ 9.4「最小结构骨架」等价重建同构 HTML，并在输出头部注明"按模板结构等价重建"。重建必须保留：模板头部特征注释（"波浪理论网页报告模板"）、`.tabs`/`.tab-panel` 主备切换、`.viewport` + `.pano-img` 查看器结构、关键价位 table、简洁总结与页脚；交互 JS 可保留模板等价实现（缩放/拖拽/复位），无交互要求时可简化为静态展示并注明。

### 9.3 模板字段清单（与 `assets/网页报告_web_report.html` 一一对应，共 29 个）

- **页面字段（19）**：`{{标的名称}}`、`{{标的代码}}`、`{{分析日期}}`、`{{分析级别}}`、`{{收盘价}}`、`{{核心判断}}`、`{{当前关键形态}}`、`{{备选方案}}`、`{{概率与仓位}}`、`{{数据范围}}`、`{{放大图数据范围}}`、`{{上方突破观察价位}}`、`{{上方突破观察说明}}`、`{{下方防守价位}}`、`{{下方防守说明}}`、`{{纪律止损价位}}`、`{{纪律止损说明}}`、`{{数据来源}}`、`{{生成时间}}`；
- **图区图片占位符（4，由 `scripts/embed_report_images.py` 注入 base64，禁止手工填路径）**：`{{主方案全景图路径}}`、`{{主方案放大图路径}}`、`{{替代方案全景图路径}}`、`{{替代方案放大图路径}}`；
- **简洁总结字段（6）**：`{{总结核心判断}}`、`{{总结当前关键形态}}`、`{{总结备选方案}}`、`{{总结概率与仓位}}`、`{{总结关键价位}}`、`{{总结近期交易计划}}`。

> 注：模板头部注释里的「字段名」只是通用说法（"将全部字段替换为分析数据"），不是可填充字段；实际可填充字段为上列 29 个。

### 9.4 最小结构骨架（≤30 行，精简注释形式）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{标的名称}} · Elliott Wave 分析报告</title>
<!-- 模板头部特征注释：波浪理论网页报告模板（可复用）——重建必须保留 -->
</head>
<body><div class="container">
  <header><h1>{{标的名称}}（{{标的代码}}）· Elliott Wave 分析</h1>
    <div class="meta"><span>{{分析日期}}</span><span>{{分析级别}}</span><span>{{收盘价}}</span></div></header>
  <section><h2>简明分析说明</h2>
    <p>{{核心判断}}</p><p>{{当前关键形态}}</p><p>{{备选方案}}</p><p>{{概率与仓位}}</p></section>
  <section><h2>浪型标注图</h2>
    <div class="tabs"><button class="tab-btn active">主方案</button><button class="tab-btn">替代方案</button></div>
    <div class="tab-panel active">
      <div class="viewport"><img class="pano-img" src="{{主方案全景图路径}}"></div>
      <div class="viewport"><img class="pano-img" src="{{主方案放大图路径}}"></div></div>
    <div class="tab-panel">
      <div class="viewport"><img class="pano-img" src="{{替代方案全景图路径}}"></div>
      <div class="viewport"><img class="pano-img" src="{{替代方案放大图路径}}"></div></div>
  </section>
  <section><h2>关键价位</h2><table>
    <tr><th>类型</th><th>价位</th><th>说明</th></tr>
    <tr><td>上方突破观察</td><td>{{上方突破观察价位}}</td><td>{{上方突破观察说明}}</td></tr>
    <tr><td>下方防守</td><td>{{下方防守价位}}</td><td>{{下方防守说明}}</td></tr>
    <tr><td>纪律止损</td><td>{{纪律止损价位}}</td><td>{{纪律止损说明}}</td></tr></table></section>
  <section class="summary"><h2>简洁总结</h2>
    <p>{{总结核心判断}}</p><p>{{总结当前关键形态}}</p><p>{{总结备选方案}}</p>
    <p>{{总结概率与仓位}}</p><p>{{总结关键价位}}</p><p>{{总结近期交易计划}}</p></section>
  <footer><p>{{数据来源}} ｜ {{生成时间}}</p></footer>
</div></body>
</html>
```

### 9.5 无脚本/无绘图环境（降级交付）

无 Python 运行环境（无法执行 `scripts/` 下脚本）时，本次分析整体降级为**参考级**，并显著披露：

- **浪型图降级**：以"文字结构图 + 价位标注表"呈现（如"1（100→160）→ 2（160→130）→ 3（130→220）…"，价位按极端价位标注，见 references/rules.md R20），并注明"环境受限，未按模板出图，结构仅供示意"；
- **锚点降级**：`scripts/key_levels.py` 无法执行，R32 的脚本产出要求不满足——按 references/defaults.md D27 口径人工提取四类锚点，并在报告【1 分析前提】显著标注"锚点未脚本产出（环境受限），置信度下调"；锚点只作参考，禁止作为唯一失效价位依据；
- **交付降级**：网页报告按 9.2 等价重建；分析报告与网页报告均在头部显著标注降级原因；降级版结论不进交易计划执行仓位（按 references/guidelines.md G27 背离处理，强制观望）。
