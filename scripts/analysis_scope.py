# -*- coding: utf-8 -*-
"""分析尺度契约：集中核对框架覆盖、逐浪细分与正式图表窗口。

年／月／日是项目观察尺度，不是艾略特浪级的固定时长。
只验证已登记事实与缺证记录，不自动认定形态、父级或历史扫描已完成。
"""
from copy import deepcopy
from datetime import date
import math
import re


DAILY_PROFILE = "daily-year-month-day"
STATES = {"expanded", "in_progress", "unresolved", "leaf"}
STATE_LABELS = {"expanded": "已展开", "in_progress": "进行中", "unresolved": "无法分辨", "leaf": "本次最深层"}
SCOPE_VERSION = 2
REVIEW_REASONS = {"ambiguity", "resolution", "structure_conflict", "ongoing"}
NEXT_ACTIONS = {"recount", "finer_data", "wait"}


def display_path(path):
    """三重联合第二个X仅在数据中使用唯一标识X2。"""
    return "-".join("X" if part == "X2" else part for part in path.split("-"))


def required_text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("分析尺度缺少非空字段：" + key)
    return value


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("分析尺度日期须为YYYY-MM-DD")
    return date.fromisoformat(value)


def finite_price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("覆盖端点及扫描极值价格须为有限数值")


def validate_inspection(wave, data_end):
    """校验扫描事实的日期范围；完成声明与摆动确认分别保留。"""
    for key in ("start_price", "end_price"):
        finite_price(wave.get(key))
    inspection = wave.get("inspection")
    observation_end = wave["end"] if wave["completed"] else data_end
    if not isinstance(inspection, dict) or inspection.get("start") != wave["start"] or inspection.get("end") != observation_end:
        raise ValueError("逐浪inspection须覆盖实际区间；未完成浪观察至data_end")
    windows = inspection.get("windows")
    if (not isinstance(windows, list) or not all(isinstance(w, dict) for w in windows)
            or [w.get("k") for w in windows] != [5, 3, 1]):
        raise ValueError("逐浪扫描须登记k=5→3→1的实际摆动事实")
    for window in windows:
        points = window.get("pivots")
        if not isinstance(points, list):
            raise ValueError("扫描窗口pivots须为数组")
        previous = None
        for point in points:
            if not isinstance(point, dict) or point.get("kind") not in ("H", "L"):
                raise ValueError("扫描摆动须含H/L与真实价日")
            day = parse_date(point.get("date"))
            if not parse_date(wave["start"]) <= day <= parse_date(observation_end) or (previous and day < previous):
                raise ValueError("扫描摆动越出观察区间或日期逆序")
            finite_price(point.get("price"))
            previous = day
    extrema = inspection.get("extrema")
    if not isinstance(extrema, dict):
        raise ValueError("扫描须含真实high/low极值")
    for key in ("high", "low"):
        point = extrema.get(key)
        if not isinstance(point, dict) or not wave["start"] <= point.get("date", "") <= observation_end:
            raise ValueError("扫描极值须在观察区间内")
        parse_date(point["date"])
        finite_price(point.get("price"))
    if extrema["high"]["price"] < extrema["low"]["price"]:
        raise ValueError("扫描最高价不能低于最低价")


def validate_review(wave):
    """缺证必须逐窗口说明；多解、分辨率不足、反例和进行中不能混用。"""
    review = wave.get("review")
    if not isinstance(review, dict) or review.get("reason") not in REVIEW_REASONS:
        raise ValueError("缺证父浪须有review.reason：ambiguity/resolution/structure_conflict/ongoing")
    findings = review.get("windows")
    if (not isinstance(findings, list) or not all(isinstance(f, dict) for f in findings)
            or [f.get("k") for f in findings] != [5, 3, 1]):
        raise ValueError("缺证父浪review须逐项说明k=5→3→1的具体检查结果")
    for finding in findings:
        required_text(finding, "finding")
    action = review.get("next_action")
    if action not in NEXT_ACTIONS:
        raise ValueError("review.next_action须为recount/finer_data/wait")
    if wave["completed"] and (action == "wait" or review["reason"] == "ongoing" or wave["state"] == "in_progress"):
        raise ValueError("已结束历史区间不能等待未来补齐内部结构；须重数或补更细数据")
    if wave["state"] == "in_progress" and review["reason"] != "ongoing":
        raise ValueError("进行中须登记ongoing原因，结构缺证须单独说明")
    if action == "wait" and review["reason"] != "ongoing":
        raise ValueError("仅实际进行中结构可以等待后续；不能以等待代替历史复核")
    if review["reason"] == "ambiguity":
        alternatives = review.get("alternatives")
        if (not isinstance(alternatives, list) or not all(isinstance(a, str) and a.strip() for a in alternatives)
                or len(set(alternatives)) < 2):
            raise ValueError("多解须列至少两种具体候选，不能只写未形成唯一序列")


def validate_scope(scope, depth, names):
    """验证正式交付契约；返回原对象，缺证可保留但须逐浪登记。"""
    if not isinstance(scope, dict) or type(scope.get("version")) is not int or scope["version"] != SCOPE_VERSION:
        raise ValueError("正式报告须含analysis_scope版本2；旧状态可提取，须用CSV重建扫描与状态后再渲染")
    if type(depth) is not int or depth not in (2, 3):
        raise ValueError("分析尺度深度须为2或3")
    profile = scope.get("profile")
    if profile not in (DAILY_PROFILE, "user-defined"):
        raise ValueError("分析尺度profile须为daily-year-month-day或user-defined")
    if profile == "user-defined":
        if scope.get("source") != "user-request":
            raise ValueError("其他观察尺度须有用户明确要求，source=user-request")
        required_text(scope, "scope_basis")
    start, end = parse_date(scope.get("data_start")), parse_date(scope.get("data_end"))
    if start >= end:
        raise ValueError("分析尺度数据区间须递增")
    required_text(scope, "history_review")
    schemes = scope.get("schemes")
    if not isinstance(schemes, list) or not all(isinstance(s, dict) for s in schemes):
        raise ValueError("analysis_scope.schemes须为方案对象数组")
    for scheme in schemes:
        required_text(scheme, "name")
    if len(schemes) != len(names) or {s.get("name") for s in schemes} != set(names):
        raise ValueError("分析尺度须逐一覆盖全部有效方案，不得重复或遗漏")
    for scheme in schemes:
        framework = parse_date(scheme.get("framework_start"))
        if not start <= framework < end:
            raise ValueError("第一层框架起点须在数据覆盖范围内")
        for key in ("basis", "review_condition", "current_parent"):
            required_text(scheme, key)
        # 365天只触发覆盖披露，不是每一浪的时间规则。
        if profile == DAILY_PROFILE and (end - framework).days < 365:
            required_text(scheme, "short_scope_reason")
            required_text(scheme, "supplement")
        waves = scheme.get("waves")
        if not isinstance(waves, list) or not waves or not all(isinstance(w, dict) for w in waves):
            raise ValueError("每个方案须逐浪登记waves，不能以全部待确认代替")
        indexed = {}
        for wave in waves:
            path = wave.get("path")
            if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", path):
                raise ValueError("覆盖路径须为单层或父子路径，如1、1-1、2-A")
            level = path.count("-") + 1
            if path in indexed or level > depth:
                raise ValueError("覆盖路径重复或超出声明深度")
            a, b = parse_date(wave.get("start")), parse_date(wave.get("end"))
            if not framework <= a < b <= end:
                raise ValueError("覆盖浪段日期须在第一层框架内且递增")
            state = wave.get("state")
            if not isinstance(state, str) or state not in STATES or (state == "leaf") != (level == depth):
                raise ValueError("覆盖state与层级不一致；最深层用leaf，父浪须逐项说明细分状态")
            if any(type(wave.get(key)) is not bool for key in ("completed", "confirmed")):
                raise ValueError("每浪须登记completed和confirmed布尔值")
            validate_inspection(wave, scope["data_end"])
            required_text(wave, "evidence")
            if state in ("in_progress", "unresolved"):
                required_text(wave, "needed")
                validate_review(wave)
            indexed[path] = wave
        roots = sorted((w for p, w in indexed.items() if "-" not in p), key=lambda w: w["start"])
        if not roots or roots[0]["start"] != scheme["framework_start"]:
            raise ValueError("第一层首浪起点与框架起点不一致")
        if scheme["current_parent"] not in {w["path"] for w in roots}:
            raise ValueError("current_parent须指向已登记的第一层父浪")
        for path, wave in indexed.items():
            if "-" in path:
                parent = indexed.get(path.rsplit("-", 1)[0])
                if parent is None or not parent["start"] <= wave["start"] < wave["end"] <= parent["end"]:
                    raise ValueError("覆盖路径缺父浪或子浪越出父浪区间")
            children = sorted((w for p, w in indexed.items() if p.rsplit("-", 1)[0] == path and "-" in p),
                              key=lambda w: w["start"])
            if children and children[0]["start"] != wave["start"]:
                raise ValueError("细分起点未与父浪衔接")
            if wave["state"] == "expanded" and (not children or children[-1]["end"] != wave["end"]):
                raise ValueError("宣称已展开却未列子浪或未与父浪闭合")
            if wave["state"] == "expanded" and (not wave["completed"] or not all(c["completed"] for c in children)):
                raise ValueError("进行中或部分子浪不能登记为完整已展开")
            for a, b in zip(children, children[1:]):
                if a["end"] != b["start"]:
                    raise ValueError("同父浪的子浪区间不连续或重叠")
        for a, b in zip(roots, roots[1:]):
            if a["end"] != b["start"]:
                raise ValueError("第一层浪段区间不连续或重叠")
    return scope


def from_facts(metadata, result, data_start):
    """以CSV事实生成覆盖清单；调用者只补框架解释与每个缺证父浪的gaps。"""
    scope = deepcopy(metadata)
    if not isinstance(scope, dict):
        raise ValueError("analysis_scope须为对象")
    scope.update(version=SCOPE_VERSION, data_start=data_start, data_end=result["data_end"])
    schemes = scope.get("schemes")
    if not isinstance(schemes, list) or not all(isinstance(s, dict) for s in schemes):
        raise ValueError("analysis_scope.schemes须为方案对象数组")
    metadata_by_name = {required_text(s, "name"): s for s in schemes}
    names = [s["name"] for s in result["schemes"]]
    if len(metadata_by_name) != len(scope.get("schemes", [])) or set(metadata_by_name) != set(names):
        raise ValueError("分析尺度元数据与候选方案不一致")
    for facts in result["schemes"]:
        scheme = metadata_by_name[facts["name"]]
        gaps = scheme.pop("gaps", [])
        if not isinstance(gaps, list) or not all(isinstance(g, dict) for g in gaps):
            raise ValueError("gaps须逐个登记缺证父浪")
        gaps_by_path = {g.get("path"): g for g in gaps}
        if len(gaps_by_path) != len(gaps):
            raise ValueError("缺证父浪路径重复")
        records = []
        used_gaps = set()
        for fact in facts["waves"]:
            path = fact["path"]
            level = path.count("-") + 1
            if level > result["depth"]:
                continue
            children = [w for w in facts["waves"] if w["parent"] == path]
            expanded = (fact["completed"] and children and all(w["completed"] for w in children)
                        and children[-1]["end"]["date"] == fact["end"]["date"])
            gap = gaps_by_path.get(path)
            if level == result["depth"]:
                state, evidence = "leaf", "已登记截止日内端点；形态及完成性另核"
            elif gap is not None:
                state, evidence = gap.get("state"), gap.get("evidence")
                if state not in ("in_progress", "unresolved"):
                    raise ValueError("gaps只允许in_progress或unresolved")
                used_gaps.add(path)
            elif expanded:
                state, evidence = "expanded", "下一层端点组已登记且声明完成、首尾闭合；内部形态仍须按规则核验"
            else:
                raise ValueError("父浪%s未展开，须逐浪补gaps的state/evidence/needed" % path)
            record = {"path": path, "start": fact["start"]["date"], "end": fact["end"]["date"],
                      "start_price": fact["start"]["price"], "end_price": fact["end"]["price"],
                      "inspection": deepcopy(fact.get("inspection")),
                      "completed": fact["completed"], "confirmed": fact["end"]["confirmed"],
                      "state": state, "evidence": evidence}
            if gap is not None:
                record["needed"] = gap.get("needed")
                record["review"] = deepcopy(gap.get("review"))
            records.append(record)
        if used_gaps != set(gaps_by_path):
            raise ValueError("gaps含不存在或最深层的父浪路径")
        scheme["waves"] = records
    return validate_scope(scope, result["depth"], names)


def check_chart(scope, depth, name, dates, start_index, last_n, paths):
    """正式全景图须覆盖框架；每个已完成且确认的端点须进入同层--path。"""
    validate_scope(scope, depth, [s["name"] for s in scope["schemes"]])
    scheme = next((s for s in scope["schemes"] if s["name"] == name), None)
    if scheme is None:
        raise ValueError("图表方案不在analysis_scope中")
    if start_index is None or dates[start_index] != scheme["framework_start"]:
        raise ValueError("正式全景图--start必须等于第一层框架起点，不能取当前子浪起点")
    if last_n is not None and last_n < len(dates) - start_index:
        raise ValueError("正式全景图--last会裁掉第一层框架，禁止缩窗")
    expected = set()
    for wave in scheme["waves"]:
        if wave["completed"] and wave["confirmed"]:
            expected.add((display_path(wave["path"]), wave["end"]))
    actual = set()
    root_start = False
    indexed = {w["path"]: w for w in scheme["waves"]}
    for indices, labels, _ in paths:
        if len(indices) != len(labels):
            raise ValueError("正式全景图须用逐点标签的--path，禁止自动序号")
        if not indices:
            raise ValueError("正式全景图路径不能为空")
        first = labels[0].strip("[]()")
        parent_path = first.rsplit("-", 1)[0] if "-" in first else ""
        if first != (parent_path + "-0" if parent_path else "0"):
            raise ValueError("每条正式路径须从对应层起点0开始")
        if not 0 <= indices[0] < len(dates):
            raise ValueError("图表端点索引越界或晚于截止日")
        parent = next((w for path, w in indexed.items()
                       if display_path(path) == parent_path
                       and w["start"] == dates[indices[0]]), None) if parent_path else None
        start_date = parent["start"] if parent else scheme["framework_start"]
        previous_date = None
        for index, label in zip(indices, labels):
            if not 0 <= index < len(dates):
                raise ValueError("图表端点索引越界或晚于截止日")
            label = label.strip("[]()")
            if previous_date is None:
                if dates[index] != start_date or (parent_path and parent is None):
                    raise ValueError("图表路径起点与对应父浪不一致")
            else:
                # 三重联合的第二个X可沿用绘图显示名，由端点日期区分。
                matched = next((w for path, w in indexed.items()
                                if display_path(path) == label
                                and w["end"] == dates[index]), None)
                actual_parent = matched["path"].rsplit("-", 1)[0] if matched and "-" in matched["path"] else ""
                if matched is None or matched["start"] != previous_date or actual_parent != (parent["path"] if parent else ""):
                    raise ValueError("图表路径连线与已登记浪段不一致")
                if not matched["completed"] or not matched["confirmed"]:
                    raise ValueError("未完成或未确认端点不能进入实线--path")
            actual.add((label, dates[index]))
            root_start |= label == "0" and dates[index] == scheme["framework_start"]
            previous_date = dates[index]
    if not root_start:
        raise ValueError("正式全景图缺少第一层起点0的主链")
    if expected - actual:
        raise ValueError("正式全景图遗漏已确认浪端点：" + str(sorted(expected - actual)))


def scope_tables(scope):
    """两份报告共用的可见覆盖表，避免分别手写后出现口径漂移。"""
    profile = "第一层年尺度／第二层月尺度／第三层日尺度" if scope["profile"] == DAILY_PROFILE else scope["scope_basis"]
    premise = [{"项": "分析尺度", "内容": profile + "；时间尺度参考，不固定绑定浪级"},
               {"项": "历史扫描", "内容": scope["data_start"] + "—" + scope["data_end"] + "；" + scope["history_review"]}]
    coverage = []
    for scheme in scope["schemes"]:
        text = scheme["framework_start"] + "起；当前父浪=" + scheme["current_parent"] + "；" + scheme["basis"]
        text += "；复核条件：" + scheme["review_condition"]
        if scheme.get("short_scope_reason"):
            text += "；短框架限制：" + scheme["short_scope_reason"] + "；补证：" + scheme["supplement"]
        premise.append({"项": scheme["name"] + "第一层框架", "内容": text})
        for wave in scheme["waves"]:
            if wave["state"] != "leaf":
                coverage.append({"方案": scheme["name"], "父浪": wave["path"],
                                 "候选起止点": "%g/%s→%g/%s" % (wave["start_price"], wave["start"], wave["end_price"], wave["end"]),
                                 "观察区间": wave["start"] + "—" + wave["inspection"]["end"],
                                 "摆动确认": "已确认价格拐点" if wave["confirmed"] else "价格拐点未确认",
                                 "完成声明": "候选声明完成；结构另核" if wave["completed"] else "未完成；止点暂定",
                                 "细分状态": STATE_LABELS[wave["state"]],
                                 "扫描事实": inspection_summary(wave["inspection"]),
                                 "依据与补证": review_summary(wave)})
    return premise, coverage


def review_summary(wave):
    text = wave["evidence"]
    if wave.get("review"):
        review = wave["review"]
        reasons = {"ambiguity": "多解", "resolution": "分辨率不足", "structure_conflict": "结构冲突", "ongoing": "实际进行中"}
        actions = {"recount": "重数父级", "finer_data": "补该区间更细数据", "wait": "等待后续结构"}
        text += "；" + reasons[review["reason"]] + "；" + "；".join(
            "k=%d：%s" % (w["k"], w["finding"]) for w in review["windows"])
        if review.get("alternatives"):
            text += "；候选：" + " / ".join(review["alternatives"])
        text += "；下一步：" + actions[review["next_action"]]
    if wave.get("needed"):
        text += "；需：" + wave["needed"]
    return text


def inspection_summary(inspection):
    extrema = inspection["extrema"]
    return "最高%g/%s；最低%g/%s；%s" % (
        extrema["high"]["price"], extrema["high"]["date"], extrema["low"]["price"], extrema["low"]["date"],
        "、".join("k=%d共%d拐点" % (w["k"], len(w["pivots"])) for w in inspection["windows"]))


def endpoint_chain(waves):
    """价日来自覆盖事实，止点状态随每一浪显示，不默认为确定终点。"""
    if not waves:
        return "未登记子浪端点；见具体缺证记录"
    waves = sorted(waves, key=lambda w: w["start"])
    points = ["起点%g/%s" % (waves[0]["start_price"], waves[0]["start"])]
    for wave in waves:
        status = "完成终点候选" if wave["completed"] else "暂定止点，未完成"
        status += "；价格拐点已确认" if wave["confirmed"] else "；价格拐点未确认"
        points.append("%s:%g/%s（%s）" % (display_path(wave["path"]), wave["end_price"], wave["end"], status))
    return "→".join(points)


def pending_chart_segments(scope, name, dates):
    """正式图从同一覆盖事实派生进行中虚线；日期均已发生，不画未来终点。"""
    scheme = next(s for s in scope["schemes"] if s["name"] == name)
    index = {day: i for i, day in enumerate(dates)}
    return [{"path": display_path(w["path"]), "start": index[w["start"]], "end": index[w["end"]],
             "start_price": w["start_price"], "end_price": w["end_price"],
             "end_date": w["end"], "observation_end": w["inspection"]["end"]}
            for w in scheme["waves"] if not w["completed"]]
