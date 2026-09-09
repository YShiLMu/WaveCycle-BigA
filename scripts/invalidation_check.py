#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""失效价位触发判定脚本（workflow 第 5 步 2.2 节，D29 口径）。

用途：更新轮（05 更新数浪）把上一份报告的失效价位清单与最新行情 CSV 交给
本脚本，机械判定每个失效价位是否触发。禁止模型重读 CSV 逐根比价。
本脚本只输出事实（是否触发、首次触及日、确认窗口状态、距离），触发后的
分支处理（降级/切换/退回）仍由模型按 05 第 2.3 节判断。

判定口径（D29，与 05 第 2.2 节一致）：
  - 触及按极端价位（R20）：break-down（跌破支撑/失效位）= low ≤ 价位；
    break-up（升破压力/失效位）= high ≥ 价位
  - 确认窗口："触及后连续 N 根收盘未收回"（默认 N=2，--confirm-bars），
    从触及 bar 的下一根起计；收回定义：break-down 后收盘 > 价位，
    break-up 后收盘 < 价位
  - --since YYYY-MM-DD 只从该日起判定触及（增量更新用；此前触及不计）

用法：
    python invalidation_check.py --csv data.csv \
        --from-report "分析输出/<文件夹>/分析报告_<标的>_<代码>_<时间>.md" \
        [--include-structural] [--since 2026-08-14] [--confirm-bars 2]
    python invalidation_check.py --csv data.csv \
        --level "160|break-down|主方案|规则失效|R7" \
        --level "185|break-down|主方案|结构失效|06 6.6注" \
        [--since 2026-08-14] [--confirm-bars 2]

--from-report（推荐，模型零接触报告正文——交付文档内嵌 base64 后达 MB 级，
禁止模型 Read/整读报告）：脚本按锚点 <!-- INVALIDATION-TABLE-BEGIN/END --> 抽取
失效表；无锚点的历史报告降级按表头/章节标题定位并在输出披露"已降级解析"。
方向判定三层降级：① 方向列（break-down/break-up，新报告零推断）；
② 类型列括号标记（上→break-up，下→break-down）；③ 关键词推断
（跌破/下破/失守/低于/触及下方→break-down；升破/突破/上破/站上/触及上方→break-up，
"触及"必须带方位词才定方向）；仍不确定的行不猜方向，break-down 与 break-up
各查一次并标注「方向待确认」。默认只判「规则失效」行：结构失效行用
--include-structural 纳入；观察位（非规则失效价位/实务观察）单独输出，不参与触发判定。

--level 五段格式（竖线分隔，解析失败即报错退出，防止静默漏判）：
    价位|方向(break-down/break-up)|方案|类型(规则失效/结构失效)|对应规则

输出：markdown 表 + 触发摘要一行。退出码：0 正常（触发与否都算正常完成）。
CSV 列：date,open,high,low,close[,volume]（复用 key_levels.load_ohlc，坏数据硬拦截）。
"""

import argparse
import os
import re
import sys
import math

import pandas as pd

from ohlc_io import load_ohlc, fmt_date


def parse_level(text):
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 5:
        raise SystemExit("[错误] --level 需为 5 段「价位|方向|方案|类型|规则」，收到 %d 段：%r"
                         % (len(parts), text))
    price_s, direction, plan, kind, rule = parts
    if direction not in ("break-down", "break-up"):
        raise SystemExit("[错误] --level 方向段须为 break-down（跌破）或 break-up（升破），收到：%r" % direction)
    try:
        price = float(price_s)
    except ValueError:
        raise SystemExit("[错误] --level 价位段不是数字：%r" % price_s)
    if not math.isfinite(price) or price <= 0 or kind not in ("规则失效", "结构失效"):
        raise SystemExit("[错误] 价位须为正的有限数，类型须为规则失效/结构失效")
    return {"price": price, "direction": direction, "plan": plan, "kind": kind, "rule": rule}


# ---------------------------------------------------------------------------
# --from-report：从分析报告 .md 抽取失效价位表（模型零接触报告正文）
# ---------------------------------------------------------------------------

# 关键词推断词表（第三层降级）；"触及"必须带方位词才入表
DOWN_KEYWORDS = ("跌破", "下破", "失守", "低于", "向下突破", "触及下方")
UP_KEYWORDS = ("升破", "上破", "站上", "突破", "触及上方")
# 观察位标记：命中即单独输出、不参与触发判定
OBSERVATION_MARKERS = ("观察位", "非规则失效", "实务观察")


def _split_md_row(line):
    """拆分 markdown 表格数据行（处理 \\| 转义），返回单元格列表。"""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells, buf, esc = [], [], False
    for ch in line:
        if esc:
            buf.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def _find_invalidation_table(text):
    """定位失效价位表，返回 (表格行列表[含表头/分隔行], 定位方式)。
    锚点优先；无锚点降级：先按章节标题（含"失效价位清单"）找其后第一张表，
    再退为全文档找表头含"失效价位"的表。"""
    anchor_b = re.search(r"<!--\s*INVALIDATION-TABLE-BEGIN\s*-->", text)
    anchor_e = re.search(r"<!--\s*INVALIDATION-TABLE-END\s*-->", text)
    if anchor_b and anchor_e and anchor_b.start() < anchor_e.start():
        zone = text[anchor_b.end():anchor_e.start()]
        rows = [ln for ln in zone.splitlines() if ln.strip().startswith("|")]
        if len(rows) >= 2:
            return rows, "锚点抽取"
        raise SystemExit("[错误] 报告含 INVALIDATION-TABLE 锚点但锚点内未找到失效表")

    lines = text.splitlines()

    def table_after(start):
        tbl = []
        for ln in lines[start:]:
            if ln.strip().startswith("|"):
                tbl.append(ln)
            elif tbl:
                break
        return tbl if len(tbl) >= 2 else None

    for idx, ln in enumerate(lines):
        if ln.lstrip().startswith("#") and "失效价位清单" in ln:
            tbl = table_after(idx + 1)
            if tbl and "失效价位" in tbl[0]:
                return tbl, "降级解析（章节标题定位）"
    for idx, ln in enumerate(lines):
        if ln.strip().startswith("|") and "失效价位" in ln and "方案" in ln:
            tbl = table_after(idx)
            if tbl:
                return tbl, "降级解析（表头定位）"
    raise SystemExit("[错误] 报告中未找到失效价位表（无锚点、无'失效价位清单'章节、无匹配表头）")


def _column_index(header_cells, names):
    for n in names:
        for i, c in enumerate(header_cells):
            if c == n:
                return i
        for i, c in enumerate(header_cells):
            if n in c:
                return i
    return None


def _infer_direction(text):
    """第三层降级：关键词推断。双向命中或均未命中 → None（不猜，双向各查一次）。"""
    down = any(k in text for k in DOWN_KEYWORDS)
    up = any(k in text.replace("向下突破", "") for k in UP_KEYWORDS)
    if down == up:
        return None
    return "break-down" if down else "break-up"


def parse_report_levels(path):
    """从报告 .md 抽取失效价位。
    返回 (rules, structural, observations, note)：
    rules        待判定的规则失效行（direction=None 表示方向待确认，双向各查一次）；
    structural   结构失效行（默认不判定，--include-structural 纳入）；
    observations 观察位行（不参与触发判定，仅单独输出）。"""
    if path.lower().endswith((".html", ".htm")):
        raise SystemExit("[错误] --from-report 请传分析报告 .md（网页报告 .html 不作抽取源）")
    if not os.path.isfile(path):
        raise SystemExit("[错误] 报告文件不存在: %s" % path)
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    rows, how = _find_invalidation_table(text)
    header = _split_md_row(rows[0])
    i_plan = _column_index(header, ["方案"])
    i_kind = _column_index(header, ["类型"])
    i_price = _column_index(header, ["失效价位"])
    i_dir = _column_index(header, ["方向"])
    i_basis = _column_index(header, ["规则依据", "判定标准"])
    if i_price is None:
        raise SystemExit("[错误] 失效表缺少'失效价位'列，无法抽取")

    rules, structural, observations = [], [], []
    for ln in rows[1:]:
        cells = _split_md_row(ln)
        if not cells or all(set(c) <= set("-: ") for c in cells):
            continue  # 表头分隔行

        def cell(i):
            return cells[i] if i is not None and i < len(cells) else ""

        plan, kind, basis = cell(i_plan), cell(i_kind), cell(i_basis)
        m = re.search(r"-?\d+(?:\.\d+)?", cell(i_price).replace(",", ""))
        if not m:
            raise SystemExit("[错误] 失效价位列不是数字：%r（行：%s）"
                             % (cell(i_price), ln.strip()[:80]))
        entry = {"price": float(m.group()), "plan": plan or "-", "kind": kind,
                 "rule": "、".join(re.findall(r"R\d+", basis)) or basis[:24],
                 "basis": basis}
        # 方向三层降级：① 方向列（零推断）② 类型括号（上/下）③ 关键词推断 ④ 双向各查
        d = cell(i_dir)
        if d not in ("break-down", "break-up"):
            d = None
        if d is None and kind:
            if "（上）" in kind or "(上)" in kind:
                d = "break-up"
            elif "（下）" in kind or "(下)" in kind:
                d = "break-down"
        if d is None:
            d = _infer_direction(" ".join([kind, basis]))
        entry["direction"] = d
        blob = " ".join([kind, basis, plan])
        if any(k in blob for k in OBSERVATION_MARKERS):
            observations.append(entry)
            continue
        if "结构" in kind or (not kind and "结构" in basis):
            entry["kind"] = "结构失效"
            structural.append(entry)
            continue
        if not kind and not re.search(r"\bR(?:[1-9]|[12][0-9]|3[0-5])\b", basis):
            raise SystemExit("[错误] 历史失效表缺少类型且依据不能确定，请恢复正文后补齐类型")
        entry["kind"] = "规则失效"
        rules.append(entry)
    return rules, structural, observations, how


def check_level(df, lv, since=None, confirm_bars=2):
    """判定单个失效价位。返回 dict（状态、首次触及日、确认根数、确认日、距离）。"""
    price = lv["price"]
    down = lv["direction"] == "break-down"
    dates = df["date"].values
    lows = df["low"].astype(float).values
    highs = df["high"].astype(float).values
    closes = df["close"].astype(float).values

    start = 0
    if since is not None:
        ts = pd.Timestamp(since)
        idx = df.index[df["date"] >= ts]
        if len(idx) == 0:
            return {**lv, "status": "数据范围在 --since 之后为空", "first_touch": None,
                    "confirmed": None, "run": 0, "dist": None}
        start = next(i for i, d in enumerate(df["date"]) if d >= ts)

    rule_kind = "规则失效" in lv.get("kind", "")
    if rule_kind and not set(re.findall(r"\bR(\d+)\b", lv.get("rule", ""))) & {"5", "6", "7", "17", "29"}:
        return {**lv, "status": "待确认（未提供可推导价格比较符的规则）", "first_touch": None,
                "confirmed": None, "run": 0, "dist": float(closes[-1]) - price}
    strict = rule_kind and not re.search(r"\bR7\b", lv.get("rule", ""))
    touch = None
    for i in range(start, len(df)):
        hit = (lows[i] < price if strict else lows[i] <= price) if down else (highs[i] > price if strict else highs[i] >= price)
        if hit:
            touch = i
            break
    last_close = float(closes[-1])
    dist = last_close - price  # 正=在价位上方

    if touch is None:
        return {**lv, "status": "未触发", "first_touch": None,
                "confirmed": None, "run": 0, "dist": dist}

    if rule_kind:
        return {**lv, "status": "已触发规则失效（立即生效，无需收盘确认）",
                "first_touch": dates[touch], "confirmed": dates[touch], "run": 0, "dist": dist}

    # 触及后逐根扫描：streak = 当前连续未收回根数；streak 首次达到 confirm_bars
    # 的那根即确认日（确认后 streak 只表示当前尾段，不再影响判定）
    def recovered(c):
        return c >= price if down else c <= price

    confirm_idx = None
    streak = 0
    for j in range(touch + 1, len(df)):
        if not recovered(closes[j]):
            streak += 1
            if confirm_idx is None and streak >= confirm_bars:
                confirm_idx = j
        else:
            streak = 0
    confirmed = confirm_idx is not None
    status = ("已触发且已确认（连续 %d 根收盘未收回）" % confirm_bars if confirmed
              else "结构位触及待确认（触及后连续未收回 %d 根，确认窗口 %d）" % (streak, confirm_bars))
    return {**lv, "status": status, "first_touch": dates[touch],
            "confirmed": dates[confirm_idx] if confirmed else None,
            "run": streak, "dist": dist}


def main(argv=None):
    ap = argparse.ArgumentParser(description="失效价位触发判定（workflow 第 5 步 2.2，D29）")
    ap.add_argument("--csv", required=True, help="行情 CSV 路径")
    ap.add_argument("--from-report", default=None,
                    help="从分析报告 .md 抽取失效价位表（锚点优先，无锚点降级定位并披露；"
                         "模型零接触报告正文）。缺省时 --level 必填")
    ap.add_argument("--level", action="append", default=None,
                    help="失效价位，5 段「价位|break-down/break-up|方案|类型|规则」，可重复；"
                         "可与 --from-report 并用（手工补传）")
    ap.add_argument("--include-structural", action="store_true",
                    help="--from-report 时把结构失效价位一并纳入判定（默认只判规则失效行）")
    ap.add_argument("--since", default=None, help="只从该日期起判定触及（YYYY-MM-DD，增量更新用）")
    ap.add_argument("--confirm-bars", type=int, default=2,
                    help="确认窗口：触及后连续 N 根收盘未收回（默认 2，D 口径）")
    args = ap.parse_args(argv)
    if args.confirm_bars < 1:
        ap.error("确认根数须为正整数")

    levels, structural, observations = [], [], []
    if args.from_report:
        levels, structural, observations, how = parse_report_levels(args.from_report)
        note = how if how == "锚点抽取" else "该报告无锚点，已降级解析（按表头/章节标题定位）"
        print("失效价位来源：%s（%s）" % (args.from_report, note))
        print("抽取结果：规则失效 %d 条参与判定；结构失效 %d 条%s；观察位 %d 条（不参与触发判定）。\n"
              % (len(levels), len(structural),
                 "，已纳入判定" if args.include_structural else "，默认不参与（--include-structural 纳入）",
                 len(observations)))
        if args.include_structural:
            levels += structural
    if args.level:
        levels += [parse_level(t) for t in args.level]
    if not levels and not observations and not structural:
        raise SystemExit("[错误] 未提供失效价位：用 --from-report 或 --level")
    df = load_ohlc(args.csv)

    print("## 失效价位触发判定（invalidation_check.py，确认窗口 = 触及后连续 %d 根收盘未收回%s）\n"
          % (args.confirm_bars, "，--since %s 起" % args.since if args.since else ""))
    print("| 方案 | 失效价位 | 方向 | 类型 | 对应规则 | 状态 | 首次触及 | 确认日 | 距最新收盘 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    n_trig = 0
    n_conf = 0
    n_levels = 0
    for lv in levels:
        pending = lv.get("direction") is None
        dirs = ("break-down", "break-up") if pending else (lv["direction"],)
        n_levels += 1
        for d in dirs:
            sub = dict(lv, direction=d,
                       kind=lv["kind"] + "（方向待确认）" if pending else lv["kind"])
            r = check_level(df, sub, args.since, args.confirm_bars)
            arrow = ("跌破" if d == "break-down" else "升破") + ("?" if pending else "")
            dist = ("%.3f（价格在上方）" % r["dist"]) if r["dist"] is not None and r["dist"] > 0 else \
                   ("%.3f（价格在下方）" % -r["dist"]) if r["dist"] is not None else "-"
            print("| %s | %.3f | %s | %s | %s | %s | %s | %s | %s |"
                  % (sub["plan"], sub["price"], arrow, sub["kind"], sub["rule"], r["status"],
                     fmt_date(r["first_touch"]), fmt_date(r["confirmed"]), dist))
            if "已触发" in r["status"]:
                n_trig += 1
                if "已确认" in r["status"]:
                    n_conf += 1

    print("\n触发摘要：%d/%d 个失效价位已触发，其中 %d 个已过确认窗口。"
          % (n_trig, n_levels, n_conf))
    if any(lv.get("direction") is None for lv in levels):
        print("注：标注「方向待确认」的价位已按 break-down / break-up 各查一次（双向或零命中关键词，"
              "脚本不猜方向以免漏检）；请人工判定方向后按 05 第 2.3 节处理。")
    if structural and not args.include_structural:
        print("\n### 结构失效价位（不参与本次触发判定，--include-structural 纳入）\n")
        print("| 方案 | 失效价位 | 依据 |")
        print("| --- | --- | --- |")
        for ob in structural:
            print("| %s | %.3f | %s |" % (ob["plan"], ob["price"], ob["basis"][:40] or ob["rule"]))
    if observations:
        print("\n### 观察位（非规则失效价位/实务观察，不参与触发判定）\n")
        print("| 方案 | 失效价位 | 依据 |")
        print("| --- | --- | --- |")
        for ob in observations:
            print("| %s | %.3f | %s |" % (ob["plan"], ob["price"], ob["basis"][:40] or ob["rule"]))
    if n_trig:
        print("\n触发后的分支处理（降级/切换/退回，05 第 2.3 节）由模型判断，本脚本不替代。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
