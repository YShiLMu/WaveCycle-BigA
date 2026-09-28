#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Power Rating 功率评级查询（Neely 修正浪量化评级，16 口径 / D35）。

用途：根据**已完成修正浪的类型** → 输出该修正浪的功率评级（+3…0…-3，按
"向上完成 / 向下完成"两种方向）+ "适用条件下的后势参考"。
——类型由模型数浪确定（脚本不识别形态），脚本只做查表，不验证完成状态、压缩或父级位置。

用法：
    python power_rating.py --type "Double Zigzag"
    python power_rating.py --type "Zigzag"

--type 取值（16 功率评级表所列 19 种）：
    Triple Zigzag / Triple Combination / Triple Flat
    Double Zigzag / Double Combination / Double Flat
    Elongated Zigzag / Elongated Flat / Zigzag
    B-Failure / Common / C-Failure
    Irregular / Irregular Failure
    Double Three / Triple Three / Running Correction
    Double Three-Running / Triple Three-Running

输出：markdown 表（类型 | 向上完成 | 向下完成 | 后势参考）+ 适用条件。
依据：Mastering Elliott Wave ch10 页10-1–10-6；0无固定回撤值，非零须分方向和变体。
"""

import argparse
import sys

# (类型, 向上完成评级, 向下完成评级)
RATINGS = [
    ("Triple Zigzag", 3, -3),
    ("Triple Combination", 3, -3),
    ("Triple Flat", 3, -3),
    ("Double Zigzag", 2, -2),
    ("Double Combination", 2, -2),
    ("Double Flat", 2, -2),
    ("Elongated Zigzag", 1, -1),
    ("Elongated Flat", 1, -1),
    ("Zigzag", 0, 0),
    ("B-Failure", 0, 0),
    ("Common", 0, 0),
    ("C-Failure", -1, 1),
    ("Irregular", -1, 1),
    ("Irregular Failure", -2, 2),
    ("Double Three", -2, 2),
    ("Triple Three", -2, 2),
    ("Running Correction", -3, 3),
    ("Double Three-Running", -3, 3),
    ("Triple Three-Running", -3, 3),
]

def retrace_label(rating):
    """传入表中向上完成列；相反完成方向使用对应相反符号，条件见16/D35。"""
    if rating == 0:
        return "无固定回撤比例（可超过100%）"
    if rating < 0:
        return "反向力量情景，查具体变体；不套绝对值回撤上限"
    if rating == 1:
        return "适用位置下一般不超过约90%"
    if rating == 2:
        return "适用位置下一般不超过约80%"
    return "适用位置下一般约60–70%"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Power Rating 功率评级查询（16 / D35）")
    ap.add_argument("--type", required=True, help="修正浪类型，如 \"Double Zigzag\"")
    args = ap.parse_args(argv)

    key = args.type.strip()
    hit = next((r for r in RATINGS if r[0].lower() == key.lower()), None)
    if hit is None:
        raise SystemExit("[错误] 未知修正浪类型：%r（可用：%s）"
                         % (args.type, ", ".join(r[0] for r in RATINGS)))

    name, up, down = hit
    print("## Power Rating 功率评级（power_rating.py，16 口径 / D35）\n")
    print("| 类型 | 向上完成 | 向下完成 | 后势参考（须核对方向和位置） |")
    print("| --- | --- | --- | --- |")
    print("| %s | %+d | %+d | %s |" % (name, up, down, retrace_label(up)))
    print("\n> 以下正负分支为项目保守解释，不是原书逐字算法；原书一般幅度描述与具体变体预期须合看。幅度参照仅用于向上正评级／向下负评级且位置适用的情景；"
          "向上负评级／向下正评级须查具体变体，例如 C-Failure、Irregular Failure 有完全回撤预期。")
    print("\n> 先压缩并确认最大已完成形态及末段完成方向；Triangle 或 Terminal 的腿"
          "不一定传递评级含义，不统一归零。同级完全回撤且后者更接近0只提示复查，不能单独定形。"
          "Power Rating 不并入8因子权重（D25），也不产生Rule失效价位。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
