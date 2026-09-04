#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elliott Wave K 线图 + 浪型标注绘制脚本。

用法（命令行）：
    python ew_chart.py --csv data.csv --out 主方案_第4浪平台形.png ^
        --title "日线级别 · Intermediate · 主方案：第 4 浪平台形（Flat）" ^
        --waves "1:start,end:Impulse" "2:start,end:Correction:down" ^
        --path "[1]:4165:4174:4178:4223:4295:4484" ^
        --channel "4174:4223:4178" ^
        --invalid "160:跌破 160（第 1 浪高点，R7）即失效" ^
        --theme dark

CSV 列：date,open,high,low,close[,volume]（date 形如 2026-08-08；读取时强制校验
OHLC 合理性：high ≥ low ≥ 0、open/close 落在 [low, high]、日期升序无重复，坏数据报错）。
浪段参数格式：<标注>:<起始索引>:<结束索引>:<形态备注>[:方向up/down/auto]，索引为 CSV 行号（0 起）；
方向默认 auto = 按端点极端价位判定（终点高/低均高于起点 → 上行，均低 → 下行，
区间重叠时回退收盘价比较，与 R20 极端价位口径一致），显式 up/down 可覆盖。
--path 连续浪路径：<标注>:<索引>:<索引>... —— 把一组端点按序连成一条带箭头的连续折线
（亮色细线，未走完段灰虚线），浪型文字由底部注释区呈现，用于呈现 1-2-3-4-5-A-B-C 完整路径。
--channel 推动浪平行通道：<1浪高点索引>:<3浪高点索引>:<2浪低点索引> —— 连接 1、3 浪高点
为上轨，过 2 浪低点画平行线为下轨。
--theme dark（默认）/ light：深色画布亮色连线，或旧浅色。
失效价位参数格式：<价格>:<标签>，如 "160:跌破 160（第 1 浪高点，R7）即失效"。
江恩扇形：--gann "起点索引:起点价格:刻度[:方向]"；加 --gann-auto-scale 时省略刻度
（格式 "起点索引:起点价格[:方向]"），按项目默认口径 D23 自动分档，--gann-index 表示
指数点位（固定刻度 50）。
本脚本只依赖 matplotlib；K 线主体统一使用原生 matplotlib 蜡烛图实现，
不依赖 mplfinance（其 ax 模式会重置坐标、覆盖浪型标注，已弃用）。
"""

import argparse
import os
import sys

import pandas as pd

import matplotlib

matplotlib.use("Agg")  # 无界面后端，适配脚本/CI
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# 中文字体：优先微软雅黑/黑体，避免 DejaVu 缺字形（中文标注变方块）
from matplotlib import font_manager

from ohlc_io import load_ohlc
from naming import CHART_VIEWS, SCHEME_NAMES, chart_png

# ---------------------------------------------------------------------------
# 主题（深色为默认）：深色画布下红涨用亮红、绿跌用亮蓝绿，连线用白/亮青，
# 保证 K 线与浪路径在深色背景清晰可见。--theme light 可退回旧浅色。
# ---------------------------------------------------------------------------
THEMES = {
    "dark": {
        "fig": "#0e1117", "ax": "#0e1117", "grid": "#2b3038",
        "text": "#d7dae0", "tick": "#aab0bb", "up": "#ff5b5b",
        "down": "#3fb6a8", "path": "#f5f5f5", "path2": "#4dd0e1",
        "channel": "#4dd0e1", "frame": "#3a4149", "note": "#b8c0cc",
        "label_fc": "#1a2029", "ref_hi": "#4fc3f7", "resist": "#81d4fa",
        "invalid": "#ff7043", "current": "#66bb6a", "fib": "#ffb74d",
        "gann": "#009688",
    },
    "light": {
        "fig": "#ffffff", "ax": "#ffffff", "grid": "#dddddd",
        "text": "#111111", "tick": "#555555", "up": "#d32f2f",
        "down": "#1e88e5", "path": "#333333", "path2": "#1565c0",
        "channel": "#00897b", "frame": "#888888", "note": "#555555",
        "label_fc": "#ffffff", "ref_hi": "#1565c0", "resist": "#1565c0",
        "invalid": "#d32f2f", "current": "#2e7d32", "fib": "#ffb74d",
        "gann": "#00897b",
    },
}

# 底部注释区（左=线的注释，右=浪型）统一排版参数：
#   _BOTTOM_Y0     —— 两块第一行统一 y（贴近注释块顶部=贴近主图，不碰坐标轴/日期）
#   _BOTTOM_ROW_H  —— 行距下限（行数少时的默认行距；行数多时不压缩行距，
#                    而是按 _BOTTOM_ROW_IN/行 加高画布，见 _bottom_layout）
#   _BOTTOM_FS     —— 所有文字统一字号（固定 13pt，不随 font_scale 缩放）
#   _BOTTOM_ROW_IN —— 每行占用的画布英寸数（按 13pt 字号+bbox 内边距定 0.35）
_BOTTOM_Y0 = 0.93
_BOTTOM_ROW_H = 0.13
_BOTTOM_FS = 13
_BOTTOM_ROW_IN = 0.35

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


def _fmt_price(v):
    """价格格式化：整数去小数点，非整数保留两位。"""
    if abs(v - round(v)) < 1e-9:
        return f"{v:.0f}"
    return f"{v:.2f}"


def _label_level(lb):
    """浪标签层级：连字符段数+1。1→1级、1-1→2级、1-1-1→3级（标注"1-1-1"式多级子浪）。"""
    return str(lb).count("-") + 1


def _text_units(s):
    """估算文本宽度单位：CJK 全角字符计 2、其余计 1（用于底部列宽按比例分配）。"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def _bottom_layout(paths, waves, pivots, levels, invalids, current_price, channels, fs):
    """预计算底部注释区所需行数与画布尺寸（在建 figure 前调用）。

    行距不压缩：行数多时按 _BOTTOM_ROW_IN/行 加高底部注释区、同步加高整张画布，
    保证文字永不溢出/叠行（最多列行数 → bottom_in = 0.35 + 行数 × 行高英寸）。
    返回 (fig_h, main_in, bottom_in, row_h_frac, bottom_rows)：
    fig_h 画布总高(英寸)，row_h_frac 为底部坐标轴内每行的分数行距。
    """
    n_lvl = {1: 0, 2: 0}
    for idxs, labels in paths or []:
        seq = labels if len(labels) == len(idxs) else list(labels) * len(idxs)
        for lb in seq:
            if lb:
                lv = _label_level(lb)
                if lv in n_lvl:
                    n_lvl[lv] += 1
    for label, *_rest in waves or []:
        if label:
            lv = _label_level(label)
            if lv in n_lvl:
                n_lvl[lv] += 1
    # 浪型区两列：大级别列 = pivots + 1级子浪 + 当前价；2级列 = 2级子浪（无列标题行）
    wave_col1 = len(pivots or []) + n_lvl[1] + (1 if current_price is not None else 0)
    wave_col2 = n_lvl[2]
    wave_rows = max(wave_col1, wave_col2)
    legend_rows = (len(levels or []) + len(invalids or [])
                   + (1 if current_price is not None else 0) + (2 if channels else 0))
    bottom_rows = max(wave_rows, legend_rows, 3)
    row_in = _BOTTOM_ROW_IN
    bottom_in = 0.35 + bottom_rows * row_in
    main_in = 8.4
    fig_h = main_in + bottom_in + 1.1  # 标题/边距余量
    row_h_frac = row_in / bottom_in
    return fig_h, main_in, bottom_in, row_h_frac, bottom_rows


def _level_color(lb, t):
    """按标签层级取配色：1级白、2级青、3级橙（显眼）、4级红；层级越高越突出，与底部浪型区对应。"""
    key = {1: "path", 2: "path2", 3: "fib", 4: "up"}.get(_label_level(lb), "path")
    return t[key]


def _seg_direction(plot_df, s, e):
    """段方向判定（R20 极端价位口径）：终点 high/low 均高于起点 → 上行（True），
    均低于起点 → 下行（False），区间重叠时回退收盘价比较。
    --waves 的 auto 与 --path 的峰谷判定共用，禁止另写判向逻辑。s/e 为 plot_df 内部索引。"""
    hs, ls = plot_df.iloc[s]["high"], plot_df.iloc[s]["low"]
    he, le = plot_df.iloc[e]["high"], plot_df.iloc[e]["low"]
    if he > hs and le > ls:
        return True
    if he < hs and le < ls:
        return False
    return bool(plot_df.iloc[e]["close"] >= plot_df.iloc[s]["close"])


def _draw_candles(ax, df, last_n=None, t=THEMES["dark"]):
    """在指定坐标轴上绘制蜡烛图（原生 matplotlib 实现，含影线）。

    t: 主题字典（THEMES["dark"] 或 THEMES["light"]）。深色下红涨用亮红、
    绿跌用亮蓝绿，保证对比度。
    """
    if last_n is not None:
        df = df.tail(last_n)
    x = range(len(df))
    width = 0.6
    up_c, down_c = t["up"], t["down"]
    for i, (_, row) in enumerate(df.iterrows()):
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        up = c >= o
        color = up_c if up else down_c  # 红涨绿跌（中国习惯）
        ax.plot([i, i], [l, h], color=color, linewidth=1, zorder=2)  # 影线
        ax.add_patch(
            Rectangle((i - width / 2, min(o, c)), width, abs(c - o) or 1e-6,
                      facecolor=color, edgecolor=color, zorder=3)
        )
    ax.set_xlim(-1, len(df))
    # 时间刻度：稀疏显示，避免重叠；横排（rotation=0），标签放 X 轴下方
    ticks = list(range(0, len(df), max(1, len(df) // 6)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([df.index[i].strftime("%Y-%m-%d") for i in ticks],
                       rotation=0, ha="center", fontsize=10, va="top")


def draw_chart(df, out_path, title, waves, invalids, current_price=None,
               fib_zones=None, last_n=None, levels=None, font_scale=1.0,
               gann_fans=None, theme="dark", paths=None, channels=None,
               pivots=None, start=None):
    """绘制单方案 K 线图并保存 PNG。

    waves: [(label, start_idx, end_idx, form_note, direction), ...]
        # direction: "up"/"down"/"auto"（auto 按端点极端价位判定，见 _wave 判向逻辑）
    invalids: [(price, label), ...]
    fib_zones: [(lo, hi, label), ...]
    levels: [(price, label), ...]  # 关键阻力/支撑（蓝色虚线，非失效）
    gann_fans: [(anchor_idx, anchor_price, scale, direction), ...]
        # 江恩角度线扇形（青绿色）；scale = 每根 K 线 1 单位价格（刻度按项目默认口径 D23 分档），
        # direction: "up"（低点出发向上，默认）/ "down"（高点出发向下）
    font_scale: 字号缩放（全景图子浪标注建议 1.2–1.4，保证缩放后子浪清晰）
    theme: "dark"（默认）/ "light"。深色画布下蜡烛与连线改用亮色系。
    paths: [([idx_a, idx_b, ...], labels), ...]  # 连续浪路径：按索引顺序把端点
        # 连成一条带箭头折线（亮色，线宽 0.9px 半透明；最后一段未走完为灰虚线），
        # 浪型文字由底部注释区呈现。labels 长度=n 为逐点标签，长度=1 自动序号。
    pivots: [(idx, big_label[, peak/trough]), ...]  # 大级别浪标注（[I][II][III]…），
        # 价格/日期实时取端点极值，呈现在底部浪型区左列，与子浪编号区分级别。
    channels: [(idx1_hi, idx3_hi, idx2_low), ...]  # 推动浪平行通道（常规通道）：
        # 连接 1 浪高点(idx1_hi) 与 3 浪高点(idx3_hi) 的直线为上轨，
        # 过 2 浪低点(idx2_low) 画与上轨平行的下轨。
    """
    # 观察窗口：--start 定左界（起画点，原始 CSV 行号），--last 定尾部根数；start 在 last 前应用
    plot_df = df
    if start is not None:
        plot_df = plot_df.iloc[start:]
    if last_n is not None:
        plot_df = plot_df.tail(last_n)
    base = len(df) - len(plot_df)  # 索引偏移（浪段索引基于全量 CSV 行号）

    t = THEMES.get(theme, THEMES["dark"])

    fs = font_scale
    # 宽幅图（含底部注释带）：主图区 + 下方注释区。
    # 底部行距不压缩：先按输入（pivots/paths/waves/levels/invalids…）预估最多行数，
    # 行数多则按 _BOTTOM_ROW_IN/行 加高画布（_bottom_layout），文字永不叠行。
    fig_h, main_in, bottom_in, row_h, _brows = _bottom_layout(
        paths, waves, pivots, levels, invalids, current_price, channels, fs)
    fig = plt.figure(figsize=(18, fig_h))
    # 布局：主图跨全宽（只画线，不放任何文字）。
    #   下方 2 块：左 = 平行线注释（ax_legend）；右 = 浪型区（ax_waves，内部大浪左列+小浪右列）。
    #   大浪/小浪行距各自独立、互不干涉；第一行 y 统一用 _BOTTOM_Y0。
    gs = fig.add_gridspec(2, 2, height_ratios=[main_in, bottom_in], hspace=0.08, wspace=0.05,
                          width_ratios=[1.0, 1.6])
    ax = fig.add_subplot(gs[0, :])
    ax_legend = fig.add_subplot(gs[1, 0])
    ax_waves = fig.add_subplot(gs[1, 1])
    fig.patch.set_facecolor(t["fig"])
    ax.set_facecolor(t["ax"])
    ax_legend.set_facecolor(t["ax"])
    ax_waves.set_facecolor(t["ax"])
    # 统一使用原生蜡烛图：mplfinance 的 ax 模式会重置坐标/覆盖后续 annotate，
    # 导致浪段与价位标注不可见；原生实现标注稳定（已在多案例实测）。
    _draw_candles(ax, plot_df, t=t)

    ax.set_title(title, fontsize=17 * fs, pad=14, color=t["text"])
    ax.set_ylabel("价格", fontsize=13 * fs, color=t["text"])
    ax.grid(True, linestyle="--", alpha=0.4, color=t["grid"])
    ax.tick_params(colors=t["tick"], labelcolor=t["text"])
    for spine in ax.spines.values():
        spine.set_color(t["grid"])

    # 1) 连续浪路径：优先（paths 传了就用新样式），只连线不在 K 线上标文字
    sub_rows = []
    if paths:
        sub_rows = _draw_paths(ax, plot_df, base, paths, t, fs)
        # 起画点校验（硬性）：至少一条路径的起点即起画点(start，原始 CSV 行号)；叠加子浪路径允许起点偏右
        # 但不越出窗口左界。防止"从数据起点/中途起画"，同时不误伤多级叠加（子浪起点晚于主路径起点）。
        if start is not None:
            touched = any(idxs and idxs[0] == start for idxs, _l in paths)
            for idxs, labels in paths:
                if idxs and (idxs[0] - base) < 0:
                    print(f"[警告] 起画点校验：{labels[0]} 存在早于窗口左界的端点，已跳过", file=sys.stderr)
            if not touched:
                print("[警告] 起画点校验：没有路径从起画点(第1浪起点)开始，白线可能从数据起点/中途起画",
                      file=sys.stderr)
    # 原有的每段浪标注（兼容旧调用；与 paths 可并存）
    for label, s0, e0, note, direction in waves:
        s = s0 - base
        e = e0 - base
        if s < 0 or e < 0 or s >= len(plot_df) or e >= len(plot_df):
            print(f"[警告] 浪段 {label} 索引越界，跳过", file=sys.stderr)
            continue
        xs, xe = s, e
        # 方向判定（R20 极端价位口径）：显式 up/down 优先；auto 见 _seg_direction
        if direction == "auto":
            up = _seg_direction(plot_df, s, e)
        else:
            up = direction == "up"
        ys = plot_df.iloc[s]["low"] if up else plot_df.iloc[s]["high"]
        ye = plot_df.iloc[e]["high"] if up else plot_df.iloc[e]["low"]
        ax.annotate(
            "", xy=(xe, ye), xytext=(xs, ys),
            arrowprops=dict(arrowstyle="-|>", color=t["path"], lw=1.5,
                            connectionstyle="arc3,rad=0.12"),
            zorder=4,
        )
        # 旧 waves 也把文字移到底部（不在 K 线上标注）；收集子浪端点
        if label:
            date_s = plot_df.index[e].strftime("%Y-%m-%d")
            sub_rows.append((label, _fmt_price(ye), date_s, e))

    # 1b) 推动浪平行通道（深色下亮青）：只画轨道线，不标文字
    if channels:
        _draw_channels(ax, plot_df, base, channels, t, fs)

    # 2) 参考线：只画线，不放标签
    price_floor = plot_df["low"].min()
    price_ceil = plot_df["high"].max()
    span = price_ceil - price_floor or 1.0

    # 失效价位：红色虚线
    for price, _label in invalids:
        ax.axhline(price, color=t["invalid"], linestyle="--", linewidth=1.4, zorder=6)

    # 关键阻力/支撑：蓝色点划线
    for price, _label in levels or []:
        ax.axhline(price, color=t["resist"], linestyle="-.", linewidth=1.1, zorder=6)

    # 当前价格：绿色实线
    if current_price is not None:
        ax.axhline(current_price, color=t["current"], linestyle="-", linewidth=1.2, zorder=6)

    # 3) 底部注释区
    # 3a) 蓝框：水平线含义注释（ax_legend）
    legend_lines = []
    for price, label in levels or []:
        legend_lines.append((t["resist"], "蓝色点划线", f"{label} {_fmt_price(price)}"))
    for price, label in invalids:
        legend_lines.append((t["invalid"], "红色虚线", f"{label} {_fmt_price(price)}"))
    if current_price is not None:
        legend_lines.append((t["current"], "绿色实线", f"当前价 {_fmt_price(current_price)}"))
    if channels:
        legend_lines.append((t["channel"], "青色实线", "平行通道：上轨=连[1][3]高点"))
        legend_lines.append((t["channel"], "青色虚线", "平行通道：下轨=过[2]低点平行"))
    _draw_level_legend(ax_legend, plot_df, legend_lines, t, fs, row_h=row_h)

    # 3b) 浪型区：按层级分多块（大级别 / 2级 / 3级…），层级越高颜色越显眼（与线上颜色一致）
    #     块1=大级别（pivot [I][II] 等 + 单数字 1 级子浪）；块2+ = 多级子浪（1-1、1-1-1 按连字符段数分级）
    sub_groups = {}
    for label, price, date, _x in sub_rows:
        lvl = _label_level(label)
        sub_groups.setdefault(lvl, []).append((label, price, date))
    # 大级别价格/日期从 pivot 索引实时取
    big_seq = []
    for item in pivots or []:
        idx_p, big, kind = item if len(item) == 3 else (item[0], item[1], "peak")
        gip = idx_p - base
        if 0 <= gip < len(plot_df):
            rp = plot_df.iloc[gip]
            is_peak = kind == "peak"
            yv = rp["high"] if is_peak else rp["low"]
            ds = plot_df.index[gip].strftime("%Y-%m-%d")
            big_seq.append((big, _fmt_price(yv), ds))
    if current_price is not None:
        sub_groups.setdefault(1, []).append(("当前", _fmt_price(current_price),
                                             plot_df.index[-1].strftime("%Y-%m-%d")))
    # 浪型区：大级别块 + 逐级子浪块（多列并排，第一行 y 统一 _BOTTOM_Y0）
    _draw_wave_legend(ax_waves, big_seq, sub_groups, t, fs, row_h=row_h)

    # 比率目标区：浅色区间（只画区间，不放文字到 K 线旁，底部已说明）
    if fib_zones:
        for lo, hi, label in fib_zones:
            lo = max(lo, price_floor - span * 0.1)
            hi = min(hi, price_ceil + span * 0.1)
            ax.axhspan(lo, hi, color=t["fib"], alpha=0.18, zorder=5)

    # 江恩角度线：青绿色扇形（可选叠加；只画线不放文字）
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
            ax.plot([a, x_end], [p0, y_end], color=t["gann"], linestyle=ls,
                    linewidth=lw, alpha=0.9, zorder=5)

    # 不用 tight_layout（与 gridspec 冲突会挤掉 x 轴日期），改用 subplots_adjust 留边；
    # 底边距按英寸换算（画布高度已随底部行数自适应，固定分数会在高画布上留白过多）
    fig.subplots_adjust(left=0.05, right=0.985, top=1 - 0.62 / fig_h,
                        bottom=0.30 / fig_h)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # 紧凑裁边：坐标轴铺满图片，四周无多余白边
    fig.savefig(out_path, dpi=180, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    # 验证输出文件存在且非空
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"图片保存失败或为空: {out_path}")
    print(f"[OK] 已保存: {out_path} ({os.path.getsize(out_path)} bytes)")


def _draw_paths(ax, plot_df, base, paths, t, fs):
    """绘制连续浪路径：把 paths 里每个端点序列连成一条带箭头的折线。

    paths: [([idx...], labels), ...]。labels 为每点浪标签文字（长度 1=用序号 1..n 自动，
    长度=n=逐点）。端点价格取该 K 线的极端价位：峰谷性按相邻端点段方向判
    （R20 口径，见 _seg_direction），峰取 high、谷取 low。
    连线：已确认段用亮色细实线（0.9px、半透明），**最后一段**（当前未走完）用灰色虚线。
    只连线、不画任何文字（K 线旁无标注，浪型文字由底部注释区呈现），
    返回子浪端点序列 sub_rows=[(label, price, date, x)] 供 draw_chart 生成浪型列表。
    """
    sub_rows = []  # [(label, price, date, x)] 有序子浪端点序列
    for idxs, labels in paths:
        auto_seq = len(labels) == 1
        # 层级色：按该路径首标签的层级取色（多级子浪叠加用颜色区分）
        c = _level_color(labels[0], t)
        # 第一遍：过滤越界点，只留有效端点（峰谷判定依赖相邻有效端点，不能带洞）
        valid = []
        for i, idx in enumerate(idxs):
            gi = idx - base
            if 0 <= gi < len(plot_df):
                valid.append((gi, labels[0] if auto_seq else labels[i]))
            else:
                print(f"[警告] 路径点 {labels[0] if auto_seq else labels[i]}[{i}] 索引越界，跳过",
                      file=sys.stderr)
        if len(valid) < 2:
            continue
        # 第二遍：峰谷性按相邻端点段方向判（R20 极端价位口径，见 _seg_direction）——
        # 上行段到达点为峰（取 high）、起点为谷（取 low）；下行段对称
        pts = []
        label_seq = []
        for j, (gi, lbl) in enumerate(valid):
            if j == 0:
                is_peak = not _seg_direction(plot_df, valid[0][0], valid[1][0])
            else:
                is_peak = _seg_direction(plot_df, valid[j - 1][0], gi)
            row = plot_df.iloc[gi]
            y = row["high"] if is_peak else row["low"]
            pts.append((gi, y))
            label_seq.append(lbl)
            # 收集子浪端点（仅非空标签；空标签=更大级别/当前，由 pivot 或底部区处理）
            if lbl != "":
                date_s = plot_df.index[gi].strftime("%Y-%m-%d")
                sub_rows.append((lbl, _fmt_price(y), date_s, gi))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # 分级折线：labels 非空 → 已确认子浪段（实线）；labels 为空("") → 未走完/更大级别段（虚线）
        last_labeled = -1
        for k, lb in enumerate(label_seq):
            if lb != "":
                last_labeled = k
        # 0..last_labeled 段为实线（已确认），last_labeled 之后画虚线
        if last_labeled >= 0:
            # 实线段：从第 0 点画到 last_labeled 点
            ax.plot(xs[:last_labeled + 1], ys[:last_labeled + 1], color=c,
                    linewidth=0.9, alpha=0.6, zorder=5,
                    marker=None, solid_capstyle="round", solid_joinstyle="round")
            # 虚线段：从 last_labeled 点画到路径末端（未走完/延伸段）
            if last_labeled < len(pts) - 1:
                ax.plot(xs[last_labeled:], ys[last_labeled:], color=t["note"],
                        linewidth=0.9, linestyle="--", alpha=0.8, zorder=5)
        # 每段末端加箭头（实线段用路径色，虚线段用灰）
        for k in range(len(pts) - 1):
            seg = t["note"] if k >= last_labeled else c
            ax.annotate("", xy=(xs[k + 1], ys[k + 1]), xytext=(xs[k], ys[k]),
                        arrowprops=dict(arrowstyle="-|>", color=seg,
                                        lw=0.9, shrinkA=0, shrinkB=0),
                        zorder=5)
    return sub_rows


def _draw_channels(ax, plot_df, base, channels, t, fs):
    """绘制推动浪平行通道（常规通道）：连接 1 浪高点与 3 浪高点为上轨，
    过 2 浪低点画平行线为下轨。轨道上标注"上轨"/"下轨"。

    注意：轨道只画在 [1浪高点, 3浪高点] 的 X 区间内。因为推动浪短区间内涨幅大，
    斜率通常很陡，若全幅延伸会把坐标轴撑爆（Y 轴被压到顶部）。区间内绘制能稳定
    显示通道斜率，且不破坏其它 K 线的可视范围。连线最细（1px）且半透明，避免压 K 线。
    """
    span = plot_df["high"].max() - plot_df["low"].min() or 1.0
    n = len(plot_df)
    for idx1_hi, idx3_hi, idx2_low in channels:
        g1, g3, g2 = idx1_hi - base, idx3_hi - base, idx2_low - base
        if not (0 <= g1 < n and 0 <= g3 < n and 0 <= g2 < n):
            print("[警告] 平行通道索引越界，跳过", file=sys.stderr)
            continue
        x0, x1 = min(g1, g3) - max(3, int(n * 0.002)), max(g1, g3) + max(3, int(n * 0.002))
        x0 = max(0, x0)
        x1 = min(n - 1, x1)
        p1_y = plot_df.iloc[g1]["high"]
        p3_y = plot_df.iloc[g3]["high"]
        # 上轨：连接 1、3 浪高点的直线（在区间内）
        slope = (p3_y - p1_y) / (g3 - g1) if g3 != g1 else 0.0
        top_intercept = p1_y - slope * g1
        # 下轨：过 2 浪低点，与上轨平行（斜率相同）
        bot_intercept = plot_df.iloc[g2]["low"] - slope * g2
        g2_y = plot_df.iloc[g2]["low"]
        for intercept, lw in ((bot_intercept, 1.0), (top_intercept, 1.0)):
            ax.plot([x0, x1], [slope * x0 + intercept, slope * x1 + intercept],
                    color=t["channel"], linestyle="-", linewidth=lw, alpha=0.75,
                    zorder=5)
        # 上轨/下轨说明不贴在轨道上（避免压 K 线），改由 draw_chart 汇总到左上角图例块，
        # 与标题同高度区域统一标注（见 _draw_level_legend / draw_chart 的 legend_lines）。


def _draw_level_legend(ax, plot_df, lines, t, fs, row_h=_BOTTOM_ROW_H):
    """左块（线的注释）：水平线 + 平行通道，连续排布。

    lines: [(color, 线型描述, 说明文本), ...]，如 [(蓝色, "蓝色点划线", "2015大顶 3108.70")]。
    所有行统一行距（row_h，由 _bottom_layout 按画布底部区实际高度换算）与字号(_BOTTOM_FS)，
    第一行 y=_BOTTOM_Y0（与右块对齐）。每行左侧一个色块示意（短横线），右侧说明文字。
    """
    if not lines:
        ax.axis("off")
        return
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for i, (color, ltype, desc) in enumerate(lines):
        y = _BOTTOM_Y0 - i * row_h
        x0 = 0.03
        # 线型（按 ltype 单词判线型，与图上实际线型一致）
        if "虚线" in ltype:
            ls = "--"
        elif "实线" in ltype:
            ls = "-"
        else:
            ls = "-."
        ax.plot([x0, x0 + 0.035], [y, y], color=color, linestyle=ls,
                linewidth=1.8, zorder=8)
        ax.text(x0 + 0.05, y, f"{desc}", color=t["text"], fontsize=_BOTTOM_FS,
                ha="left", va="center", zorder=8)
    return


def _draw_wave_legend(ax, big_seq, sub_groups, t, fs, row_h=_BOTTOM_ROW_H):
    """右块（浪型）：按层级分多个文本块并排——块1 大级别([I][II]等 + 1级子浪)，
    块2+ 为多级子浪(1-1、1-1-1 按连字符段数分 2级/3级…)，颜色与对应层级连线一致。

        [大级别]         [2级]            [3级]
        [I]: 1111, 2020    1-1: 1200, 2021  1-1-1: 1180, 2021.3
        [II]: 3333, 2023   1-2:  900, 2022  1-1-2: 1250, 2021.4

    big_seq: [(label, price, date), ...] 大级别浪（[I][II][III]…）
    sub_groups: {level: [(label, price, date), ...]} 按层级分组（level=连字符段数+1）
    每列直接列该级终点（无列标题，颜色即级别区分）；
    列宽按各列最长文本的宽度单位（CJK 计 2）比例分配（不再均分），
    行距 row_h 由 _bottom_layout 按画布底部区实际高度换算（行数多则加高画布而非压缩行距）。
    """
    if not big_seq and not sub_groups:
        ax.axis("off")
        return
    cols = [("大级别", list(big_seq) + list(sub_groups.get(1, [])))]
    # 底部浪型区只列 第 1 层(大级别) + 第 2 层 子浪；第 3 层及更深(1-1-1…)仅画线、不进底部文本（避免图过高）
    for lvl in sorted(k for k in sub_groups if k == 2):
        cols.append(("%d级" % lvl, sub_groups[lvl]))
    n = len(cols)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    # 列宽自适应：按各列最长数据行文本的宽度单位比例分配，设下限防空列被挤没
    weights = []
    for _title, rows in cols:
        u = 6
        for lb, pr, dt in rows:
            u = max(u, _text_units(f"{lb}: {pr}, {_dot_fmt(dt)}"))
        weights.append(u)
    total = sum(weights)
    shares = [max(0.14, 0.94 * w / total) for w in weights]
    scale = 0.94 / sum(shares)  # 归一化回 0.94 总宽
    shares = [s * scale for s in shares]
    x_starts = [0.03]
    for s in shares[:-1]:
        x_starts.append(x_starts[-1] + s)
    for ci, (_title, rows) in enumerate(cols):
        x0 = x_starts[ci]
        # 该级终点（数据行，第一行与左块注释 y 对齐=_BOTTOM_Y0）
        for i, (lb, pr, dt) in enumerate(rows):
            y = _BOTTOM_Y0 - i * row_h
            col = t["text"] if lb == "当前" else _level_color(lb, t)
            ax.text(x0, y, f"{lb}: {pr}, {_dot_fmt(dt)}", color=col,
                    fontsize=_BOTTOM_FS, ha="left", va="center", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.1", fc=t["label_fc"],
                              ec=t["frame"], alpha=0.9, lw=0.6))
    return


def _dot_fmt(date_s):
    """把 'YYYY-MM-DD' 转成点分 'YYYY.M.D'（贴合示例 2020.1.1 样式）。"""
    try:
        y, m, d = date_s.split("-")
        return f"{y}.{int(m)}.{int(d)}"   # 去前导零
    except (ValueError, AttributeError):
        return date_s


def parse_wave_arg(s):
    """解析 '标签:起点:终点:备注[:方向]'。方向 up/down/auto（默认 auto）。
    起点/终点返回原始字符串（整数索引 或 YYYY-MM-DD 日期），由 resolve_index()
    在拿到 df 后统一归一化为整数索引（与 --start 的日期口径一致，见 main）。"""
    parts = s.split(":", 4)
    if len(parts) not in (4, 5):
        raise argparse.ArgumentTypeError(
            "拒绝: 浪段格式应为 标签:起点:终点:备注[:方向up/down/auto]"
            "（冒号分 4–5 段；起点/终点可为整数索引或 YYYY-MM-DD 日期；勿用 @ 分隔），收到: %r" % s)
    direction = parts[4] if len(parts) == 5 else "auto"
    if direction not in ("up", "down", "auto"):
        raise argparse.ArgumentTypeError("拒绝: 浪段方向只支持 up/down/auto，收到: %r" % direction)
    # 端点保留原文，供 resolve_index 在拿到 df 后转换；这里不转 int（避免误把日期当索引）
    return (parts[0], parts[1], parts[2], parts[3], direction)


def resolve_index(df, token, label):
    """把 --waves 端点 token 归一化为整数索引。纯数字→int；否则按日期在 df.index
    定位（与 --start 同一口径，须为数据内交易日）。返回 int 索引。
    既非整数也非可解析日期时给出清晰报错（勿让底层 DateParseError 漏出）。"""
    token = token.strip()
    if token.isdigit():
        idx = int(token)
    else:
        try:
            ts = pd.Timestamp(token)
        except Exception:  # noqa: BLE001 —— 统一转成可读的 CLI 报错
            raise SystemExit("拒绝: --waves %s 端点既非整数索引也非合法日期，无法解析: %r"
                             "（格式「标签:起点:终点:备注[:方向]」，起点/终点用 : 分隔且需为"
                             "索引或 YYYY-MM-DD）" % (label, token))
        pos = df.index.get_indexer([ts])
        if pos[0] < 0:
            raise SystemExit("拒绝: --waves %s 的端点日期不在数据内: %s" % (label, token))
        idx = int(pos[0])
    if idx < 0 or idx >= len(df):
        raise SystemExit("拒绝: --waves %s 的端点索引越界: %d（数据共 %d 根）" % (label, idx, len(df)))
    return idx


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


def gann_auto_scale(price, is_index=False):
    """D23 自动分档：指数点位固定 50；价格 <10→0.05、10–100→0.5、
    100–1000→5、≥1000→50（单位价格/根 K 线，目标使 1×1 线视觉接近 45°）。"""
    if is_index:
        return 50.0
    if price < 10:
        return 0.05
    if price < 100:
        return 0.5
    if price < 1000:
        return 5.0
    return 50.0


def parse_gann_arg(s, auto=False):
    """解析江恩扇形参数。auto 模式（--gann-auto-scale）：'起点索引:起点价格[:方向]'，
    刻度按 D23 自动分档；手动模式：'起点索引:起点价格:刻度[:方向]'。"""
    parts = s.split(":")
    if auto:
        if len(parts) not in (2, 3):
            raise argparse.ArgumentTypeError(
                f"江恩参数（--gann-auto-scale 模式）应为 起点索引:起点价格[:方向]，收到: {s}")
        direction = parts[2] if len(parts) == 3 else "up"
        if direction not in ("up", "down"):
            raise argparse.ArgumentTypeError(f"江恩方向只支持 up/down，收到: {direction}")
        return (int(parts[0]), float(parts[1]), None, direction)
    if len(parts) not in (3, 4):
        raise argparse.ArgumentTypeError(
            f"江恩参数应为 起点索引:起点价格:刻度[:方向]，收到: {s}")
    direction = parts[3] if len(parts) == 4 else "up"
    if direction not in ("up", "down"):
        raise argparse.ArgumentTypeError(f"江恩方向只支持 up/down，收到: {direction}")
    return (int(parts[0]), float(parts[1]), float(parts[2]), direction)


def parse_path_arg(s):
    """解析连续浪路径，两种形式：

    1) 每点带框标（推荐）：'框标@索引,框标@索引,...'，框标即浪编号（如 1/2/3/4/5/A/B/C）。
       例：--path "1@4165,2@4174,3@4178,4@4223,5@4295,A@4484,B@4612,C@4624"，
       把每个点依序连成带箭头折线，编号框显示 [1][2][3][4][5][A][B][C]。
    2) 兼容旧式：'标签:索引:索引:...'，框标自动取序号 1..n。
       例：--path "[1]:4165:4174:4178:4223:4295:4484"。
    """
    if "@" in s and "," in s:
        points = s.split(",")
        idxs, labels = [], []
        for pp in points:
            lb, ix = pp.split("@", 1)
            idxs.append(int(ix))
            labels.append(lb)
        return (idxs, labels)
    if "@" in s:  # 单点带框标（无逗号），视为一个转折点
        lb, ix = s.split("@", 1)
        return ([int(ix)], [lb])
    # 旧式：标签:索引:索引:...
    parts = s.split(":")
    if len(parts) < 3:
        raise argparse.ArgumentTypeError(
            f"路径格式应为 框标@索引,... 或 标签:索引:索引:...（至少 2 个索引），收到: {s}")
    label = parts[0]
    try:
        idxs = [int(x) for x in parts[1:]]
    except ValueError:
        raise argparse.ArgumentTypeError(f"路径索引须为整数，收到: {s}")
    return (idxs, [label])


def parse_channel_arg(s):
    """解析推动浪平行通道：'1浪高点索引:3浪高点索引:2浪低点索引'。

    例：--channel "4174:4223:4178" → 连接 1 浪高点 4174 与 3 浪高点 4223 为上轨，
    过 2 浪低点 4178 画平行线为下轨。
    """
    parts = s.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"通道格式应为 1浪高点索引:3浪高点索引:2浪低点索引，收到: {s}")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        raise argparse.ArgumentTypeError(f"通道索引须为整数，收到: {s}")


def parse_pivot_arg(s):
    """解析大级别浪标注：'标注:索引[:峰/谷]'。标注即大级别编号（如 [I]/[II]/[III]）。

    例：--pivot "[I]:4484:peak" → 在索引 4484 处挂大级别标注 [I]，标在波峰(高点)上方；
    --pivot "[II]:4612:trough" → 挂 [II] 标在波谷(低点)下方。默认 peak。
    """
    parts = s.split(":")
    if len(parts) not in (2, 3):
        raise argparse.ArgumentTypeError(
            f"大级别标注格式应为 标注:索引[:peak/trough]，收到: {s}")
    kind = parts[2] if len(parts) == 3 else "peak"
    if kind not in ("peak", "trough"):
        raise argparse.ArgumentTypeError(f"大级别类型只支持 peak/trough，收到: {kind}")
    try:
        return (int(parts[1]), parts[0], kind)
    except ValueError:
        raise argparse.ArgumentTypeError(f"大级别索引须为整数，收到: {s}")


def main():
    p = argparse.ArgumentParser(description="Elliott Wave K 线图绘制")
    p.add_argument("--csv", required=True, help="OHLC CSV（date,open,high,low,close）")
    p.add_argument("--out", default=None, help="输出 PNG 路径（与 --out-auto 二选一）")
    p.add_argument("--out-auto", default=None, metavar="DIR|方案|图型",
                   help="按 embed_report_images.py 固定命名权威自动生成输出路径："
                        "目录|方案|图型（方案∈{主方案,替代方案}，图型∈{全景}——每方案一张全景图），"
                        "如 --out-auto \"C:/x/图表|主方案|全景\" → DIR/主方案_全景.png；"
                        "与 --out 互斥，命名约定单一出处，禁止手工另起名")
    p.add_argument("--title", required=True, help="图标题（含分析级别与方案名）")
    p.add_argument("--waves", nargs="*", action="append", type=parse_wave_arg, default=[],
                   help="浪段标注：标签:起点:终点:备注[:方向up/down/auto]。"
                        "起点/终点可为整数索引 或 YYYY-MM-DD 日期（与 --start 口径一致，"
                        "日期须为数据内交易日）；方向默认 auto=按端点极端价位判定"
                        "（终点高/低均高于起点→上行，均低→下行，区间重叠回退收盘比较，R20 口径）；"
                        "三段分隔符为冒号，勿用 @ 或空格；仅作大级别底图，子浪请用 --path")
    p.add_argument("--invalid", nargs="*", action="append", type=parse_price_arg, default=[],
                   help="失效价位：价格:标签（含规则编号）")
    p.add_argument("--level", nargs="*", action="append", type=parse_price_arg, default=[],
                   help="关键阻力/支撑：价格:标签（蓝色点划线，区别于失效价位）")
    p.add_argument("--current", type=float, default=None, help="当前价格")
    p.add_argument("--fib", nargs="*", action="append", type=parse_fib_arg, default=[],
                   help="斐波那契目标区：低:高:标签")
    p.add_argument("--last", type=int, default=None, help="只绘制最近 N 根 K 线")
    p.add_argument("--start", default=None, metavar="INDEX|YYYY-MM-DD",
                   help="观察窗口左界（起画点）：数值=原始 CSV 行号，或日期 YYYY-MM-DD；"
                        "全景图传该方案最大分析级别标注结构的第 1 浪起点；"
                        "强制 X 轴从该点起画；与 --path 同用触发首端点贴起点校验，禁止从数据起点或中途起画")
    p.add_argument("--gann", nargs="*", action="append", default=[], metavar="FAN",
                   help="江恩角度线扇形（可选叠加）：起点索引:起点价格[:刻度][:方向up/down]；"
                        "刻度 = 每根 K 线 1 单位价格（分档见项目默认口径 D23），须披露")
    p.add_argument("--gann-auto-scale", action="store_true",
                   help="江恩刻度自动分档（D23）：--gann 省略刻度，按锚点价格量级取 "
                        "0.05/0.5/5/50，图例与输出披露刻度值；同一分析内禁止换刻度")
    p.add_argument("--gann-index", action="store_true",
                   help="标的为指数点位：--gann-auto-scale 时分档固定取 50（D23）")
    p.add_argument("--font-scale", type=float, default=1.0,
                   help="字号缩放（全景图子浪标注建议 1.2–1.4）")
    p.add_argument("--theme", default="dark", choices=("dark", "light"),
                   help="主题：dark（默认，深色画布亮色连线）/ light（旧浅色）")
    p.add_argument("--path", action="append", type=parse_path_arg, default=[],
                   help="连续浪路径：框标@索引,... 或 标签:索引:索引:...（按序连成一条带箭头折线，"
                        "端点加编号框）。可多次传入叠加不同层级子浪（如 1-1、1-1-1），"
                        "层级颜色由框标的连字符段数区分（1→白、1-1→青、1-1-1→橙）。"
                        "子浪必用 --path、大级别底图用 --waves；默认 2 层=每个大级别浪都叠第 2 层子浪，"
                        "用户明确要 3 层才叠第 3 层（09 默认口径表 D37）。"
                        "例：--path \"1-1@339,1-2@465\" --path \"1-1-1@360,1-1-2@400\"")
    p.add_argument("--channel", nargs="*", action="append", type=parse_channel_arg, default=[],
                   help="推动浪平行通道：1浪高点索引:3浪高点索引:2浪低点索引。"
                        "例：--channel \"4174:4223:4178\"")
    p.add_argument("--pivot", nargs="*", action="append", type=parse_pivot_arg, default=[],
                   help="大级别浪标注：标注:索引[:peak/trough]（如 [I]:4484:peak），挂在对应端点，"
                        "白框大号字，与子浪编号框区分（分级标注）。peak=波峰标上方默认、"
                        "trough=波谷标下方。例：--pivot \"[I]:4484:peak\" \"[II]:4612:trough\"")
    args = p.parse_args()

    # 多值参数（--waves/--invalid/--level/--fib/--gann/--channel/--pivot）：
    # action="append"+nargs="*" 得到嵌套列表，展平为单层。
    # 修复"同一 flag 分多次传会被 store 静默覆盖只剩最后一个"（如 --level A --level B → [A,B]）。
    for _n in ("waves", "invalid", "level", "fib", "gann", "channel", "pivot"):
        _v = getattr(args, _n, None)
        if isinstance(_v, list) and _v and isinstance(_v[0], (list, tuple)):
            setattr(args, _n, [x for _sub in _v for x in _sub])

    # 输出路径：--out-auto（embed 固定命名权威）优先，与 --out 互斥
    if args.out_auto:
        if args.out:
            p.error("--out 与 --out-auto 只能二选一")
        parts = args.out_auto.split("|")
        if len(parts) != 3 or parts[1] not in SCHEME_NAMES or parts[2] not in CHART_VIEWS:
            p.error('--out-auto 格式应为 "目录|主方案|全景"（方案∈{主方案,替代方案}，图型∈{全景}——每方案一张全景图），'
                    "收到: %s" % args.out_auto)
        out_path = os.path.join(parts[0], chart_png(parts[1], parts[2]))
    elif args.out:
        out_path = args.out
    else:
        p.error("必须提供 --out 或 --out-auto 之一")

    df = load_ohlc(args.csv, set_date_index=True)

    # --start 起画点（原始 CSV 行号）：数值直接取行号；日期须为数据内交易日，精确匹配（起画点应为 swings 端点所在日）
    start_idx = None
    if args.start:
        if args.start.isdigit():
            start_idx = int(args.start)
        else:
            pos = df.index.get_indexer([pd.Timestamp(args.start)])
            if pos[0] >= 0:
                start_idx = int(pos[0])
            else:
                raise SystemExit(f"[错误] --start 起画点日期不在数据内: {args.start}")
        if start_idx < 0 or start_idx >= len(df):
            raise SystemExit(f"[错误] --start 起画点越界: {start_idx}（数据共 {len(df)} 根）")

    # 江恩扇形：auto 模式统一按第一个锚点价格分档（D23 同一分析内禁止换刻度）
    gann_fans = []
    if args.gann:
        raw_fans = [parse_gann_arg(s, auto=args.gann_auto_scale) for s in args.gann]
        if args.gann_auto_scale:
            scale = gann_auto_scale(raw_fans[0][1], args.gann_index)
            for idx, price, _sc, direction in raw_fans:
                if gann_auto_scale(price, args.gann_index) != scale:
                    print("[警告] 江恩锚点价格 %s 与首个锚点分档不同，已统一用刻度 %s（D23 同一分析内禁止换刻度）"
                          % (_fmt_price(price), _fmt_price(scale)), file=sys.stderr)
                gann_fans.append((idx, price, scale, direction))
            print("[江恩] 自动刻度 %s/根（D23 分档：锚点价格 %s%s）"
                  % (_fmt_price(scale), _fmt_price(raw_fans[0][1]),
                     "，指数点位固定 50" if args.gann_index else ""))
        else:
            gann_fans = [(idx, price, scale, direction)
                         for idx, price, scale, direction in raw_fans]

    # --waves 端点归一化：日期/索引统一转为整数索引（parse_wave_arg 已保留原文，
    # 此处须在拿到 df 后转换，与 --start 日期口径一致）
    waves = []
    for label, s, e, note, direction in args.waves:
        si = resolve_index(df, s, label + "起点")
        ei = resolve_index(df, e, label + "终点")
        waves.append((label, si, ei, note, direction))

    # ---- 外观规范警告（B2：浪级配色，警告不阻断出图）----
    def _lvl(lb):
        return str(lb).count("-") + 1
    if args.waves and args.path:
        print("[警告] 大级别用 --waves 是 up/down 方向色（青/蓝），不是'首层白'；要首层白色请用 --path 无连字符标签",
              file=sys.stderr)
    has_l1 = any(any(l != "" and _lvl(l) == 1 for l in labels)
                 for _idxs, labels in args.path)
    if args.path and not has_l1:
        print("[警告] 缺少大级别白色主链：--path 全是带连字符标签（第 2 层+），未用无连字符标签标大级别（应为白色）",
              file=sys.stderr)
    for _idxs, labels in args.path:
        lv = {_lvl(l) for l in labels if l != ""}
        if len(lv) > 1:
            print(f"[警告] 同一条 --path 内标签层级不一致 {sorted(lv)}（一条=一个浪链，勿混层级）",
                  file=sys.stderr)

    draw_chart(df, out_path, args.title, waves, args.invalid,
               current_price=args.current, fib_zones=args.fib, last_n=args.last,
               levels=args.level, font_scale=args.font_scale,
               gann_fans=gann_fans, theme=args.theme, paths=args.path,
               channels=args.channel, pivots=args.pivot, start=start_idx)


if __name__ == "__main__":
    main()
