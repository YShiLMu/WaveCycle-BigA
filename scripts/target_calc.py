#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双向价格目标计算。只演算给定基准，不识别形态或确认共振。

回撤从基准终点逆向计算；投射从显式锚点沿指定方向计算。
用法：target_calc.py --start 100 --end 200 --kind retracement
      target_calc.py --start 200 --end 100 --kind projection --anchor 140 --direction down
"""
import argparse
import json
import math
import sys

RETRACEMENTS = (0.382, 0.5, 0.618)
PROJECTIONS = (1.0, 1.618, 2.618)


def calculate(start, end, kind, ratios=None, anchor=None, direction=None):
    """返回原始目标；不舍入用于比较的数值，不从结果倒推选档。"""
    if kind not in ("retracement", "projection"):
        raise ValueError("kind须为retracement或projection")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in (start, end)) or start == end:
        raise ValueError("基准端点必须有限，且长度非零")
    length = abs(end - start)
    if kind == "retracement":
        if anchor is not None or direction is not None:
            raise ValueError("回撤由基准方向和终点确定，不接受另设锚点或方向")
        origin, sign = end, -1 if end > start else 1
        ratios = RETRACEMENTS if ratios is None else ratios
    else:
        if not isinstance(anchor, (int, float)) or isinstance(anchor, bool) or not math.isfinite(anchor):
            raise ValueError("投射须有有限锚点")
        if direction not in ("up", "down"):
            raise ValueError("投射须显式声明up/down方向")
        origin, sign = anchor, 1 if direction == "up" else -1
        ratios = PROJECTIONS if ratios is None else ratios
    if not math.isfinite(length) or not isinstance(ratios, (list, tuple)) or not ratios:
        raise ValueError("长度超出计算范围或倍率为空")
    results = []
    for ratio in ratios:
        if (not isinstance(ratio, (int, float)) or isinstance(ratio, bool)
                or not math.isfinite(ratio) or ratio <= 0):
            raise ValueError("倍率须为有限正数")
        price = origin + sign * length * ratio
        if not math.isfinite(price):
            raise ValueError("目标超出计算范围")
        results.append({"ratio": ratio, "price": price})
    return {"kind": kind, "start": start, "end": end, "length": length,
            "origin": origin, "direction": "up" if sign > 0 else "down", "values": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--kind", choices=["retracement", "projection"], required=True)
    parser.add_argument("--anchor", type=float)
    parser.add_argument("--direction", choices=["up", "down"])
    parser.add_argument("--ratio", type=float, action="append", help="重复指定倍率；省略用常用档位")
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    args = parser.parse_args(argv)
    try:
        result = calculate(args.start, args.end, args.kind, args.ratio, args.anchor, args.direction)
    except ValueError as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    else:
        print("方向=%s；基准长度=%g；起算价=%g" % (result["direction"], result["length"], result["origin"]))
        for v in result["values"]:
            print("%g倍 → %.8g" % (v["ratio"], v["price"]))
        print("条件演算；端点来源、结构前提及目标合法范围须另核。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
