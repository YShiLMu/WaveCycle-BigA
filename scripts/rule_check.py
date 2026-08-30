#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rule Check 数值规则判定（workflow 第 2 步第 4 节，D31 口径）。

用途：对候选数法的推动浪端点做 R5/R6/R7/R17/R29 数值判定，输出
"通过/违反 + 数值依据"，消除手算误差与漏检。输入是**模型枚举出的候选
浪段端点价格**（按 R20 极端价位口径取自 swings.py 输出），不是 CSV。

判定范围（仅数值可判的 5 条，其余规则仍由模型逐条核对）：
  - R5  第 2 浪终点不得低于第 1 浪起点（下跌推动镜像：不得高于）
  - R6  第 3 浪不是 1/3/5 中最短
  - R7  第 4 浪终点不得进入第 1 浪价格区域（下跌镜像对称）
  - R17/R29 失败第 5 浪前提：第 5 浪终点未超越第 3 浪终点（ up：未创新高 /
    down：未创新低）——"子浪是否完整五浪"仍由模型确认，脚本只给位置事实
  形态类规则（R8–R16、R21–R28 等）与 R18 计数一致性不在此列，由模型判定。

用法（--wave 可重复，五浪全给判 5 条，只给 1–3 判 R5/R6，只给 1–4 判到 R7）：
    python rule_check.py --wave "1:100:160" --wave "2:160:130" \
                         --wave "3:130:220" --wave "4:220:185" --wave "5:185:178"

--wave 格式：标签:起点价:终点价（标签任意字符串；下跌推动照常给
"高→低"端点，脚本按第 1 浪方向自动镜像全部规则；--dir up/down 可显式指定）。

输出：markdown 表（规则|判定|依据）+ 缺浪提示；存在"违反"时退出码 1
（方案判"规则失效"由模型按 R19 执行，脚本只标数值事实）。
"""

import argparse
import sys


def parse_wave(text):
    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError("--wave 需为「标签:起点价:终点价」，收到：%r" % text)
    label = parts[0].strip()
    try:
        return label, float(parts[1]), float(parts[2])
    except ValueError:
        raise ValueError("--wave 价格段不是数字：%r" % text)


def get(waves, label):
    for w in waves:
        if w[0] == label:
            return w
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rule Check 数值规则判定（R5/R6/R7/R17/R29，D31）")
    ap.add_argument("--wave", action="append", required=True,
                    help="候选推动浪端点「标签:起点价:终点价」，可重复；至少 1-2-3")
    ap.add_argument("--dir", choices=["up", "down"], default=None,
                    help="推动方向（缺省按第 1 浪起点→终点自动识别）")
    args = ap.parse_args(argv)

    waves = [parse_wave(t) for t in args.wave]
    labels = [w[0] for w in waves]
    for need in ("1", "2", "3"):
        if need not in labels:
            raise SystemExit("[错误] 缺少第 %s 浪（--wave \"1:起点:终点\"）；R5/R6 需 1-2-3" % need)

    w1, w2, w3 = get(waves, "1"), get(waves, "2"), get(waves, "3")
    w4 = get(waves, "4")
    w5 = get(waves, "5")
    up = (w1[2] > w1[1]) if args.dir is None else (args.dir == "up")
    direction = "上升推动" if up else "下跌推动"

    print("## Rule Check 数值判定（rule_check.py，方向自动识别：%s，R20 极端价位口径）\n" % direction)
    print("| 规则 | 判定 | 依据 |")
    print("| --- | --- | --- |")
    violations = 0

    def row(rule, ok, basis):
        nonlocal violations
        print("| %s | %s | %s |" % (rule, "通过" if ok else "违反", basis))
        if not ok:
            violations += 1

    # R5：第 2 浪不破第 1 浪起点
    if up:
        row("R5", w2[2] > w1[1],
            "第 2 浪终点 %.3f %s 第 1 浪起点 %.3f" % (w2[2], ">" if w2[2] > w1[1] else "≤", w1[1]))
    else:
        row("R5", w2[2] < w1[1],
            "第 2 浪终点 %.3f %s 第 1 浪起点 %.3f" % (w2[2], "<" if w2[2] < w1[1] else "≥", w1[1]))

    # R6：第 3 浪不是最短（严格短于任一其他推动浪即违反）
    l1 = abs(w1[2] - w1[1])
    l3 = abs(w3[2] - w3[1])
    if w5:
        l5 = abs(w5[2] - w5[1])
        others = [l1, l5]
        ok6 = l3 >= min(others)
        row("R6", ok6,
            "浪长 |1|=%.3f、|3|=%.3f、|5|=%.3f —— 第 3 浪%s最短" %
            (l1, l3, l5, "并非" if ok6 else "是"))
    else:
        row("R6", l3 >= l1, "浪长 |1|=%.3f、|3|=%.3f（第 5 浪未提供，仅比 1/3）" % (l1, l3))

    # R7：第 4 浪不进第 1 浪价格区域
    if w4:
        if up:
            row("R7", w4[2] > w1[2],
                "第 4 浪终点 %.3f %s 第 1 浪终点（区域下沿）%.3f" % (w4[2], ">" if w4[2] > w1[2] else "≤", w1[2]))
        else:
            row("R7", w4[2] < w1[2],
                "第 4 浪终点 %.3f %s 第 1 浪终点（区域上沿）%.3f" % (w4[2], "<" if w4[2] < w1[2] else "≥", w1[2]))
    else:
        print("| R7 | 不适用 | 未提供第 4 浪 |")

    # R17/R29：失败第 5 浪位置前提
    if w5:
        if up:
            fail_pos = w5[2] <= w3[2]
            basis = "第 5 浪终点 %.3f %s 第 3 浪终点 %.3f（未创新高）" % \
                    (w5[2], "≤" if fail_pos else ">", w3[2])
        else:
            fail_pos = w5[2] >= w3[2]
            basis = "第 5 浪终点 %.3f %s 第 3 浪终点 %.3f（未创新低）" % \
                    (w5[2], "≥" if fail_pos else "<", w3[2])
        print("| R17/R29 | %s | %s；子浪是否完整五浪由模型确认（G12），满足才可标失败浪 |"
              % ("位置满足" if fail_pos else "位置不满足（第 5 浪已超越第 3 浪终点——非失败浪，按普通第 5 浪核对 R6）", basis))
    else:
        print("| R17/R29 | 不适用 | 未提供第 5 浪 |")

    print("\n形态类规则（R8–R16、R21–R28）与 R18 计数一致性、R25/R30 身份判定由模型逐条核对；"
          "存在'违反'时该方案按 R19 判规则失效，脚本只输出数值事实。")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
