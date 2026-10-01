# -*- coding: utf-8 -*-
"""报告生成共享层——data.json 加载/校验 + 无副作用的通用渲染器。

单一职责：本模块只做「数据准备 + 纯渲染」，不读具体报表模板、不写出报表——
由 gen_report_md.py（分析报告 .md）与 gen_report_web.py（网页报告 .html）两个入口分别调用。

data.json 模式（顶层键）：
    {
      "标的名称": "...", "标的代码": "...", "时间戳": "YYYYMMDD_HHMM",
      "细分深度": 2, "细分深度来源": "用户确认-2层",
      "fields": { <PAGE_FIELDS 中各字符串字段> },
      "tables": { <TABLE_FIELDS> 各表为 list[dict]，键与列头一一对应 },
      "简明分析说明": { "大级别浪": "第4浪", "小级别浪": "第4浪的b浪",
                        "neely得分": 1, "neely强度": "中等",
                        "结论": "偏多" }  # 各层价日及状态从analysis_scope读取，不另填端点
    }
细分深度 2/3 必填；细分深度来源（用户确认-2层/用户确认-3层/非交互默认-2层）必填且与深度匹配
（3 层须匹配用户确认-3层，见 06 R35 / 09 D37）；分析前提表必须含"细分深度来源"行。
正式报告须含analysis_scope（D41），由wave_facts按CSV生成并逐父浪保留缺证。
失效价位表固定列：方案 / 失效价位 / 方向（break-down/break-up，--from-report 零推断依赖）/
规则依据 / 触发后果；两个模板 {{失效价位表}} 外侧带 INVALIDATION-TABLE 锚点
（invalidation_check.py --from-report 抽取依赖，check_invalidation_anchor 校验缺失即报错）。
"""
import json
import os
import re
import sys
import base64
import math

from naming import IMAGE_PLACEHOLDERS, validate_component
from analysis_scope import validate_scope, scope_tables, endpoint_chain

# 文本字段（字符串直接替换占位符）；简明分析说明为独立对象，不在此列
PAGE_FIELDS = [
    "分析日期", "分析级别", "收盘价",
    "主方案说明", "主方案失效", "替代方案",
    "概率说明", "概率结论", "交易计划", "风险提示", "更新跟踪",
    "数据来源", "生成时间",
]
# 简明分析说明仅含解释；各层价日从同一覆盖事实读取。
JIANMING_KEYS = ["大级别浪", "小级别浪", "neely得分", "neely强度", "结论"]
# 表格：表名 → 固定列头
TABLE_FIELDS = {
    "分析前提": ["项", "内容"],
    "主方案数浪": ["浪", "端点", "结构", "说明"],
    "neely参考": ["脚本", "输出", "意义"],
    "八因子": ["因子", "主方案", "替代方案"],
    "失效价位": ["方案", "类型", "失效价位", "方向", "规则依据", "触发后果"],
}

FACTOR_NAMES = ["Guideline 得分", "结构完整度", "斐波那契共振", "道氏一致性",
                "江恩价格共振", "江恩时间共振", "蜡烛图信号", "失效距离"]
STATE_PATTERN = r"<!-- REPORT-STATE-v1:([A-Za-z0-9+/=]+) -->"


def encode_state(data):
    """状态保留在两个交付文档内，跨会话恢复不依赖临时文件。"""
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "\n<!-- REPORT-STATE-v1:%s -->\n" % base64.b64encode(payload).decode("ascii")


def extract_state(text):
    matches = re.findall(STATE_PATTERN, text)
    if len(matches) != 1:
        raise ValueError("报告须含唯一 v1 状态；历史报告请用 --text 恢复正文后补齐输入")
    return json.loads(base64.b64decode(matches[0], validate=True).decode("utf-8"))


def finite_number(value, label):
    try:
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError()
        return float(value)
    except (ValueError, TypeError):
        fail("%s 必须为有限数值" % label)

# 失效价位表锚点（圈定报告第 5 章失效表；invalidation_check.py --from-report 据以抽取。
# 模板 {{失效价位表}} 外侧必须保留：gen_report_md / gen_report_web 渲染前校验模板、
# embed_report_images 交付前校验产出，缺失即报错）
INVALIDATION_ANCHOR_BEGIN = "<!-- INVALIDATION-TABLE-BEGIN -->"
INVALIDATION_ANCHOR_END = "<!-- INVALIDATION-TABLE-END -->"
# 失效价位表"方向"列合法值（--from-report 零推断依赖；观察位行同样须填方向）
INVALIDATION_DIRECTIONS = ("break-down", "break-up")


def check_invalidation_anchor(text, label):
    """校验文本含失效价位表锚点对且 BEGIN 在 END 之前；缺失/乱序即 fail()。"""
    b = text.find(INVALIDATION_ANCHOR_BEGIN)
    e = text.find(INVALIDATION_ANCHOR_END)
    if b < 0 or e < 0 or b > e:
        fail("%s 缺少失效价位表锚点（%s / %s）或顺序错误——模板须在 {{失效价位表}} 外侧保留锚点"
             "（invalidation_check.py --from-report 依赖）"
             % (label, INVALIDATION_ANCHOR_BEGIN, INVALIDATION_ANCHOR_END))

# 细分深度（09 默认口径表 D37 / 06 R35）：默认 2 层，3 层须用户明确要求。data.json 顶层
# "细分深度" 必填（2/3）+ "细分深度来源" 必填且必须匹配（3 层仅用户确认），校验失败即 fail。
SUBDIVISION_DEPTHS = (2, 3)
DEPTH_SOURCES = ("用户确认-2层", "用户确认-3层", "非交互默认-2层")


def fail(msg):
    print("[错误] %s" % msg, file=sys.stderr)
    sys.exit(1)


def load_data(path_or_dash):
    """读取 data.json；'-' 表示从 stdin 读。校验失败 fail()，成功返回顶层 dict。"""
    if path_or_dash == "-":
        try:
            data = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            fail("stdin JSON 解析失败: %s" % e)
    else:
        if not os.path.isfile(path_or_dash):
            fail("数据文件不存在: %s" % path_or_dash)
        with open(path_or_dash, encoding="utf-8-sig") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                fail("data.json 解析失败: %s" % e)
    if not isinstance(data, dict):
        fail("data.json 顶层应为 JSON 对象")
    return data


def validate(data):
    """校验 data.json 并返回 (名称, 代码, 时间戳)；失败即 fail()。"""
    name = validate_component(data.get("标的名称", ""), "标的名称")
    code = validate_component(data.get("标的代码", ""), "标的代码")
    stamp = str(data.get("时间戳", ""))
    if not re.fullmatch(r"\d{8}_\d{4}", stamp):
        fail("时间戳 格式应为 YYYYMMDD_HHMM，收到: %r" % stamp)

    depth = data.get("细分深度")
    if depth not in SUBDIVISION_DEPTHS:
        fail("细分深度 必填且须为 %s（默认 2 层，3 层须用户明确要求，见 09 默认口径表 D37 / 06 R35）；收到: %r"
             % ("/".join(str(d) for d in SUBDIVISION_DEPTHS), depth))
    depth_source = data.get("细分深度来源")
    if depth_source not in DEPTH_SOURCES:
        fail("细分深度来源 必填且须为 %s（06 R35 / 09 D37）；收到: %r"
             % ("/".join(DEPTH_SOURCES), depth_source))
    if depth == 3 and depth_source != "用户确认-3层":
        fail("细分深度=3 必须匹配 细分深度来源=用户确认-3层（3 层仅用户明确要求，06 R35 / 09 D37）；收到: %r"
             % depth_source)
    if depth == 2 and depth_source not in ("用户确认-2层", "非交互默认-2层"):
        fail("细分深度=2 仅匹配 细分深度来源=用户确认-2层 或 非交互默认-2层（06 R35 / 09 D37）；收到: %r"
             % depth_source)

    fields = data.get("fields")
    tables = data.get("tables")
    jm = data.get("简明分析说明")
    if not isinstance(fields, dict):
        fail("data.json 顶层应含 'fields' 对象")
    if not isinstance(tables, dict):
        fail("data.json 顶层应含 'tables' 对象")
    if not isinstance(jm, dict):
        fail("data.json 顶层应含 '简明分析说明' 对象")

    missing = [k for k in PAGE_FIELDS if not isinstance(fields.get(k), str) or not fields[k].strip()]
    if missing:
        fail("data.json 缺少非空文本字段: %s" % "、".join(missing))

    jm_missing = [k for k in JIANMING_KEYS if k not in jm]
    if jm_missing:
        fail("简明分析说明 缺少键: %s" % "、".join(jm_missing))
    if "端点" in jm:
        fail("简明分析说明不再另填端点；价日与状态统一从analysis_scope版本2读取")

    empty_tables = []
    for tname, cols in TABLE_FIELDS.items():
        rows = tables.get(tname)
        if not isinstance(rows, list) or not rows:
            empty_tables.append(tname)
            continue
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                fail("%s 表第 %d 行应为对象" % (tname, i + 1))
            bad = [c for c in cols if c not in r]
            if bad:
                fail("%s 表第 %d 行缺列: %s" % (tname, i + 1, "、".join(bad)))
        if tname == "失效价位":
            for i, r in enumerate(rows):
                if str(r.get("方向", "")).strip() not in INVALIDATION_DIRECTIONS:
                    fail("失效价位表第 %d 行'方向'列须为 break-down/break-up"
                         "（--from-report 零推断依赖），收到: %r" % (i + 1, r.get("方向")))
    if empty_tables:
        fail("data.json 表格为空或缺失: %s" % "、".join(empty_tables))
    if not any(str(r.get("项", "")).strip() == "细分深度来源"
               for r in tables.get("分析前提", [])):
        fail("分析前提表缺少'细分深度来源'行（06 R35 / 09 D37 强制披露）")

    mode = data.get("报告模式")
    if mode not in ("标准", "单方案防御"):
        fail("报告模式须为 标准/单方案防御")
    defensive = mode == "单方案防御"
    if defensive and (not isinstance(data.get("单方案原因"), str) or not data["单方案原因"].strip()):
        fail("单方案防御须披露单方案原因")
    if defensive and fields["交易计划"].strip() != "观望，不执行交易。":
        fail("单方案防御交易计划须为：观望，不执行交易。")
    factor_rows = tables["八因子"]
    if len(factor_rows) != 8 or {r["因子"] for r in factor_rows} != set(FACTOR_NAMES):
        fail("八因子表须恰含八项且不重复：%s" % "、".join(FACTOR_NAMES))
    for row in factor_rows:
        for plan in ("主方案", "替代方案"):
            value = row[plan]
            if defensive and plan == "替代方案":
                if value != "不适用":
                    fail("单方案防御的替代方案评分须为 不适用")
                continue
            if row["因子"] == "道氏一致性" and value == "不适用":
                continue
            score = finite_number(value, "八因子评分")
            if row["因子"] != "Guideline 得分" and score not in (0, 1, 2):
                fail("除 Guideline 得分外，因子分值须为 0/1/2")
    active_plans = {"主方案"} if defensive else {"主方案", "替代方案"}
    covered = set()
    for row in tables["失效价位"]:
        kind = row["类型"]
        if kind not in ("规则失效", "结构失效", "观察位"):
            fail("失效价位类型须为 规则失效/结构失效/观察位")
        if finite_number(row["失效价位"], "失效价位") <= 0:
            fail("失效价位须大于零")
        basis = str(row["规则依据"])
        ids = re.findall(r"\bR(\d+)\b", basis)
        if any(not 1 <= int(n) <= 35 for n in ids):
            fail("失效价位引用未知规则编号")
        if kind == "规则失效" and not set(ids) & {"5", "6", "7", "17", "29"}:
            fail("规则失效须引用可推导数值边界的 R5/R6/R7/R17/R29，结构身份与流程规则不能单独生成价位")
        if not basis.strip() or not str(row["触发后果"]).strip():
            fail("失效价位须有依据与触发后果")
        if kind != "观察位":
            covered.add(row["方案"])
    if not active_plans <= covered:
        fail("各有效方案须至少有一个真实失效条件，观察位不能代替")
    source_rows = [r for r in tables["分析前提"] if r["项"] == "细分深度来源"]
    if len(source_rows) != 1 or source_rows[0]["内容"] != depth_source:
        fail("分析前提中的细分深度来源与顶层字段不一致")
    try:
        validate_scope(data.get("analysis_scope"), depth, active_plans)
    except ValueError as exc:
        fail(str(exc))

    return name, code, stamp


def render_scope(data, html=False):
    """从同一结构化记录生成尺度与逐父浪覆盖表。"""
    premise, coverage = scope_tables(data["analysis_scope"])
    renderer = render_html_table if html else render_md_table
    return renderer(["项", "内容"], premise) + "\n\n" + renderer(
        ["方案", "父浪", "候选起止点", "观察区间", "摆动确认", "完成声明", "细分状态", "扫描事实", "依据与补证"], coverage)


def render_html_table(cols, rows):
    """生成网页 HTML 表格：<table><thead>…</thead><tbody>…</tbody></table>。"""
    thead = "".join("<th>%s</th>" % c for c in cols)
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % str(r.get(c, "")) for c in cols)
                   for r in rows)
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (thead, body)


def render_md_table(cols, rows):
    """生成 Markdown 表格：| 列头 |…| 与 | --- |…| 与数据行。竖线转义防破坏列。"""
    def esc(v):
        return str(v).replace("|", "\\|").replace("\n", "<br>")
    header = "| " + " | ".join(esc(c) for c in cols) + " |"
    sep = "|" + "|".join([" --- "] * len(cols)) + "|"
    lines = [header, sep]
    for r in rows:
        lines.append("| " + " | ".join(esc(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def render_jianming(jm, scope=None):
    """简明分析说明对象 → 4 行文本（日期 YYYY-MM-DD）。"""
    pts = child_pts = "端点未绑定覆盖事实"
    observation = ""
    if scope is not None:
        scheme = next(s for s in scope["schemes"] if s["name"] == "主方案")
        pts = endpoint_chain([w for w in scheme["waves"] if "-" not in w["path"]])
        child_pts = endpoint_chain([w for w in scheme["waves"]
                                   if "-" in w["path"] and w["path"].rsplit("-", 1)[0] == scheme["current_parent"]])
        observation = "；行情观察截至" + scope["data_end"]
    rating = str(jm["neely得分"]).strip()
    if rating in {"1", "2", "3"}:
        rating = "+" + rating
    return (
        "主方案：大级别%s，%s%s\n"
        "小级别：目前处于%s，%s\n"
        "Neely：得分%s，%s\n"
        "总结：目前%s"
        % (jm["大级别浪"], pts, observation, jm["小级别浪"], child_pts, rating, jm["neely强度"], jm["结论"])
    )


def substitute(text, mapping):
    """把 {{key}} 替换为 mapping[key]；未知占位符保留，供各入口做残留校验。"""
    for key, val in mapping.items():
        text = text.replace("{{%s}}" % key, str(val))
    return text
