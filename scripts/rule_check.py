#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rule Check 数值规则判定（workflow 第 2 步第 4 节，D31 口径）。

用途：对候选数法的推动浪端点做 R-IMP-07/08/09/10（旧编号 R5/R6/R7）与失败浪位置判定，输出
"通过/违反 + 数值依据"，消除手算误差与漏检。输入是**模型枚举出的候选
浪段端点价格**（按 R20 极端价位口径取自 swings.py 输出），不是 CSV。

判定范围（仅数值可判的 5 条，其余规则仍由模型逐条核对）：
  - R-IMP-07（旧 R5）第 2 浪终点不得低于第 1 浪起点（下跌推动镜像：不得高于）
  - R-IMP-09（旧 R6）第 3 浪不是 1/3/5 中最短
  - R-IMP-10（旧 R7）第 4 浪终点不得进入第 1 浪价格区域（下跌镜像对称）
  - 失败浪（旧 R17/R29；2 代不设硬公理，属结构判断）前提：第 5 浪终点未超越第 3 浪终点（ up：未创新高 /
    down：未创新低）——"子浪是否完整五浪"仍由模型确认，脚本只给位置事实
  形态类规则（R8–R16、R21–R28 等）与 R18 计数一致性不在此列，由模型判定。

用法（--wave 必须重复出现，不能用空格分隔多值；五浪全给判 5 条，只给
1–3 判 R-IMP-07/09，只给 1–4 判到 R-IMP-10）：
    python rule_check.py --wave "1:100:160" --wave "2:160:130" \
                         --wave "3:130:220" --wave "4:220:185" --wave "5:185:178"

--wave 格式：标签:起点价:终点价，用冒号分隔三段：
  · 标签 = 任意不含冒号的字符串（惯例用 "1"/"2"/"3"…，可与下一段用 @ 区隔，但
    三段分隔符必须是冒号）；
  · 起点价/终点价 = 数字（R20 极端价位口径），价格内部不得含冒号；
  · 每个浪段一个 --wave；传多个时必须各自带 --wave 前缀，禁止 --wave "1:.." "2:.."。
下跌推动照常给"高→低"端点，脚本按第 1 浪方向自动镜像全部规则；--dir up/down
可显式指定。

输出：markdown 表（规则|判定|依据）+ 缺浪提示；存在"违反"时退出码 1
（方案判"规则失效"由模型按 R19 执行，脚本只标数值事实）。
"""

import argparse
import sys
import math


def parse_wave(text):
    parts = text.split(":")
    if len(parts) != 3:
        raise SystemExit("[错误] --wave 需为「标签:起点价:终点价」（用冒号分三段，"
                         "或写成 `--wave \"1:a:b\"`；勿用 @ 或空格分隔），收到：%r" % text)
    label = parts[0].strip()
    try:
        values = float(parts[1]), float(parts[2])
        if not label or not all(math.isfinite(v) for v in values):
            raise ValueError("端点必须为有限数值")
        return label, *values
    except ValueError:
        raise SystemExit("[错误] --wave 价格段不是数字：%r（格式「标签:起点价:终点价」）" % text)


def get(waves, label):
    for w in waves:
        if w[0] == label:
            return w
    return None


def evaluate(waves, direction=None, extrema=None):
    """共享数值检查：价格不负责确认形态；返回可复用记录，不打印。
    extrema 可选字典，提供各浪含影线极值 {label: {"high": float, "low": float}}。
    """
    by_label = {w[0]: w for w in waves}
    if len(by_label) != len(waves):
        raise ValueError("浪标签重复")
    if not all(label in by_label for label in ("1", "2", "3")):
        raise ValueError("缺少第1/2/3浪")
    if set(by_label) - {"1", "2", "3", "4", "5"}:
        if any(lbl in by_label for lbl in ("A", "B", "C", "a", "b", "c")):
            raise ValueError("普通推动只接受1–5标签；若校验调整浪请指定 --pattern zigzag 或 flat")
        raise ValueError("普通推动只接受1–5标签")
    if "5" in by_label and "4" not in by_label:
        raise ValueError("提供第5浪时不能缺第4浪")
    ordered = [by_label[str(i)] for i in range(1, len(by_label) + 1)]
    for i, (_, start, end) in enumerate(ordered):
        if not all(math.isfinite(v) for v in (start, end)) or start == end:
            raise ValueError("端点必须有限且浪长非零")
        if i and ordered[i - 1][2] != start:
            raise ValueError("相邻浪端点必须相接")
    w1, w2, w3 = ordered[:3]
    up = w1[2] > w1[1]
    if direction is not None and (direction == "up") != up:
        raise ValueError("显式方向与第1浪端点不一致")
    result = []

    def row(rule, status, basis):
        result.append({"rule": rule, "status": status, "basis": basis})

    ext_dict = extrema or {}
    ok = w2[2] >= w1[1] if up else w2[2] <= w1[1]
    row("R-IMP-07", "通过" if ok else "违反", "第2浪终点 %g；第1浪起点 %g（等号允许）" % (w2[2], w1[1]))
    l1, l3 = abs(w1[2] - w1[1]), abs(w3[2] - w3[1])
    w4, w5 = by_label.get("4"), by_label.get("5")
    if w5:
        l5 = abs(w5[2] - w5[1])
        row("R-IMP-09", "通过" if l3 >= min(l1, l5) else "违反",
            "浪长 |1|=%g、|3|=%g、|5|=%g；仅第3浪同时严格短于1/5时违反" % (l1, l3, l5))
    else:
        row("R-IMP-09", "待确认", "第5浪未提供；|1|=%g、|3|=%g；若第3浪已完成且短于第1浪，第5浪长度须 ≤ %g" % (l1, l3, l3))
    if w4:
        if up:
            w1_top = ext_dict.get("1", {}).get("high", max(w1[1], w1[2]))
            w4_bottom = ext_dict.get("4", {}).get("low", min(w4[1], w4[2]))
            ok = w4_bottom > w1_top
            if ok:
                basis = ("第4浪区间最低 %g 高于第1浪最高 %g，无重叠；推动浪（Impulse）绝大多数情况下严禁重叠（仅倾斜三角形/楔形 Diagonal 例外允许）"
                         % (w4_bottom, w1_top))
            else:
                basis = ("第4浪区间最低 %g 侵入第1浪最高 %g 区域发生重叠；在波浪理论中，绝大多数情况下推动浪（Impulse）严禁浪4与浪1价格重叠；仅当形态为倾斜三角形（斜纹浪/楔形 Diagonal Wave）时作为唯一形态例外允许重叠。当前方案被明确声明为推动浪（Impulse），一票否决"
                         % (w4_bottom, w1_top))
        else:
            w1_bottom = ext_dict.get("1", {}).get("low", min(w1[1], w1[2]))
            w4_top = ext_dict.get("4", {}).get("high", max(w4[1], w4[2]))
            ok = w4_top < w1_bottom
            if ok:
                basis = ("第4浪区间最高 %g 低于第1浪最低 %g，无重叠；推动浪（Impulse）绝大多数情况下严禁重叠（仅倾斜三角形/楔形 Diagonal 例外允许）"
                         % (w4_top, w1_bottom))
            else:
                basis = ("第4浪区间最高 %g 侵入第1浪最低 %g 区域发生重叠；在波浪理论中，绝大多数情况下推动浪（Impulse）严禁浪4与浪1价格重叠；仅当形态为倾斜三角形（斜纹浪/楔形 Diagonal Wave）时作为唯一形态例外允许重叠。当前方案被明确声明为推动浪（Impulse），一票否决"
                         % (w4_top, w1_bottom))
        row("R-IMP-10", "通过" if ok else "违反", basis)
    else:
        row("R-IMP-10", "不适用", "未提供第4浪")
    if w5:
        failure = w5[2] <= w3[2] if up else w5[2] >= w3[2]
        row("失败浪(R17/R29)", "位置满足" if failure else "位置不满足",
            "第5浪终点 %g；第3浪终点 %g；失败浪的内部完整五浪仍须另核" % (w5[2], w3[2]))
    else:
        row("失败浪(R17/R29)", "不适用", "未提供第5浪")
    return result


def evaluate_corrective(waves, pattern="zigzag", direction=None):
    """调整浪（A-B-C）数值规则判定（R12/R25 等）。"""
    by_label = {w[0]: w for w in waves}
    if len(by_label) != len(waves):
        raise ValueError("浪标签重复")
    if "A" not in by_label:
        raise ValueError("调整浪必须包含A浪")
    if set(by_label) - {"A", "B", "C"}:
        raise ValueError("基础调整浪只接受A–C标签")
    if "C" in by_label and "B" not in by_label:
        raise ValueError("提供C浪时不能缺B浪")

    order = [by_label[k] for k in ["A", "B", "C"] if k in by_label]
    for i, (_, start, end) in enumerate(order):
        if not all(math.isfinite(v) for v in (start, end)) or start == end:
            raise ValueError("端点必须有限且浪长非零")
        if i and order[i - 1][2] != start:
            raise ValueError("相邻浪端点必须相接")

    wa = by_label["A"]
    up = wa[2] > wa[1]
    if direction is not None and (direction == "up") != up:
        raise ValueError("显式方向与A浪端点不一致")

    result = []

    def row(rule, status, basis):
        result.append({"rule": rule, "status": status, "basis": basis})

    wb = by_label.get("B")
    wc = by_label.get("C")

    if wb:
        # R25: 调整浪方向规则：B 浪方向必须与 A 浪反向
        b_up = wb[2] > wb[1]
        b_dir_ok = (b_up != up)
        row("R25", "通过" if b_dir_ok else "违反",
            "B浪方向必须与A浪反向（A浪 %s，B浪 %s）" % ("向上" if up else "向下", "向上" if b_up else "向下"))

        if pattern == "zigzag":
            # R12 / R-ZIG-02: 锯齿形 B 浪终点不得越过 A 浪起点（不得回撤 100% 以上，等号允许）
            b_not_breach = (wb[2] >= wa[1]) if up else (wb[2] <= wa[1])
            row("R12", "通过" if b_not_breach else "违反",
                "锯齿形B浪终点 %g；A浪起点 %g（不得越过A浪起点，等号允许）" % (wb[2], wa[1]))
    else:
        row("R12", "待确认", "未提供B浪，暂无法验证回撤边界")

    if wc:
        # R25: C 浪必须与 A 浪同向
        c_up = wc[2] > wc[1]
        c_dir_ok = (c_up == up)
        row("R25-C", "通过" if c_dir_ok else "违反",
            "C浪方向必须与A浪同向（A浪 %s，C浪 %s）" % ("向上" if up else "向下", "向上" if c_up else "向下"))
        la, lc = abs(wa[2] - wa[1]), abs(wc[2] - wc[1])
        ratio = lc / la if la > 0 else 0
        row("R-FIB", "参考", "C浪/A浪长度比 = %.3f（经典比率 1.0 或 1.618）" % ratio)

    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="波浪规则数值检查（推动浪 R5/R6/R7/R17/R29；调整浪 R12/R25）")
    ap.add_argument("--wave", action="append", required=True, help="重复传入 标签:起点价:终点价")
    ap.add_argument("--pattern", choices=["impulse", "zigzag", "flat"], default="impulse", help="形态类型：impulse(默认)|zigzag|flat")
    ap.add_argument("--dir", choices=["up", "down"])
    args = ap.parse_args(argv)
    waves = [parse_wave(t) for t in args.wave]
    try:
        if args.pattern in ("zigzag", "flat"):
            records = evaluate_corrective(waves, pattern=args.pattern, direction=args.dir)
        else:
            records = evaluate(waves, args.dir)
    except ValueError as exc:
        raise SystemExit("[错误] " + str(exc)) from exc
    print("## Rule Check 数值判定（rule_check.py，R20 极端价位口径）\n")
    print("| 规则 | 判定 | 依据 |\n| --- | --- | --- |")
    for r in records:
        print("| {rule} | {status} | {basis} |".format(**r))
    print("\n形态、级别与内部完成状态须另行核对；这里只检查给定端点下的数值。")
    return int(any(r["status"] == "违反" for r in records))


if __name__ == "__main__":
    sys.exit(main())
