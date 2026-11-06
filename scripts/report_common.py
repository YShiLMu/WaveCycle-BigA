# -*- coding: utf-8 -*-
"""报告生成共享层——data.json 加载/校验 + 无副作用的通用渲染器。

单一职责：本模块只做「数据准备 + 纯渲染」，不读具体报表模板、不写出报表——
由 gen_report_md.py（分析报告 .md）与 gen_report_web.py（网页报告 .html）两个入口分别调用。

data.json 模式（顶层键）：
    {
      "标的名称": "...", "标的代码": "...", "时间戳": "YYYYMMDD_HHMM",
      "细分深度": 3, "细分深度来源": "默认-3层",
      "fields": { <PAGE_FIELDS 中各字符串字段> },
      "tables": { <TABLE_FIELDS> 各表为 list[dict]，键与列头一一对应 },
      "简明分析说明": { "大级别浪": "第4浪", "小级别浪": "第4浪的b浪",
                        "neely得分": 1, "neely强度": "中等",
                        "结论": "偏多" }  # 各层价日及状态从analysis_scope读取，不另填端点
    }
细分深度3/4必填；三层来源默认-3层或用户确认-3层，四层来源用户确认-4层。
分析前提须披露来源，交付范围与额外检查证据由analysis_scope版本3保留；
分析前提另须含唯一一行"分钟分形层"询问答复（已询问-启用／已询问-不启用／未询问-环境无交互，04 EG-07）。
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
import html

from naming import ARCHIVE_TMP_DIR, ARCHIVE_TMP_MAX_BYTES, validate_component
import rule_ids
from analysis_scope import validate_scope, scope_tables, endpoint_chain, position_tables

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
    "短期支撑压力": ["周期", "方向", "浪", "基准", "比率", "价位", "级别"],
    "多周期共振": ["共振带", "方向", "浪族", "参与周期", "各轴原级", "星数", "级别", "结论"],
}

# 分钟分形层询问记录（04 EG-07）：跳过询问或记错答复的报告一律不得交付。
MINUTE_ASK_ROW = "分钟分形层"
MINUTE_ASK_VALUES = ("已询问-启用", "已询问-不启用", "未询问-环境无交互")

# 短期支撑压力与多周期共振（11/12 号文件）：波位用"N 级"，共振用"N 星"，两者不得混用。
SR_TABLES = ("短期支撑压力", "多周期共振")
SR_GRADES = ("1 级", "2 级", "3 级")
SR_SIDES = ("支撑", "压力")
SR_STAR_PATTERN = r"(?:0\.5|1|1\.5|2|2\.5|3) 星|≥3 星"
SR_SKIP_MARKS = ("不适用", "未数出浪型")

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
    def reject_constant(value):
        raise ValueError("报告状态不能含非有限 JSON 数值：%s" % value)

    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("报告状态含重复 JSON 键：%s" % key)
            obj[key] = value
        return obj

    state = json.loads(base64.b64decode(matches[0], validate=True).decode("utf-8"),
                       parse_constant=reject_constant, object_pairs_hook=unique_object)
    if not isinstance(state, dict):
        raise ValueError("报告状态顶层须为 JSON 对象")
    def check_finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("报告状态不能含非有限 JSON 数值")
        if isinstance(value, dict):
            for child in value.values():
                check_finite(child)
        elif isinstance(value, list):
            for child in value:
                check_finite(child)
    check_finite(state)
    # 恢复检查只约束容器类型，旧版本字段完整性留待迁移后由 validate 检查。
    for key in ("fields", "tables", "简明分析说明", "analysis_scope"):
        if key in state and not isinstance(state[key], dict):
            raise ValueError("报告状态的 %s 须为对象" % key)
    return state


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

# 新交付默认三层；旧状态仍可extract_state，但不能直接重新渲染。
SUBDIVISION_DEPTHS = (3, 4)
DEPTH_SOURCES = ("默认-3层", "用户确认-3层", "用户确认-4层")


ASSET_DIRNAME = "assets"
INSTALLED_SCRIPTS = os.path.join(os.path.expanduser("~"), ".agents", "skills", "wavecycle", "scripts")


def template_path(script_dir, filename):
    """技能模板路径：优先 WAVECYCLE_ASSETS（开发冒烟临时 assets），否则 <技能根>/assets。"""
    override = os.environ.get("WAVECYCLE_ASSETS")
    if override:
        return os.path.normpath(os.path.join(override, filename))
    return os.path.normpath(os.path.join(os.path.dirname(script_dir), ASSET_DIRNAME, filename))


def missing_asset_message(path, script_dir):
    """技能资源缺失的指路提示：执行根不对，不是依赖问题（见 SKILL.md「执行根」）。"""
    return ("缺少技能资源: %s\n"
            "  当前脚本所在目录: %s（同级没有 %s/）\n"
            "  技能脚本须从安装版执行: %s\n"
            "  安装或更新: 在项目根运行 python install_skill.py --install"
            % (path, script_dir, ASSET_DIRNAME, INSTALLED_SCRIPTS))


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


def validate_minute_ask(tables, legacy_ok=False):
    """分钟分形层询问答复必须留下唯一且合法的记录；返回该值供图组交叉核对。

    legacy_ok 仅供重嵌旧归档使用：旧报告没有该行时返回 None 并提示，
    新报告生成路径（gen_report_md/web）保持严格，缺行即拒绝。
    """
    rows = [r for r in tables["分析前提"] if str(r.get("项", "")).strip() == MINUTE_ASK_ROW]
    if len(rows) != 1:
        if legacy_ok and not rows:
            print("[提示] 旧归档报告缺少'%s'询问记录，按旧归档兼容重嵌（不做记录↔图组核对）"
                  % MINUTE_ASK_ROW, file=sys.stderr)
            return None
        fail("分析前提表须有且仅有一行'%s'（04 EG-07 强制询问记录，取值：%s）"
             % (MINUTE_ASK_ROW, "、".join(MINUTE_ASK_VALUES)))
    value = str(rows[0].get("内容", "")).strip()
    if value not in MINUTE_ASK_VALUES:
        fail("%s 记录须为 %s 之一，收到: %r"
             % (MINUTE_ASK_ROW, "、".join(MINUTE_ASK_VALUES), value))
    return value


def validate_sr_rows(tname, rows):
    """短期支撑压力／多周期共振表的取值契约：方向、级别、星数。

    降级行（首列写"不适用"或"未数出浪型"）不参与取值校验，但必须真实存在：
    空表由 validate 的 empty_tables 直接拒绝，禁止用空表冒充"无共振"。
    """
    head = "周期" if tname == "短期支撑压力" else "共振带"
    for index, row in enumerate(rows):
        if str(row.get(head, "")).strip() in SR_SKIP_MARKS:
            continue
        if str(row.get("方向", "")).strip() not in SR_SIDES:
            fail("%s表第 %d 行'方向'列须为 %s 之一，收到：%r"
                 % (tname, index + 1, "、".join(SR_SIDES), row.get("方向")))
        grade = str(row.get("级别", "")).strip()
        if grade not in SR_GRADES:
            fail("%s表第 %d 行'级别'列须为 %s 之一，收到：%r"
                 % (tname, index + 1, "、".join(SR_GRADES), grade))
        if tname == "多周期共振":
            stars = str(row.get("星数", "")).strip()
            if not re.fullmatch(SR_STAR_PATTERN, stars):
                fail("多周期共振表第 %d 行'星数'列须形如「1 星」「0.5 星」「≥3 星」，收到：%r"
                     % (index + 1, stars))


def validate(data, legacy_ok=False):
    """校验 data.json 并返回 (名称, 代码, 时间戳)；失败即 fail()。"""
    name = validate_component(data.get("标的名称", ""), "标的名称")
    code = validate_component(data.get("标的代码", ""), "标的代码")
    stamp = str(data.get("时间戳", ""))
    if not re.fullmatch(r"\d{8}_\d{4}", stamp):
        fail("时间戳 格式应为 YYYYMMDD_HHMM，收到: %r" % stamp)

    depth = data.get("细分深度")
    if type(depth) is not int or depth not in SUBDIVISION_DEPTHS:
        fail("新报告细分深度须为3或4（默认三层，用户要求时四层）")
    depth_source = data.get("细分深度来源")
    allowed = ("默认-3层", "用户确认-3层") if depth == 3 else ("用户确认-4层",)
    if depth_source not in allowed:
        fail("细分深度来源与3/4层不匹配：%r" % depth_source)

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
        fail("简明分析说明不再另填端点；价日与状态统一从analysis_scope版本3读取")

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
        if tname in SR_TABLES:
            validate_sr_rows(tname, rows)
    if empty_tables:
        fail("data.json 表格为空或缺失: %s" % "、".join(empty_tables))
    if not any(str(r.get("项", "")).strip() == "细分深度来源"
               for r in tables.get("分析前提", [])):
        fail("分析前提表缺少'细分深度来源'行（D37 强制披露）")
    validate_minute_ask(tables, legacy_ok=legacy_ok)

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
            if row["因子"] == "Guideline 得分" and (
                    isinstance(value, bool) or not re.fullmatch(r"[+-]?\d+", str(value).strip())):
                fail("Guideline 得分须为整数，与 score.py 累计分口径一致")
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
        ids = rule_ids.rule_ids(basis)
        if kind == "规则失效":
            if not ids:
                fail("规则失效须给出规则编号（如 R-IMP-07）")
            if not ids & rule_ids.DERIVABLE_RULES:
                fail("规则失效须引用可推导数值边界的 R-IMP-07/08/09/10；"
                     "失败浪、通道等结构预期请登记为“结构失效”")
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
    if html:
        return render_web_premise(data) + "\n" + "\n".join(
            render_web_scheme(data, scheme["name"]) for scheme in data["analysis_scope"]["schemes"])
    premise, coverage = scope_tables(data["analysis_scope"])
    renderer = render_md_table
    return renderer(["项", "内容"], premise) + "\n\n" + renderer(
        ["方案", "浪路径", "定位状态", "依据", "缺证", "撤销条件"], position_tables(data["analysis_scope"])) + "\n\n" + renderer(
        ["方案", "父浪", "候选起止点", "观察区间", "摆动确认", "完成声明", "细分状态", "扫描事实", "依据与补证"], coverage)


def render_web_premise(data):
    """网页只展示用户需要的四项前提；完整检查留在Markdown。"""
    source = {row["项"]: row["内容"] for row in data["tables"]["分析前提"]}
    dow = next((source[key] for key in ("道氏", "道氏前提", "道氏状态") if key in source), "未提供道氏判断")
    colors = "第一层白、第二层青、第三层橙" + ("、第四层亮黄绿" if data["细分深度"] == 4 else "")
    scope = data.get("analysis_scope", {})
    del_depth = scope.get("delivery_depth", data["细分深度"])
    insp_depth = scope.get("inspection_depth", 1)
    depth_desc = "交付%d层；实际端点登记到%d层" % (del_depth, insp_depth)
    return render_html_table(["项", "内容"], [
        {"项": "细分深度", "内容": depth_desc},
        {"项": "观察截止", "内容": data["analysis_scope"]["data_end"]},
        {"项": "道氏", "内容": dow},
        {"项": "图例", "内容": colors + "；实线为方案采用的历史段，虚线为未完成段。实线不代表浪型或归属已确认。"},
    ])


def web_wave_pattern(wave):
    """有内部组时采用其浪型；未定细型仅列该方案要求的候选类型。中英文专业命名严密区分驱动与推动。"""
    labels = {
        "impulse": "推动浪 (Impulse)",
        "diagonal": "倾斜三角形/斜纹浪 (Diagonal)",
        "motive": "驱动五浪 (Motive)",
        "zigzag": "锯齿调整浪 (Zigzag)",
        "flat": "平台调整浪 (Flat)",
        "triangle": "三角形调整浪 (Triangle)",
        "double_combination": "双重组合调整 (Double Combination)",
        "triple_combination": "三重组合调整 (Triple Combination)",
    }
    pattern = wave.get("pattern", "unknown")
    parent_pattern = wave.get("component_pattern")
    component = wave["path"].rsplit("-", 1)[-1]

    # 特殊处理调整浪内部的作用子浪（如平台/锯齿 C 浪，或锯齿 A 浪）：
    # 在理论层级上属于调整浪的驱动子浪（Motive Subwave），绝不能混同为大级别的单立推动浪（Impulse）
    if parent_pattern in ("flat", "zigzag") and component == "C":
        if pattern in ("impulse", "motive"):
            label = "C浪驱动五浪 (Motive C-wave)"
        elif pattern == "diagonal":
            label = "终结倾斜三角形 (Ending Diagonal C-wave)"
        else:
            label = "C浪驱动模式 (Motive C-wave，细型未定)"
    elif parent_pattern == "zigzag" and component == "A":
        if pattern in ("impulse", "motive"):
            label = "A浪驱动五浪 (Motive A-wave)"
        elif pattern == "diagonal":
            label = "引导倾斜三角形 (Leading Diagonal A-wave)"
        else:
            label = "A浪驱动模式 (Motive A-wave，细型未定)"
    elif parent_pattern == "flat" and component == "A":
        label = labels.get(pattern, "A浪调整 (Corrective A-wave)")
    elif component == "B":
        label = labels.get(pattern, "B浪调整 (Corrective B-wave)")
    else:
        label = labels.get(pattern)
        if label is None:
            if parent_pattern == "impulse":
                label = "驱动模式 (Motive Mode)" if component in ("1", "3", "5") else "调整模式 (Corrective Mode)"
            elif parent_pattern in ("zigzag", "flat"):
                label = "驱动模式 (Motive Mode)" if component in ("A", "C") else "调整模式 (Corrective Mode)"
            elif parent_pattern in ("triangle", "double_combination", "triple_combination"):
                label = "调整模式 (Corrective Mode)"
            else:
                return "未定"
            label += "，细型未定"

    if wave.get("completion_status") != "confirmed_complete":
        label += "（候选）"
    return label


def render_web_scheme(data, name):
    """网页方案表仅保留浪号、起止点、浪型与是否细分，按父子树排序。"""
    scheme = next((scheme for scheme in data["analysis_scope"]["schemes"] if scheme["name"] == name), None)
    if scheme is None:
        return "<p>不适用（单方案防御）</p>"
    children = {}
    for wave in scheme["waves"]:
        parent = wave["path"].rsplit("-", 1)[0] if "-" in wave["path"] else ""
        children.setdefault(parent, []).append(wave)
    all_children = {}
    for wave in scheme["waves"] + scheme.get("extra_checks", []):
        if "-" in wave["path"]:
            all_children.setdefault(wave["path"].rsplit("-", 1)[0], []).append(wave)
    rows = []

    def append_group(parent):
        for wave in sorted(children.get(parent, []), key=lambda w: w["start"]):
            end = "%s / %g" % (wave["end"], wave["end_price"])
            if not wave["completed"]:
                end = "观察截至" + end + "（未完成）"
            registered = sorted(all_children.get(wave["path"], []), key=lambda w: w["start"])
            full_span = (registered and registered[0]["start"] == wave["start"]
                         and registered[-1]["end"] == wave["end"] and all(w["completed"] for w in registered))
            level = wave["path"].count("-")
            indent = ("　" * level + "└─ ") if level > 0 else ""
            rows.append({"浪": indent + wave["path"],
                         "起止点": "%s / %g → %s" % (wave["start"], wave["start_price"], end),
                         "浪型": web_wave_pattern(wave),
                         "是否细分": ("是" if full_span else "部分") if registered else "否"})
            append_group(wave["path"])

    append_group("")
    return render_html_table(["浪", "起止点", "浪型", "是否细分"], rows)


def render_html_table(cols, rows):
    """生成网页 HTML 表格：<table><thead>…</thead><tbody>…</tbody></table>。"""
    thead = "".join("<th>%s</th>" % html_text(c) for c in cols)
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % html_text(r.get(c, "")) for c in cols)
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
        if scheme.get("current_path"):
            current = next(w for w in scheme["waves"] + scheme.get("extra_checks", []) if w["path"] == scheme["current_path"])
            child_pts = endpoint_chain([current]) + "；上级前提：" + current["parent_identity"]["basis"]
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
    return re.sub(r"\{\{([^}]+)\}\}",
                  lambda match: str(mapping.get(match.group(1), match.group(0))), text)


def html_text(value):
    """用户数据按文本转义；换行仅由本渲染器生成 <br>。"""
    return html.escape(str(value), quote=True).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>\n")


def substitute_html(template, text_fields, html_fragments=None):
    """分别接受用户文本和程序生成的可信片段，不从 JSON 接受原始 HTML。"""
    mapping = {key: html_text(value) for key, value in text_fields.items()}
    mapping.update(html_fragments or {})
    return substitute(template, mapping)
