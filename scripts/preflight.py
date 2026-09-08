#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight 单入口流水线——分析前提一次产出（D32 口径）。

把 workflow 第 1 步的三个必跑脚本串成一条命令，减少模型多次调用往返：
  1. data_check.py        数据自检表 + 数据基准四要素（D28）
  2. swings.py --dow      摆动点/行索引/斐波比率 + 道氏状态读数（D30）
  3. key_levels.py        三类技术分析锚点（D27，R32）

失败策略：data_check 退出码非 0（存在"不通过"项）**立即终止**，不跑后续
脚本（与 01 分析市场 1.5 节"禁止带病数据进入数浪"一致）；其余脚本失败
也终止并透传退出码。

用法：
    python preflight.py --csv data.csv --source 腾讯fqkline --fq qfq
                        [--k 5] [--start 日期] [--end 日期] [--weekly]
                        [--no-dow] [--no-key-levels] [--key-levels-args "..."]
                        [--compact / --no-compact]

紧凑模式（--compact，默认开启）：swings 只打印最近 40 个摆动点（--tail 40，
省略行数由 swings 披露）；key_levels 前高/前低簇封顶 30 条（key_levels 本体
口径，按触及次数降序、同次数按距最新收盘升序截断）。--no-compact 取全量
（swings 不加 --tail、key_levels 补 --max-levels 0，考古/复核用）；显式
--tail 与 --key-levels-args 优先于紧凑默认。

--key-levels-args 原样透传给 key_levels.py（如补充口径
"--trend-threshold 1.0 --window 250"）。输出为各脚本的 stdout 顺序拼接。
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run_script(name, cmd_args):
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run([sys.executable, os.path.join(HERE, name)] + cmd_args,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return proc.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description="preflight：数据自检 + 摆动/道氏 + 锚点一次产出（D32）")
    ap.add_argument("--csv", required=True, help="行情 CSV 路径")
    ap.add_argument("--source", default="", help="数据源标注（透传 data_check，缺判不通过）")
    ap.add_argument("--fq", default="", help="复权口径标注 none/qfq/hfq（透传 data_check，缺判不通过）")
    ap.add_argument("--k", type=int, default=5, help="swings 分形窗口（默认 5）")
    ap.add_argument("--start", default=None, help="swings 分析起始日期（索引基准不变）")
    ap.add_argument("--end", default=None, help="swings 分析结束日期")
    ap.add_argument("--weekly", action="store_true", help="swings 周线聚合（道氏主要趋势口径）")
    ap.add_argument("--tail", type=int, default=None, help="swings 只打印最近 N 个摆动点")
    ap.add_argument("--no-dow", action="store_true", help="跳过道氏状态读数")
    ap.add_argument("--no-key-levels", action="store_true", help="跳过 key_levels 锚点")
    ap.add_argument("--key-levels-args", default="",
                    help="透传 key_levels.py 的附加参数（一个字符串，如 \"--trend-threshold 1.0\"；"
                         "按空格切分，不支持含空格的参数值）")
    ap.add_argument("--compact", dest="compact", action="store_true", default=True,
                    help="紧凑模式（默认开启）：swings 只打印最近 40 个摆动点、key_levels 前高/前低簇"
                         "封顶 30 条（省略行数均在输出中披露；显式 --tail / --key-levels-args 优先）")
    ap.add_argument("--no-compact", dest="compact", action="store_false",
                    help="关闭紧凑模式：swings 全量摆动点 + key_levels 簇全量（考古/复核用）")
    args = ap.parse_args(argv)

    print("== preflight 1/3：data_check（数据自检 + 四要素，D28）==")
    dc_args = ["--csv", args.csv]
    if args.source:
        dc_args += ["--source", args.source]
    if args.fq:
        dc_args += ["--fq", args.fq]
    code = run_script("data_check.py", dc_args)
    if code != 0:
        print("\n[preflight 终止] data_check 存在不通过项——禁止带病数据进入数浪（01 分析市场 1.5）。"
              "退回取数或降级标注后重跑。")
        return code

    print("\n== preflight 2/3：swings（摆动点 + 行索引%s，D30）=="
          % (" + 道氏状态" if not args.no_dow else ""))
    sw_args = ["--csv", args.csv, "--k", str(args.k)]
    if args.start:
        sw_args += ["--start", args.start]
    if args.end:
        sw_args += ["--end", args.end]
    if args.weekly:
        sw_args.append("--weekly")
    if args.tail is not None:
        sw_args += ["--tail", str(args.tail)]
    elif args.compact:
        sw_args += ["--tail", "40"]  # compact 默认：只打印最近 40 个摆动点
    if not args.no_dow:
        sw_args.append("--dow")
    code = run_script("swings.py", sw_args)
    if code != 0:
        print("\n[preflight 终止] swings 失败。")
        return code

    if not args.no_key_levels:
        print("\n== preflight 3/3：key_levels（三类技术分析锚点，D27/R32）==")
        kl_args = ["--csv", args.csv]
        if args.key_levels_args:
            kl_args += args.key_levels_args.split()
        if not args.compact and "--max-levels" not in args.key_levels_args:
            kl_args += ["--max-levels", "0"]  # --no-compact：簇全量（考古/复核）
        code = run_script("key_levels.py", kl_args)
        if code != 0:
            print("\n[preflight 终止] key_levels 失败。")
            return code

    if args.compact:
        print("\n（compact 默认口径：swings --tail 40、key_levels --max-levels 30，省略行数见各节披露行；"
              "全量用 --no-compact，或单项 --tail 0 / --key-levels-args \"--max-levels 0\"）")
    print("\n== preflight 完成：分析前提就绪，可进入 02 数浪"
          "（趋势方向与大级别框架由模型按道氏读数 + 结构判定输出，锚点禁反转已定方向，R32）==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
