#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elliott Wave K 线图 + 浪型标注绘制脚本。

用法（命令行）：
    python ew_chart.py --csv data.csv --out 主方案_第4浪平台形.png ^
        --title "日线级别 · Intermediate · 主方案：第 4 浪平台形（Flat）" ^
        --waves "1:start,end:Impulse" "2:start,end:Correction" ...

CSV 列：date,open,high,low,close（date 形如 2026-08-08）。
浪段参数格式：<标注>:<起始索引>:<结束索引>:<形态备注>，索引为 CSV 行号（0 起）。
失效价位参数格式：<价格>:<标签>，如 "160:跌破 160（第 1 浪高点，R7）即失效"。
本脚本只依赖 matplotlib；mplfinance 可用时优先用于 K 线主体。
"""

import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")  # 无界面后端，适配脚本/CI
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import pandas as pd

try:
    import mplfinance as mpf

    HAS_MPF = True
except Exception:  # pragma: no cover
    HAS_MPF = False

# 中文字体：优先微软雅黑/黑体，避免 DejaVu 缺字形（中文标注变方块）
from matplotlib import font_manager

_CJK_FONTS = ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"]
_found = None
for _fname in _CJK_FONTS:
    if any(_fname.lower() in (f.name or "").lower()
           for f in font_manager.fontManager.ttflist):
        _found = _fname
        break
if _found:
    plt.rcParams["font.sans-serif"] = [_found] + plt.rcParams.get(
        "font.sans-serif", [])
    plt.rcParams["axes.unicode_minus"] = False  # 修复中文负号显示
else:  # pragma: no cover
    print("[警告] 未找到中文字体，中文标注可能显示为方块", file=sys.stderr)


def load_ohlc(csv_path):
    """读取 CSV，返回带 datetime 索引的 DataFrame。"""
    df = pd.read_csv(csv_path)
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV 缺少列: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def _fmt_price(v):
    """价格格式化：整数去小数点，非整数保留两位。"""
    if abs(v - round(v)) < 1e-9:
        return f"{v:.0f}"
    return f"{v:.2f}"


def _draw_candles(ax, df, last_n=None):
    """在指定坐标轴上绘制蜡烛图（原生 matplotlib 实现，含影线）。"""
    if last_n is not None:
        df = df.tail(last_n)
    x = range(len(df))
    width = 0.6
    for i, (_, row) in enumerate(df.iterrows()):
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        up = c >= o
        color = "#d32f2f" if up else "#1e88e5"  # 红涨绿跌（中国习惯）
        ax.plot([i, i], [l, h], color=color, linewidth=1, zorder=2)  # 影线
        ax.add_patch(
            Rectangle((i - width / 2, min(o, c)), width, abs(c - o) or 1e-6,
                      facecolor=color, edgecolor=color, zorder=3)
        )
    ax.set_xlim(-1, len(df))
    # 时间刻度：稀疏显示，避免重叠
    ticks = list(range(0, len(df), max(1, len(df) // 6)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([df.index[i].strftime("%Y-%m-%d") for i in ticks],
                       rotation=30, ha="right", fontsize=10)
    return df


def draw_chart(df, out_path, title, waves, invalids, current_price=None,
               fib_zones=None, last_n=None, levels=None, font_scale=1.0,
               gann_fans=None):
    """绘制单方案 K 线图并保存 PNG。

    waves: [(label, start_idx, end_idx, form_note), ...]
    invalids: [(price, label), ...]
    fib_zones: [(lo, hi, label), ...]
    levels: [(price, label), ...]  # 关键阻力/支撑（蓝色虚线，非失效）
    gann_fans: [(anchor_idx, anchor_price, scale, direction), ...]
        # 江恩角度线扇形（青绿色）；scale = 每根 K 线 1 单位价格（刻度按项目默认口径 D23 分档），
        # direction: "up"（低点出发向上，默认）/ "down"（高点出发向下）
    font_scale: 字号缩放（放大图建议 1.2–1.4，保证子浪标注清晰）
    """
    plot_df = df.tail(last_n) if last_n is not None else df
    base = len(df) - len(plot_df)  # 索引偏移（浪段索引基于全量 CSV 行号）

    # 宽幅图：18:7 横向铺满，适配网页查看器
    fig, ax = plt.subplots(figsize=(18, 7))
    # 统一使用原生蜡烛图：mplfinance 的 ax 模式会重置坐标/覆盖后续 annotate，
    # 导致浪段与价位标注不可见；原生实现标注稳定（已在多案例实测）。
    _draw_candles(ax, plot_df)

    fs = font_scale
    ax.set_title(title, fontsize=17 * fs, pad=14)
    ax.set_ylabel("价格", fontsize=13 * fs)
    ax.grid(True, linestyle="--", alpha=0.4)

    # 1) 浪段标注：连线 + 标签 + 形态备注（带引线，避免遮挡）
    for label, s0, e0, note in waves:
        s = s0 - base
        e = e0 - base
        if s < 0 or e < 0 or s >= len(plot_df) or e >= len(plot_df):
            print(f"[警告] 浪段 {label} 索引越界，跳过", file=sys.stderr)
            continue
        xs, xe = s, e
        # 以收盘价方向判定涨跌，锚定极端价位：上行浪 low(start)->high(end)，下行浪 high(start)->low(end)
        up = plot_df.iloc[e]["close"] >= plot_df.iloc[s]["close"]
        ys = plot_df.iloc[s]["low"] if up else plot_df.iloc[s]["high"]
        ye = plot_df.iloc[e]["high"] if up else plot_df.iloc[e]["low"]
        ax.annotate(
            "", xy=(xe, ye), xytext=(xs, ys),
            arrowprops=dict(arrowstyle="-|>", color="#333333", lw=1.4,
                            connectionstyle="arc3,rad=0.12"),
            zorder=4,
        )
        # 标签放终点上方，形态备注放终点下方（引线短）
        label_y = ye + (plot_df["high"].max() - plot_df["low"].min()) * 0.03
        ax.annotate(label, xy=(xe, ye), xytext=(xe, label_y),
                    fontsize=15 * fs, fontweight="bold", ha="center",
                    arrowprops=dict(arrowstyle="-", color="#555555", lw=0.7),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#888888",
                              alpha=0.85, lw=0.6), zorder=8)
        note_y = ye - (plot_df["high"].max() - plot_df["low"].min()) * 0.05
        ax.annotate(note, xy=(xe, ye), xytext=(xe, note_y),
                    fontsize=12 * fs, color="#555555", ha="center",
                    arrowprops=dict(arrowstyle="-", color="#aaaaaa", lw=0.6),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none",
                              alpha=0.75), zorder=8)

    # 2) 关键价位标注
    price_floor = plot_df["low"].min()
    price_ceil = plot_df["high"].max()
    span = price_ceil - price_floor or 1.0
    x_last = len(plot_df) - 1

    # 失效价位：红色虚线 + 价格标签 + 规则编号
    for price, label in invalids:
        ax.axhline(price, color="#d32f2f", linestyle="--", linewidth=1.4, zorder=6)
        ax.text(x_last, price, f" {label}", color="#d32f2f", fontsize=12 * fs,
                va="bottom", ha="right", zorder=7,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))

    # 关键阻力/支撑：蓝色点划线（区别于红色失效价位）
    for price, label in levels or []:
        ax.axhline(price, color="#1565c0", linestyle="-.", linewidth=1.1, zorder=6)
        ax.text(x_last, price, f" {label}", color="#1565c0", fontsize=12 * fs,
                va="bottom", ha="right", zorder=7,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))

    # 当前价格：水平实线
    if current_price is not None:
        ax.axhline(current_price, color="#2e7d32", linestyle="-", linewidth=1.2, zorder=6)
        ax.text(x_last, current_price, f" 当前 {_fmt_price(current_price)}",
                color="#2e7d32", fontsize=12 * fs, va="bottom", ha="right", zorder=7,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))

    # 比率目标区：浅色区间
    if fib_zones:
        for lo, hi, label in fib_zones:
            lo = max(lo, price_floor - span * 0.1)
            hi = min(hi, price_ceil + span * 0.1)
            ax.axhspan(lo, hi, color="#ffb74d", alpha=0.18, zorder=5)
            ax.text(x_last * 0.5, hi, label, color="#e65100", fontsize=12 * fs,
                    ha="right", va="bottom")

    # 江恩角度线：青绿色扇形（可选叠加；配色区别于红色失效价位与蓝色支撑阻力）
    for a0, p0, scale, direction in gann_fans or []:
        a = a0 - base
        if a < 0 or a >= len(plot_df):
            print("[警告] 江恩角度线起点索引越界，跳过", file=sys.stderr)
            continue
        sign = -1.0 if direction == "down" else 1.0
        x_end = len(plot_df) - 1
        for ratio, lw, ls in ((2.0, 0.8, ":"), (1.0, 1.6, "-."), (0.5, 0.8, ":"),
                              (1.0 / 3.0, 0.8, ":"), (0.25, 0.8, ":")):
            y_end = p0 + sign * ratio * scale * (x_end - a)
            ax.plot([a, x_end], [p0, y_end], color="#00897b", linestyle=ls,
                    linewidth=lw, alpha=0.9, zorder=5)
            label = ("%g×1" % ratio) if ratio >= 1 else ("1×%g" % (1.0 / ratio))
            ax.text(x_end, y_end, " 江恩" + label, color="#00897b",
                    fontsize=10 * fs, va="bottom", ha="right", zorder=7)

    # 3) 图例：右下角注明方案名
    scheme = title.split("·")[-1].strip() if "·" in title else title
    ax.text(0.985, 0.02, scheme, transform=ax.transAxes, fontsize=13 * fs,
            ha="right", va="bottom", bbox=dict(boxstyle="round", fc="white",
                                               ec="#999999", alpha=0.9))

    fig.tight_layout(pad=0.4)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # 紧凑裁边：坐标轴铺满图片，四周无多余白边
    fig.savefig(out_path, dpi=180, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    # 验证输出文件存在且非空
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"图片保存失败或为空: {out_path}")
    print(f"[OK] 已保存: {out_path} ({os.path.getsize(out_path)} bytes)")


def parse_wave_arg(s):
    """解析 '标签:起点:终点:备注'。"""
    parts = s.split(":", 3)
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"浪段格式应为 标签:起点:终点:备注，收到: {s}")
    return (parts[0], int(parts[1]), int(parts[2]), parts[3])


def parse_price_arg(s):
    """解析 '价格:标签'。"""
    parts = s.split(":", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"价位格式应为 价格:标签，收到: {s}")
    return (float(parts[0]), parts[1])


def parse_fib_arg(s):
    """解析 '低:高:标签'。"""
    parts = s.split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"目标区格式应为 低:高:标签，收到: {s}")
    return (float(parts[0]), float(parts[1]), parts[2])


def parse_gann_arg(s):
    """解析 '起点索引:起点价格:刻度[:方向(up|down)]'。"""
    parts = s.split(":")
    if len(parts) not in (3, 4):
        raise argparse.ArgumentTypeError(
            f"江恩角度线格式应为 起点索引:起点价格:刻度[:方向]，收到: {s}")
    direction = parts[3] if len(parts) == 4 else "up"
    if direction not in ("up", "down"):
        raise argparse.ArgumentTypeError(f"江恩方向只支持 up/down，收到: {direction}")
    return (int(parts[0]), float(parts[1]), float(parts[2]), direction)


def main():
    p = argparse.ArgumentParser(description="Elliott Wave K 线图绘制")
    p.add_argument("--csv", required=True, help="OHLC CSV（date,open,high,low,close）")
    p.add_argument("--out", required=True, help="输出 PNG 路径")
    p.add_argument("--title", required=True, help="图标题（含分析级别与方案名）")
    p.add_argument("--waves", nargs="*", type=parse_wave_arg, default=[],
                   help="浪段标注：标签:起点:终点:形态备注")
    p.add_argument("--invalid", nargs="*", type=parse_price_arg, default=[],
                   help="失效价位：价格:标签（含规则编号）")
    p.add_argument("--level", nargs="*", type=parse_price_arg, default=[],
                   help="关键阻力/支撑：价格:标签（蓝色点划线，区别于失效价位）")
    p.add_argument("--current", type=float, default=None, help="当前价格")
    p.add_argument("--fib", nargs="*", type=parse_fib_arg, default=[],
                   help="斐波那契目标区：低:高:标签")
    p.add_argument("--last", type=int, default=None, help="只绘制最近 N 根 K 线")
    p.add_argument("--gann", nargs="*", type=parse_gann_arg, default=[],
                   help="江恩角度线扇形（可选叠加）：起点索引:起点价格:刻度[:方向up/down]；"
                        "刻度 = 每根 K 线 1 单位价格（分档见项目默认口径 D23），须披露")
    p.add_argument("--font-scale", type=float, default=1.0,
                   help="字号缩放（放大图建议 1.2–1.4）")
    args = p.parse_args()

    df = load_ohlc(args.csv)
    draw_chart(df, args.out, args.title, args.waves, args.invalid,
               current_price=args.current, fib_zones=args.fib, last_n=args.last,
               levels=args.level, font_scale=args.font_scale,
               gann_fans=args.gann)


if __name__ == "__main__":
    main()
