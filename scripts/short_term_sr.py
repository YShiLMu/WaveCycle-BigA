#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""短期支撑压力与多周期共振计算。

用途：把`01_知识库_knowledge/11_短期支撑压力测算_shortterm_sr.md`的逐浪规则
与`12_多周期共振_multiframe_resonance.md`的星级规则落地为可复现数值。
本脚本只做算术与分级，不做数浪、不判形态、不产生失效价位。

输入 JSON（各周期已由模型数浪完成，这里只登记端点）：
{
  "as_of": "2026-11-06",
  "instrument": "某某股份 000000",
  "timeframes": [
    {"tf": "day", "active_wave": "4", "family": "调整", "direction": "up",
     "anchors": {"wave1_start": 20.0, "wave1_end": 26.0,
                 "wave3_start": 22.0, "wave3_end": 35.0,
                 "wave5_start": 30.0,
                 "prev_high": 30.0, "prev_low": 20.0}},
    {"tf": "60m", "countable": false}
  ]
}

输出：levels（各周期各档位）+ resonance（跨时间轴共振星级）。
用法：python short_term_sr.py --data sr.json [--format summary|json]
"""

import argparse
import json
import sys

from target_calc import calculate

# 浪族：驱动族只与驱动族共振，调整族只与调整族共振
WAVE_FAMILY = {"1": "驱动", "2": "调整", "3": "驱动", "4": "调整", "5": "驱动"}

# 各浪的比率档位 → 级别（唯一真源：11 号文件第 3 节）
PRESSURE_GRADES = {
    "1": [(0.382, 1), (0.5, 2), (0.618, 3)],
    "3": [(1.0, 1), (1.618, 2), (2.618, 3), (4.236, 3)],
}
SUPPORT_GRADES = {
    "2": [(0.236, 1), (0.382, 2), (0.5, 3), (0.618, 3), (0.786, 3)],
    "4": [(0.236, 1), (0.382, 2), (0.5, 3), (0.618, 3)],
}

# 时间轴优先级：共振聚类以最高轴为锚
AXIS_ORDER = {"day": 0, "60m": 1, "30m": 2, "15m": 3}
AXIS_LABEL = {"day": "日线", "60m": "60m", "30m": "30m", "15m": "15m"}

SAME_AXIS_TOL = 0.01     # D6：1% 内计 1 星
WIDE_AXIS_TOL = 0.03     # D64：1%–3% 计 0.5 星
STAR_CAP = 3.0


def _price(kind, start, end, ratio, anchor=None, direction=None):
    """按 target_calc 的口径取单一比率的价位。"""
    result = calculate(start, end, kind, ratios=[ratio], anchor=anchor, direction=direction)
    return result["values"][0]["price"]


def _require(anchors, *keys):
    missing = [k for k in keys if anchors.get(k) is None]
    if missing:
        raise ValueError("锚点缺失：%s" % "、".join(missing))


def _support_levels(wave, anchors):
    """返回 [(基准说明, 比率, 价位, 级别)]。"""
    if wave == "1":
        _require(anchors, "wave1_start")
        return [("1 浪起点 L1", None, anchors["wave1_start"], 3)]
    if wave == "2":
        _require(anchors, "wave1_start", "wave1_end")
        return [("回撤 1 浪 L1→H1", ratio,
                 _price("retracement", anchors["wave1_start"], anchors["wave1_end"], ratio), grade)
                for ratio, grade in SUPPORT_GRADES["2"]]
    if wave == "3":
        _require(anchors, "wave3_start")
        return [("3 浪起点 L3", None, anchors["wave3_start"], 3)]
    if wave == "4":
        _require(anchors, "wave3_start", "wave3_end")
        return [("回撤 3 浪 L3→H3", ratio,
                 _price("retracement", anchors["wave3_start"], anchors["wave3_end"], ratio), grade)
                for ratio, grade in SUPPORT_GRADES["4"]]
    _require(anchors, "wave5_start")
    return [("5 浪起点 L5", None, anchors["wave5_start"], 3)]


def _pressure_levels(wave, anchors):
    """返回 [(基准说明, 比率, 价位, 级别)]。"""
    if wave == "1":
        _require(anchors, "prev_high", "prev_low")
        return [("回撤前跌段 H0→L0", ratio,
                 _price("retracement", anchors["prev_high"], anchors["prev_low"], ratio), grade)
                for ratio, grade in PRESSURE_GRADES["1"]]
    if wave == "2":
        _require(anchors, "wave1_end")
        return [("2 浪起点 H2（=1 浪顶）", None, anchors["wave1_end"], 3)]
    if wave == "3":
        _require(anchors, "wave1_start", "wave1_end", "wave3_start")
        return [("自 3 浪起点 L3 扩展 1 浪幅度", ratio,
                 _price("projection", anchors["wave1_start"], anchors["wave1_end"], ratio,
                        anchor=anchors["wave3_start"], direction="up"), grade)
                for ratio, grade in PRESSURE_GRADES["3"]]
    if wave == "4":
        _require(anchors, "wave3_end")
        return [("4 浪起点 H4（=3 浪顶）", None, anchors["wave3_end"], 3)]
    return _wave5_pressures(anchors)


def _wave5_pressures(anchors):
    """5 浪三主线自 5 浪起点 L5 起算，算完后按价位升序赋级（11 号文件 3.6）。"""
    _require(anchors, "wave1_start", "wave1_end", "wave3_end", "wave5_start")
    origin = anchors["wave5_start"]
    raw = [
        ("0.618 × 浪 1 长度", 0.618,
         _price("projection", anchors["wave1_start"], anchors["wave1_end"], 0.618,
                anchor=origin, direction="up")),
        ("1.0 × 浪 1 长度", 1.0,
         _price("projection", anchors["wave1_start"], anchors["wave1_end"], 1.0,
                anchor=origin, direction="up")),
        ("0.618 ×（L1→H3）", 0.618,
         _price("projection", anchors["wave1_start"], anchors["wave3_end"], 0.618,
                anchor=origin, direction="up")),
        ("1.618 × 浪 1 长度（小概率）", 1.618,
         _price("projection", anchors["wave1_start"], anchors["wave1_end"], 1.618,
                anchor=origin, direction="up")),
    ]
    raw.sort(key=lambda item: item[2])
    graded = []
    for index, (basis, ratio, price) in enumerate(raw):
        graded.append((basis, ratio, price, min(index + 1, 3)))
    return graded


def _swap_side(levels, side):
    return [dict(level, side=side) for level in levels]


def timeframe_levels(timeframe):
    """算一条时间轴的全部支撑与压力档位。"""
    tf = timeframe["tf"]
    if not timeframe.get("countable", True):
        return []
    wave = str(timeframe["active_wave"])
    if wave not in WAVE_FAMILY:
        raise ValueError("%s 的 active_wave 须为 1–5，收到：%r" % (tf, wave))
    declared = timeframe.get("family")
    if declared and declared != WAVE_FAMILY[wave]:
        raise ValueError("%s 的 family=%r 与浪 %s 的族别 %s 不一致"
                         % (tf, declared, wave, WAVE_FAMILY[wave]))
    anchors = timeframe.get("anchors") or {}
    family = WAVE_FAMILY[wave]
    supports = _support_levels(wave, anchors)
    pressures = _pressure_levels(wave, anchors)
    if timeframe.get("direction") == "down":
        supports, pressures = pressures, supports
    rows = []
    for side, group in (("支撑", supports), ("压力", pressures)):
        for basis, ratio, price, grade in group:
            rows.append({"tf": tf, "side": side, "wave": wave, "family": family,
                         "basis": basis, "ratio": ratio, "price": float(price), "grade": grade})
    return rows


def cluster_resonance(levels, same_tol=SAME_AXIS_TOL, wide_tol=WIDE_AXIS_TOL):
    """按「方向 + 浪族」分组，以最高时间轴为锚聚簇，按距离赋星。"""
    groups = {}
    for level in levels:
        groups.setdefault((level["side"], level["family"]), []).append(level)
    bands = []
    for (side, family), members in groups.items():
        ordered = sorted(members, key=lambda m: (AXIS_ORDER.get(m["tf"], 9), -m["price"]))
        consumed = set()
        for anchor in ordered:
            if id(anchor) in consumed:
                continue
            cluster = [m for m in ordered if _within(anchor["price"], m["price"], wide_tol)]
            for member in cluster:
                consumed.add(id(member))
            if len({m["tf"] for m in cluster}) < 2:
                continue
            bands.append(_make_band(cluster, anchor, side, family, same_tol, wide_tol))
    return bands


def _within(reference, price, tolerance):
    return abs(price - reference) <= abs(reference) * tolerance


def _closest_per_axis(cluster, anchor_price):
    """同一时间轴若有多档落进同一簇，只取距锚最近的一档，避免同轴自我加星。"""
    per_axis = {}
    for member in cluster:
        current = per_axis.get(member["tf"])
        if current is None or (abs(member["price"] - anchor_price)
                               < abs(current["price"] - anchor_price)):
            per_axis[member["tf"]] = member
    return sorted(per_axis.values(), key=lambda m: AXIS_ORDER.get(m["tf"], 9))


def _make_band(cluster, anchor, side, family, same_tol, wide_tol):
    members = _closest_per_axis(cluster, anchor["price"])
    close_axes = [m for m in members if _within(anchor["price"], m["price"], same_tol)]
    near_axes = [m for m in members if not _within(anchor["price"], m["price"], same_tol)]
    stars = (len(close_axes) - 1) * 1.0 + len(near_axes) * 0.5
    capped = min(stars, STAR_CAP)
    prices = [m["price"] for m in members]
    return {
        "band": [min(prices), max(prices)],
        "side": side,
        "family": family,
        "members": members,
        "axes": [m["tf"] for m in members],
        "stars": capped,
        "star_label": ("≥3 星" if stars > STAR_CAP else _star_text(capped)),
        "conclusion": _conclusion(side, family, members, capped, stars > STAR_CAP),
    }


def _star_text(stars):
    return "%g 星" % stars


def _conclusion(side, family, members, stars, capped):
    """一句话结论：几星、哪些轴、各轴原级、最终取哪一级。"""
    axes = "／".join(AXIS_LABEL.get(m["tf"], m["tf"]) for m in members)
    grades = "／".join("%s %d 级" % (AXIS_LABEL.get(m["tf"], m["tf"]), m["grade"])
                      for m in members)
    top_grade = max(m["grade"] for m in members)
    prefix = "≥3 星" if capped else _star_text(stars)
    return "%s%s（%s，%s），取 %d 级" % (prefix, side, axes, grades, top_grade)


def _minute_layer_enabled(data):
    """未显式声明时按时间轴清单推断是否启用分钟分形层。"""
    declared = data.get("minute_layer")
    if declared is not None:
        return bool(declared)
    return any(tf.get("tf") in ("60m", "30m", "15m") for tf in data.get("timeframes", []))


def build(data, same_tol=SAME_AXIS_TOL, wide_tol=WIDE_AXIS_TOL):
    """返回 {"levels": [...], "resonance": [...], "skipped": [...], "minute_layer": bool}。"""
    levels = []
    skipped = []
    for timeframe in data.get("timeframes", []):
        if not timeframe.get("countable", True):
            skipped.append(timeframe["tf"])
            continue
        levels.extend(timeframe_levels(timeframe))
    return {"levels": levels,
            "resonance": cluster_resonance(levels, same_tol, wide_tol),
            "skipped": skipped,
            "minute_layer": _minute_layer_enabled(data)}


def _check_columns(table_name, rows):
    """列名与顺序必须与 report_common.TABLE_FIELDS 完全一致，防止脚本与模板漂移。"""
    from report_common import TABLE_FIELDS
    expected = TABLE_FIELDS[table_name]
    for index, row in enumerate(rows):
        if list(row.keys()) != expected:
            raise ValueError("%s表第 %d 行列名须为 %s，实际 %s"
                             % (table_name, index + 1, expected, list(row.keys())))


def build_tables(result):
    """把计算结果整理成 data.json 的 tables 片段；整理环节不交给模型。"""
    sr_rows = []
    for level in result["levels"]:
        sr_rows.append({
            "周期": AXIS_LABEL.get(level["tf"], level["tf"]),
            "方向": level["side"],
            "浪": level["wave"],
            "基准": level["basis"],
            "比率": "-" if level["ratio"] is None else "%g" % level["ratio"],
            "价位": "%.2f" % level["price"],
            "级别": "%d 级" % level["grade"],
        })
    if not sr_rows:
        sr_rows.append({"周期": "未数出浪型", "方向": "支撑", "浪": "-", "基准": "-",
                        "比率": "-", "价位": "-", "级别": "1 级"})

    res_rows = []
    for band in result["resonance"]:
        members = band["members"]
        res_rows.append({
            "共振带": "%.2f–%.2f" % (band["band"][0], band["band"][1]),
            "方向": band["side"],
            "浪族": band["family"],
            "参与周期": "／".join(AXIS_LABEL.get(m["tf"], m["tf"]) for m in members),
            "各轴原级": "／".join("%s %d 级" % (AXIS_LABEL.get(m["tf"], m["tf"]), m["grade"])
                                for m in members),
            "星数": band["star_label"],
            "级别": "%d 级" % max(m["grade"] for m in members),
            "结论": band["conclusion"],
        })
    if not res_rows:
        reason = ("不适用（仅单时间轴）" if not result["minute_layer"]
                  else "不适用（无两条及以上时间轴在 3% 内重合）")
        res_rows.append({"共振带": "不适用", "方向": "支撑", "浪族": "调整",
                         "参与周期": "—", "各轴原级": "—", "星数": "0 星",
                         "级别": "1 级", "结论": reason})

    tables = {"短期支撑压力": sr_rows, "多周期共振": res_rows}
    for name, rows in tables.items():
        _check_columns(name, rows)
    return tables


def merge_into_tables(data_path, tables, apply=False):
    """把两张表写回 data.json，其余字段原样保留；默认只报告差异。"""
    with open(data_path, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("data.json 顶层须为对象")
    merged = dict(data.get("tables") or {})
    changes = []
    for name, rows in tables.items():
        before = merged.get(name)
        changes.append("%s：%s → %d 行" % (
            name, "缺失" if not before else "%d 行" % len(before), len(rows)))
        merged[name] = rows
    data["tables"] = merged
    report = "；".join(changes)
    if not apply:
        return "（dry-run）未写入。" + report + "；加 --apply 才落盘"
    with open(data_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return "已写入 " + data_path + "：" + report


def render_summary(result):
    lines = []
    if not result["levels"]:
        lines.append("（无可用档位：所有周期均未数出浪型）")
        return "\n".join(lines)
    lines.append("== 1. 分周期支撑压力 ==")
    for level in result["levels"]:
        ratio = "-" if level["ratio"] is None else "%g" % level["ratio"]
        lines.append("  %s %s 浪 %s ｜ %-26s 比率 %-5s 价位 %10.2f ｜ %d 级"
                     % (AXIS_LABEL.get(level["tf"], level["tf"]), level["side"],
                        level["wave"], level["basis"], ratio, level["price"], level["grade"]))
    lines.append("")
    lines.append("== 2. 多周期共振 ==")
    if not result["resonance"]:
        lines.append("  （不适用：无两条及以上时间轴在 3% 内重合）")
    for band in result["resonance"]:
        lines.append("  %.2f–%.2f %s %s ｜ %s ｜ %s"
                     % (band["band"][0], band["band"][1], band["side"], band["family"],
                        band["star_label"], band["conclusion"]))
    if result["skipped"]:
        lines.append("")
        lines.append("  未数出浪型、未参与共振的周期：%s" % "、".join(result["skipped"]))
    return "\n".join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="短期支撑压力与多周期共振计算")
    parser.add_argument("--data", required=True, help="各周期浪型端点 JSON 路径")
    parser.add_argument("--same-tol", type=float, default=SAME_AXIS_TOL,
                        help="1 星容差（默认 0.01，即 1%% 内计 1 星）")
    parser.add_argument("--wide-tol", type=float, default=WIDE_AXIS_TOL,
                        help="0.5 星容差（默认 0.03，即 1%%–3%% 计 0.5 星）")
    parser.add_argument("--format", choices=["summary", "json", "tables"], default="summary",
                        help="summary 摘要 / json 原始结果 / tables 整理成 data.json 的 tables 片段")
    parser.add_argument("--merge-into", default=None,
                        help="把两张表写回指定 data.json（默认 dry-run；须同时 --format tables）")
    parser.add_argument("--apply", action="store_true",
                        help="配合 --merge-into 真正写盘；不加时只打印将发生的差异")
    args = parser.parse_args(argv)
    if args.same_tol <= 0 or args.wide_tol <= args.same_tol:
        parser.error("容差须满足 0 < same-tol < wide-tol")
    if args.merge_into and args.format != "tables":
        parser.error("--merge-into 须与 --format tables 同时使用")
    with open(args.data, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    try:
        result = build(data, args.same_tol, args.wide_tol)
        tables = build_tables(result)
    except ValueError as exc:
        parser.error(str(exc))
    if args.merge_into:
        try:
            print(merge_into_tables(args.merge_into, tables, args.apply))
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    elif args.format == "tables":
        print(json.dumps(tables, ensure_ascii=False, allow_nan=False, indent=2))
    elif args.format == "json":
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    else:
        print(render_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
