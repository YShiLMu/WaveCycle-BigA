#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选浪统一事实入口：索引取价、层级契约、批量数值规则及双向目标。

输入格式与示例见references/tool_discipline.md第7节。
用法：wave_facts.py --csv <行情> --data <候选JSON> --out <系统临时目录/facts.json>
默认只打印异常摘要；--format json取完整结果，--scheme/--path只展开指定部分。
退出码：0=机械检查未发现违反（仍可能缺证），1=有违反，2=输入/调用错误。
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile

from ohlc_io import load_ohlc
from rule_check import evaluate
from swings import fractal_pivots
from target_calc import calculate
from analysis_scope import from_facts, validate_completion, is_solid_segment

LABELS = {
    "impulse": ["1", "2", "3", "4", "5"],
    "diagonal": ["1", "2", "3", "4", "5"],
    "zigzag": ["A", "B", "C"], "flat": ["A", "B", "C"],
    "triangle": ["A", "B", "C", "D", "E"],
    "double_combination": ["W", "X", "Y"],
    "triple_combination": ["W", "X", "Y", "X2", "Z"],
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def interval_extrema(df, start, end):
    """扫描含首尾影线的真实区间；不把越界极值自动判为波浪Rule违反。"""
    section = df.iloc[start:end + 1]
    result = {}
    for kind, column in (("H", "high"), ("L", "low")):
        offset = int(section[column].to_numpy().argmax() if kind == "H"
                     else section[column].to_numpy().argmin())
        index = start + offset
        result[column] = {"index": index, "date": df.date.iloc[index].strftime("%Y-%m-%d"),
                          "price": float(df[column].iloc[index])}
    return result


def inspect_interval(df, start, end, pivots):
    """用截止日内全序列计算分形，再过滤区间；不丢失边界附近的局部摆动。"""
    windows = []
    for k in (5, 3, 1):
        if k not in pivots:
            pivots[k] = fractal_pivots(df.high.to_numpy(), df.low.to_numpy(), k)
        windows.append({"k": k, "pivots": [
            {"index": int(i), "date": df.date.iloc[int(i)].strftime("%Y-%m-%d"),
             "price": float(price), "kind": kind}
            for i, price, kind in pivots[k] if start <= int(i) <= end]})
    return {"start": df.date.iloc[start].strftime("%Y-%m-%d"),
            "end": df.date.iloc[end].strftime("%Y-%m-%d"),
            "extrema": interval_extrema(df, start, end), "windows": windows}


def verify_endpoint_source(df, endpoint, current_k, pivots):
    """核对端点来源（06 R20 / 09 D31）：支持多尺度自适应（k=5/3/1 或局部真实极值）。"""
    if endpoint["pivot"]:
        return True, "命中本组k=%d摆动点" % current_k
    index, kind = endpoint["index"], endpoint["kind"]
    # 1. 多尺度自适应检查（逐级核对更细分形窗口 k=3, k=1 等）
    for alt_k in (5, 3, 1):
        if alt_k not in pivots:
            pivots[alt_k] = fractal_pivots(df.high.to_numpy(), df.low.to_numpy(), alt_k)
        if any(int(i) == index and k_kind == kind for i, _, k_kind in pivots[alt_k]):
            return True, "命中自适应k=%d摆动点" % alt_k
    # 2. 局部真实极值核对（相邻 ±1 根 bar 的局部真实最高/最低价）
    left = max(0, index - 1)
    right = min(len(df) - 1, index + 1)
    window_df = df.iloc[left:right + 1]
    is_local_extreme = (float(df.high.iloc[index]) == float(window_df.high.max()) if kind == "H"
                        else float(df.low.iloc[index]) == float(window_df.low.min()))
    if is_local_extreme:
        return True, "命中局部真实%s极值" % ("最高" if kind == "H" else "最低")
    return False, "未出现在k=%d或更细分形序列中，且非相邻局部极值" % current_k


def analyze(csv_path, data):
    """候选信息截止日内计算；索引始终对应原始CSV数据行（从0起）。"""
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("候选JSON须为version=1的对象")
    as_of = data.get("as_of")
    if not isinstance(as_of, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise ValueError("as_of须显式提供YYYY-MM-DD信息截止日")
    depth = data.get("depth", 3)
    if type(depth) is not int or depth not in (2, 3, 4):
        raise ValueError("depth须为3或4；2仅兼容旧局部机械输入，不能进入新报告")
    df = load_ohlc(csv_path, end=as_of)
    for column in ("open", "high", "low", "close", "volume"):
        if column in df:
            df[column] = df[column].astype(float)
    schemes = data.get("schemes")
    if not isinstance(schemes, list) or not schemes:
        raise ValueError("schemes须为非空候选数组")
    result = {"version": 1, "as_of": as_of, "data_end": df.date.iloc[-1].strftime("%Y-%m-%d"),
              "depth": depth, "schemes": [], "scope": "给定候选的机械检查；不确认形态、级别、完整内部结构或报告交付合规"}
    # 使用截止日内数据指纹，追加未来数据不能改变历史检查身份。
    result["data_hash"] = hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()
    names = set()
    for scheme in schemes:
        if not isinstance(scheme, dict) or not isinstance(scheme.get("name"), str) or not scheme["name"].strip():
            raise ValueError("每个候选须有非空name")
        name = scheme["name"]
        if name in names:
            raise ValueError("候选名称重复")
        names.add(name)
        if not isinstance(scheme.get("degree"), str) or not scheme["degree"].strip():
            raise ValueError("每个候选须声明degree")
        result["schemes"].append(analyze_scheme(df, scheme, depth))
    result["inspection_depth"] = max(w["path"].count("-") + 1
                                      for s in result["schemes"] for w in s["waves"])
    if "analysis_scope" in data:
        result["analysis_scope"] = from_facts(data["analysis_scope"], result, df.date.iloc[0].strftime("%Y-%m-%d"))
    return result


def analyze_scheme(df, scheme, depth):
    facts, checks, chart_paths, pivots = {}, [], [], {}
    groups = scheme.get("groups")
    if not isinstance(groups, list) or not groups or not all(isinstance(g, dict) for g in groups):
        raise ValueError("groups须为非空对象数组")
    paths = [g.get("path") for g in groups]
    if any(not isinstance(p, str) or (p and not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", p)) for p in paths):
        raise ValueError("group.path须为根路径空串或如1、1-1的父浪路径")
    if len(set(paths)) != len(paths) or "" not in paths:
        raise ValueError("组路径不得重复且须包含根组path='' ")

    def record(path, rule, status, basis):
        checks.append({"path": path, "rule": rule, "status": status, "basis": basis})

    for group in sorted(groups, key=lambda g: (g["path"].count("-") + 1 if g["path"] else 0, g["path"])):
        path = group["path"]
        if path and path.count("-") + 1 >= 4:
            raise ValueError("当前检查最多四层；父组路径最多三层")
        pattern = group.get("pattern")
        if pattern not in LABELS and pattern != "unknown":
            raise ValueError("未知pattern：%r" % pattern)
        if type(group.get("completed")) is not bool:
            raise ValueError("每组须显式声明completed布尔值")
        k = group.get("k", 3)
        if type(k) is not int or k < 1:
            raise ValueError("k须为正整数")
        if k not in pivots:
            pivots[k] = fractal_pivots(df.high.to_numpy(), df.low.to_numpy(), k)
        seq = pivots[k]
        pivot_keys = {(int(i), kind): pos for pos, (i, price, kind) in enumerate(seq)}
        points = group.get("points")
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("每组须有起点及至少一个终点")
        resolved = []
        for n, p in enumerate(points):
            if not isinstance(p, dict) or not isinstance(p.get("label"), str):
                raise ValueError("point须有label、index、kind")
            index, kind = p.get("index"), p.get("kind")
            if type(index) is not int or index < 0 or index >= len(df) or kind not in ("H", "L"):
                raise ValueError("端点索引须在截止日内原始CSV范围，kind须为H/L")
            if "price" in p:
                raise ValueError("端点价格由CSV提取，请勿另填price")
            if n and type(p.get("completed")) is not bool:
                raise ValueError("每个浪终点须显式声明completed布尔值")
            row = df.iloc[index]
            position = pivot_keys.get((index, kind))
            opposite = next(({"index": int(j), "date": df.date.iloc[int(j)].strftime("%Y-%m-%d"),
                              "kind": other_kind} for j, _, other_kind in seq[position + 1:]
                             if int(j) > index and other_kind != kind), None) if position is not None else None
            confirmed = opposite is not None
            if not confirmed:
                for alt_k in (3, 1):
                    if alt_k >= k:
                        continue
                    if alt_k not in pivots:
                        pivots[alt_k] = fractal_pivots(df.high.to_numpy(), df.low.to_numpy(), alt_k)
                    alt_opposite = next(({"index": int(j), "date": df.date.iloc[int(j)].strftime("%Y-%m-%d"),
                                          "kind": other_kind} for j, _, other_kind in pivots[alt_k]
                                         if int(j) > index and other_kind != kind), None)
                    if alt_opposite is not None:
                        opposite = alt_opposite
                        confirmed = True
                        break
            completed = p.get("completed", False)
            status = p.get("completion_status", "completion_candidate" if completed else "in_progress")
            unknown = {"status": "pending", "basis": "未提供独立组成／父级证据，不能升级确认完成"}
            resolved.append({"label": p["label"], "index": index, "kind": kind,
                             "price": float(row.high if kind == "H" else row.low),
                             "date": row.date.strftime("%Y-%m-%d"), "pivot": position is not None,
                             "confirmed": confirmed, "completed": completed,
                             "completion_status": status,
                             "completion_basis": p.get("completion_basis", "给定候选阶段，结构尚需独立核验"),
                             "internal_structure": p.get("internal_structure", dict(unknown)),
                             "parent_identity": p.get("parent_identity", dict(unknown)),
                             "depends_on": p.get("depends_on"),
                             "explicit_status": "completion_status" in p,
                             "pivot_confirmation": {"identified": position is not None, "window": k,
                                                    "confirmed": confirmed, "opposite": opposite}})
            if n:
                validate_completion(resolved[-1])
        if resolved[0]["label"] != "0":
            raise ValueError("组起点label须为0（起点占位，不是新增浪）")
        labels = [p["label"] for p in resolved[1:]]
        expected = LABELS.get(pattern)
        if len(set(labels)) != len(labels) or any(not re.fullmatch(r"[A-Za-z0-9]+", lb) for lb in labels):
            raise ValueError("组内标签须唯一且为单层字母数字；三重联合第二个X用X2作内部标识")
        if expected is None:
            record(path, "组成", "待核对", "形态未定；不由段数自动命名")
        elif labels != expected[:len(labels)] or (group["completed"] and labels != expected):
            record(path, "段数", "违反", "所声明%s需要%s；实际%s" % (pattern, expected, labels))
        if group["completed"] and not all(p["completed"] for p in resolved[1:]):
            record(path, "完成声明", "违反", "组已完成但包含未完成浪")
        if not all(p["completed"] for p in resolved[1:-1]):
            record(path, "形成顺序", "违反", "前序浪尚未完成，却已登记后续浪；先修正候选阶段")
        parent = facts.get(path) if path else None
        if path and parent is None:
            raise ValueError("子组%s缺少对应父浪" % path)
        if parent:
            if resolved[0]["index"] != parent["start"]["index"] or resolved[0]["kind"] != parent["start"]["kind"]:
                record(path, "父子衔接", "违反", "子组起点不等于父浪起点")
            if resolved[-1]["index"] > parent["end"]["index"]:
                record(path, "父子区间", "违反", "子组越出已登记父浪观察区间")
            if group["completed"] and (resolved[-1]["index"], resolved[-1]["kind"]) != (parent["end"]["index"], parent["end"]["kind"]):
                record(path, "父子闭合", "违反", "已完成子组终点不等于父浪终点")
            if group["completed"] != parent["completed"]:
                record(path, "完成声明", "违反", "父浪与其细分组完成声明不同")
        valid_chain = True
        segments = []
        for a, b in zip(resolved, resolved[1:]):
            full_path = path + "-" + b["label"] if path else b["label"]
            if b["completion_status"] == "start_candidate":
                previous_path = path + "-" + a["label"] if path else a["label"]
                if b["depends_on"]["path"] != previous_path or not a["completed"]:
                    raise ValueError("启动候选须依赖同组前一个候选结束浪")
            if full_path in facts:
                raise ValueError("浪路径重复：%s" % full_path)
            span = b["index"] - a["index"]
            length = abs(b["price"] - a["price"])
            if not math.isfinite(length):
                raise ValueError("浪长超出计算范围")
            direction_ok = (b["price"] > a["price"]) if b["kind"] == "H" else (b["price"] < a["price"])
            if span <= 0 or not length or a["kind"] == b["kind"] or not direction_ok:
                record(full_path, "端点契约", "违反", "端点须日期递增、H/L交替且浪长非零")
                valid_chain = False
            is_subwave = bool(path) or ("-" in full_path)
            for endpoint, role in ((a, "起点"), (b, "终点")):
                matched, match_basis = verify_endpoint_source(df, endpoint, k, pivots)
                if not matched:
                    # 子浪绝不判违反（退出码 1）；仅大级别第一层且严格声明确认时才允许判违反
                    strict = not is_subwave and (b["completion_status"] == "confirmed_complete" or (b["completed"] and not b["explicit_status"]))
                    status = "违反" if strict else "待核对"
                    record(full_path, "R20端点来源", status, role + "未出现在本组k=%d摆动序列（%s）；先复核窗口与选点" % (k, match_basis))
                elif not endpoint["pivot"]:
                    # 命中了自适应更细分形或局部极值，记录提示/待核对，绝不判违反
                    record(full_path, "R20端点来源", "待核对", role + "自适应匹配：%s（本组基准k=%d）" % (match_basis, k))
            # R34/D39 反向摆动确认：历史已走完内部子浪或后续已有推进展开，不判硬性违反
            has_subsequent = (b != resolved[-1])
            if b["completed"] and not b["confirmed"] and not b["explicit_status"]:
                if has_subsequent or is_subwave:
                    record(full_path, "R34/D39", "待核对",
                           "历史子浪后续已有走势推进；本组k=%d尺度未提取独立反向摆动点，按交替推进认定完成候选" % k)
                else:
                    record(full_path, "R34/D39", "违反", "宣称已完成终点，但截止日内尚无后续反向摆动确认")
            elif not b["completed"]:
                record(full_path, "形成阶段", "待核对", "未完成浪；比率仅为条件测量")
            facts[full_path] = {"path": full_path, "parent": path, "start": a, "end": b,
                                "length": length, "bars": span, "completed": b["completed"],
                                "k": k, "group_pattern": pattern,
                                **{key: b[key] for key in ("completion_status", "completion_basis", "internal_structure", "parent_identity", "depends_on")},
                                "ratio_to_previous": length / segments[-1]["length"] if segments and segments[-1]["length"] else None}
            if span > 0:
                fact = facts[full_path]
                fact["segment_extrema"] = interval_extrema(df, a["index"], b["index"])
                # 未完成浪必须继续观察至行情截止日，不能停在暂定终点。
                observation_end = b["index"] if b["completed"] else len(df) - 1
                fact["inspection"] = inspect_interval(df, a["index"], observation_end, pivots)
                lower, upper = sorted((a["price"], b["price"]))
                extrema = fact["inspection"]["extrema"]
                excursions = ["%s%g/%s" % (label, extrema[key]["price"], extrema[key]["date"])
                              for key, label, outside in (
                                  ("low", "最低", extrema["low"]["price"] < lower),
                                  ("high", "最高", extrema["high"]["price"] > upper)) if outside]
                if excursions:
                    record(full_path, "区间极值复核", "待核对",
                           "观察区间存在端点范围外极值：" + "、".join(excursions)
                           + "；重查端点、简单调整与组合结构，合法越界须解释；不自动判Rule违反")
            segments.append(facts[full_path])
        if pattern in ("impulse", "diagonal") and len(segments) >= 3 and valid_chain and labels == LABELS[pattern][:len(labels)]:
            rows = evaluate([(p["end"]["label"], p["start"]["price"], p["end"]["price"]) for p in segments])
            for r in rows:
                if r["rule"] == "R6" and (not segments[2]["completed"] or
                        (len(segments) == 5 and not segments[4]["completed"] and
                         segments[2]["length"] < segments[0]["length"] and r["status"] == "通过")):
                    r = dict(r, status="待确认", basis=r["basis"] + "；第三／第五浪未完成，不确认最终长度关系")
                elif r["rule"] == "R7" and pattern == "diagonal":
                    # 楔形/对角线例外条款：06 R8/R9/R10 允许第4浪与第1浪价格重叠
                    if r["status"] == "违反":
                        r = dict(r, status="通过", basis="第4浪与第1浪价格重叠（楔形例外条款允许重叠，06 R8/R9/R10）")
                    else:
                        r = dict(r, status="通过", basis=r["basis"] + "（楔形允许重叠，当前未重叠）")
                record(path, r["rule"], r["status"], r["basis"])
        elif pattern in ("impulse", "diagonal"):
            record(path, "数值规则", "待核对", "至少需正确的1–3端点序列；修正端点契约后再核")
        # 实线复用已采用历史段；严格完成确认与图形表达分别处理。
        run = []
        run_start = None
        for i, point in enumerate(resolved[1:], 1):
            solid = valid_chain and is_solid_segment(point)
            if solid:
                if not run:
                    start = resolved[i - 1]
                    run_start = start["index"]
                    zero = path + "-0" if path else "0"
                    run.append("%s@%d:%s" % (zero, run_start, "peak" if start["kind"] == "H" else "trough"))
                lb = path + "-" + point["label"] if path else point["label"]
                lb = "-".join("X" if part == "X2" else part for part in lb.split("-"))
                run.append("%s@%d:%s" % (lb, point["index"], "peak" if point["kind"] == "H" else "trough"))
            if run and (not solid or i == len(resolved) - 1):
                chart_paths.append({"parent": path, "path": ",".join(run), "start": run_start})
                run = []
    for path, fact in facts.items():
        if path.count("-") + 1 < depth and path not in paths:
            record(path, "细分覆盖", "待核对", "未登记下一层内部结构；不得据机械检查宣称完整数浪通过")
    targets = []
    for request in scheme.get("targets", []):
        if not isinstance(request, dict) or request.get("base") not in facts:
            raise ValueError("目标须引用本方案有效base浪路径")
        base = facts[request["base"]]
        anchor = facts.get(request.get("anchor"))
        if request.get("kind") == "projection" and anchor is None:
            raise ValueError("投射目标须引用本方案anchor浪路径（取其终点）")
        target = calculate(base["start"]["price"], base["end"]["price"], request.get("kind"),
                           request.get("ratios"), anchor["end"]["price"] if anchor else None,
                           request.get("direction"))
        target.update(base=request["base"], anchor=request.get("anchor"),
                      status="条件演算；目标用途、合法范围及共振另核")
        targets.append(target)
    return {"name": scheme["name"], "degree": scheme["degree"], "waves": list(facts.values()),
            "group_patterns": {g["path"]: g["pattern"] for g in groups},
            "checks": checks, "targets": targets, "chart_paths": chart_paths}


def print_summary(result, scheme=None, path=None):
    selected = [s for s in result["schemes"] if scheme is None or s["name"] == scheme]
    if not selected:
        raise ValueError("未找到指定方案")
    global_violations = sum(r["status"] == "违反" for s in result["schemes"] for r in s["checks"])
    print("截止 %s；行情末日 %s；全部方案违反%d项；仅给定候选的机械检查" %
          (result["as_of"], result["data_end"], global_violations))
    for s in selected:
        rows = [r for r in s["checks"] if path is None or r["path"] == path or r["path"].startswith(path + "-")]
        waves = [w for w in s["waves"] if path is None or w["path"] == path or w["path"].startswith(path + "-")]
        if path is not None and not waves:
            raise ValueError("未找到指定浪路径")
        counts = Counter(r["status"] for r in rows)
        print("%s（%s）：%d浪；违反%d；待核对%d；数值通过%d" %
              (s["name"], s["degree"], len(waves), counts["违反"], counts["待核对"] + counts["待确认"], counts["通过"]))
        issues = [r for r in rows if r["status"] in ("违反", "待核对", "待确认")]
        issues.sort(key=lambda r: r["status"] != "违反")
        shown = issues if path is not None else issues[:20]
        for r in shown:
            print("  %s %s %s：%s" % (r["path"] or "根组", r["rule"], r["status"], r["basis"]))
        if len(shown) < len(issues):
            print("  已省略%d项明细；完整结果用--out保存，或--path定点展开" % (len(issues) - len(shown)))
        if path is not None:
            for w in waves:
                print("  %s：%g→%g；长度%g；%d根；前浪比%s" %
                      (w["path"], w["start"]["price"], w["end"]["price"], w["length"], w["bars"], w["ratio_to_previous"]))
                inspection = w.get("inspection")
                if inspection:
                    extrema = inspection["extrema"]
                    print("    观察%s—%s；最高%g/%s；最低%g/%s；候选止点%s（%s，摆动%s）" %
                          (inspection["start"], inspection["end"], extrema["high"]["price"], extrema["high"]["date"],
                           extrema["low"]["price"], extrema["low"]["date"], w["end"]["date"],
                           "声明完成" if w["completed"] else "未完成", "已确认" if w["end"]["confirmed"] else "未确认"))
                    for window in inspection["windows"]:
                        print("    k=%d摆动：%s" % (window["k"], ", ".join(
                            "%s%g/%s" % (p["kind"], p["price"], p["date"]) for p in window["pivots"]) or "无"))
        for t in s["targets"]:
            if path is None or t["base"] == path:
                print("  目标 %s %s %s：%s（条件演算）" %
                      (t["base"], t["kind"], t["direction"], ", ".join("%g×=%g" % (v["ratio"], v["price"]) for v in t["values"])))
    print("未覆盖的形态、级别、内部结构与目标适用性须继续核对；退出码0不等于完整数浪通过。")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--data", required=True, help="候选树JSON，格式见tool_discipline第7节")
    parser.add_argument("--out", help="完整结果JSON的绝对路径，仅允许系统临时目录")
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    parser.add_argument("--scheme", help="摘要只展开指定方案；退出码仍覆盖所有方案")
    parser.add_argument("--path", help="摘要只展开指定浪及子浪，如1、1-1")
    args = parser.parse_args(argv)
    try:
        if args.format == "json" and (args.scheme is not None or args.path is not None):
            raise ValueError("--scheme/--path只用于摘要；完整JSON不截断")
        result = analyze(args.csv, load_json(args.data))
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        else:
            print_summary(result, args.scheme, args.path)
        if args.out:
            out = Path(args.out)
            if not out.is_absolute() or not out.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
                raise ValueError("--out须为系统临时目录内绝对路径")
            if out.resolve() in (Path(args.csv).resolve(), Path(args.data).resolve()):
                raise ValueError("结果不能覆盖输入文件")
            out.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    return int(any(r["status"] == "违反" for s in result["schemes"] for r in s["checks"]))


if __name__ == "__main__":
    sys.exit(main())
