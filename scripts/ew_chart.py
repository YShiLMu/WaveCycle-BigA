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
#   _BOTTOM_Y0     —— 两块第一行统一 y（贴近注释块顶部=贴近主图）
#   _BOTTOM_ROW_H  —— 所有行统一行距（水平线/通道/大浪/小浪同一行距，不再各自算行距）
#   _BOTTOM_FS     —— 所有文字统一字号
_BOTTOM_Y0 = 0.94
_BOTTOM_ROW_H = 0.13
_BOTTOM_FS = 11

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
               pivots=None):
    """绘制单方案 K 线图并保存 PNG。

    waves: [(label, start_idx, end_idx, form_note, direction), ...]
        # direction: "up"/"down"/"auto"（auto 按端点极端价位判定，见 _wave 判向逻辑）
    invalids: [(price, label), ...]
    fib_zones: [(lo, hi, label), ...]
    levels: [(price, label), ...]  # 关键阻力/支撑（蓝色虚线，非失效）
    gann_fans: [(anchor_idx, anchor_price, scale, direction), ...]
        # 江恩角度线扇形（青绿色）；scale = 每根 K 线 1 单位价格（刻度按项目默认口径 D23 分档），
        # direction: "up"（低点出发向上，默认）/ "down"（高点出发向下）
    font_scale: 字号缩放（放大图建议 1.2–1.4，保证子浪标注清晰）
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
    plot_df = df.tail(last_n) if last_n is not None else df
    base = len(df) - len(plot_df)  # 索引偏移（浪段索引基于全量 CSV 行号）

    t = THEMES.get(theme, THEMES["dark"])

    # 宽幅图（含底部注释带）：主图区 + 下方注释区
    fig = plt.figure(figsize=(18, 10))
    # 布局：主图跨全宽（只画线，不放任何文字）。
    #   下方 2 块：左 = 平行线注释（ax_legend）；右 = 浪型区（ax_waves，内部大浪左列+小浪右列）。
    #   大浪/小浪行距各自独立、互不干涉；第一行 y 统一用 _BOTTOM_Y0。
    gs = fig.add_gridspec(2, 2, height_ratios=[6.4, 1.2], hspace=0.16, wspace=0.05,
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

    fs = font_scale
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
    _draw_level_legend(ax_legend, plot_df, legend_lines, t, fs)

    # 3b) 红框：浪型序列 —— 大级别([I][II][III])放左列、子浪([0..5]+当前)放右列，两列并排
    sub_seq = [(label, price, date) for (label, price, date, _x) in sub_rows]
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
        sub_seq.append(("当前", _fmt_price(current_price),
                        plot_df.index[-1].strftime("%Y-%m-%d")))
    # 浪型区：大浪左列、小浪右列，各自独立行距（互不干涉），第一行 y 统一 _BOTTOM_Y0
    _draw_wave_legend(ax_waves, big_seq, sub_seq, t, fs)

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

    # 不用 tight_layout（与 gridspec 冲突会挤掉 x 轴日期），改用 subplots_adjust 留边
    fig.subplots_adjust(left=0.05, right=0.985, top=0.93, bottom=0.12)
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
            ax.plot(xs[:last_labeled + 1], ys[:last_labeled + 1], color=t["path"],
                    linewidth=0.9, alpha=0.6, zorder=5,
                    marker=None, solid_capstyle="round", solid_joinstyle="round")
            # 虚线段：从 last_labeled 点画到路径末端（未走完/延伸段）
            if last_labeled < len(pts) - 1:
                ax.plot(xs[last_labeled:], ys[last_labeled:], color=t["note"],
                        linewidth=0.9, linestyle="--", alpha=0.8, zorder=5)
        # 每段末端加箭头（实线段用路径色，虚线段用灰）
        for k in range(len(pts) - 1):
            seg = t["note"] if k >= last_labeled else t["path"]
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


def _draw_level_legend(ax, plot_df, lines, t, fs):
    """左块（线的注释）：水平线 + 平行通道，连续排布。

    lines: [(color, 线型描述, 说明文本), ...]，如 [(蓝色, "蓝色点划线", "2015大顶 3108.70")]。
    所有行统一行距(_BOTTOM_ROW_H)与字号(_BOTTOM_FS)，第一行 y=_BOTTOM_Y0（与右块对齐）。
    每行左侧一个色块示意（短横线），右侧说明文字。
    """
    if not lines:
        ax.axis("off")
        return
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for i, (color, ltype, desc) in enumerate(lines):
        y = _BOTTOM_Y0 - i * _BOTTOM_ROW_H
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
        ax.text(x0 + 0.05, y, f"{desc}", color=t["text"], fontsize=_BOTTOM_FS * fs,
                ha="left", va="center", zorder=8)
    return


def _draw_wave_legend(ax, big_seq, sub_seq, t, fs):
    """右块（浪型）：大浪点位左列 + 小浪点位右列，双列并排。

        [I]: 1111, 2020.1.1      [0]: 1111, 2020.1.1
        [II]: 3333, 2023.2.2     [1]: 2222, 2020.2.2
        [III]: 5555, 2023.5.5    ...

    big_seq: [(label, price, date), ...] 大级别浪（[I][II][III]…）→ 左列
    sub_seq: [(label, price, date), ...] 子浪（[0]..[5]/当前）→ 右列
    两列第一行 y=_BOTTOM_Y0（与左块对齐），统一行距(_BOTTOM_ROW_H)与字号(_BOTTOM_FS)，
    不再各自算行距——小浪行数多只在自身列内向下排，不与其它列相互挤压。
    """
    if not big_seq and not sub_seq:
        ax.axis("off")
        return
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    # 左列：大浪（与左块同字号/行距/字号）
    for i, (lb, pr, dt) in enumerate(big_seq):
        y = _BOTTOM_Y0 - i * _BOTTOM_ROW_H
        ax.text(0.03, y, f"{lb}: {pr}, {_dot_fmt(dt)}", color=t["text"],
                fontsize=_BOTTOM_FS * fs, ha="left", va="center", zorder=8,
                bbox=dict(boxstyle="round,pad=0.1", fc=t["label_fc"],
                          ec=t["frame"], alpha=0.9, lw=0.6))
    # 右列：小浪（与左块同字号/行距/字号；行数多仅在本列内延伸）
    for i, (lb, pr, dt) in enumerate(sub_seq):
        y = _BOTTOM_Y0 - i * _BOTTOM_ROW_H
        ax.text(0.52, y, f"{lb}: {pr}, {_dot_fmt(dt)}", color=t["text"],
                fontsize=_BOTTOM_FS * fs, ha="left", va="center", zorder=8,
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
    """解析 '标签:起点:终点:备注[:方向]'。方向 up/down/auto（默认 auto）。"""
    parts = s.split(":", 4)
    if len(parts) not in (4, 5):
        raise argparse.ArgumentTypeError(
            f"浪段格式应为 标签:起点:终点:备注[:方向up/down/auto]，收到: {s}")
    direction = parts[4] if len(parts) == 5 else "auto"
    if direction not in ("up", "down", "auto"):
        raise argparse.ArgumentTypeError(f"浪段方向只支持 up/down/auto，收到: {direction}")
    return (parts[0], int(parts[1]), int(parts[2]), parts[3], direction)


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
                        "目录|方案|图型（方案∈{主方案,替代方案}，图型∈{全景,放大}），"
                        "如 --out-auto \"C:/x/图表|主方案|全景\" → DIR/主方案_全景.png；"
                        "与 --out 互斥，命名约定单一出处，禁止手工另起名")
    p.add_argument("--title", required=True, help="图标题（含分析级别与方案名）")
    p.add_argument("--waves", nargs="*", type=parse_wave_arg, default=[],
                   help="浪段标注：标签:起点:终点:备注[:方向up/down/auto]；"
                        "方向默认 auto=按端点极端价位判定（终点高/低均高于起点→上行，"
                        "均低→下行，区间重叠回退收盘比较，R20 口径）")
    p.add_argument("--invalid", nargs="*", type=parse_price_arg, default=[],
                   help="失效价位：价格:标签（含规则编号）")
    p.add_argument("--level", nargs="*", type=parse_price_arg, default=[],
                   help="关键阻力/支撑：价格:标签（蓝色点划线，区别于失效价位）")
    p.add_argument("--current", type=float, default=None, help="当前价格")
    p.add_argument("--fib", nargs="*", type=parse_fib_arg, default=[],
                   help="斐波那契目标区：低:高:标签")
    p.add_argument("--last", type=int, default=None, help="只绘制最近 N 根 K 线")
    p.add_argument("--gann", nargs="*", default=[], metavar="FAN",
                   help="江恩角度线扇形（可选叠加）：起点索引:起点价格[:刻度][:方向up/down]；"
                        "刻度 = 每根 K 线 1 单位价格（分档见项目默认口径 D23），须披露")
    p.add_argument("--gann-auto-scale", action="store_true",
                   help="江恩刻度自动分档（D23）：--gann 省略刻度，按锚点价格量级取 "
                        "0.05/0.5/5/50，图例与输出披露刻度值；同一分析内禁止换刻度")
    p.add_argument("--gann-index", action="store_true",
                   help="标的为指数点位：--gann-auto-scale 时分档固定取 50（D23）")
    p.add_argument("--font-scale", type=float, default=1.0,
                   help="字号缩放（放大图建议 1.2–1.4）")
    p.add_argument("--theme", default="dark", choices=("dark", "light"),
                   help="主题：dark（默认，深色画布亮色连线）/ light（旧浅色）")
    p.add_argument("--path", nargs="*", type=parse_path_arg, default=[],
                   help="连续浪路径：标签:索引:索引:...（按序连成一条带箭头折线，"
                        "端点加编号框）。例：--path \"[1]:4165:4174:4178:4223:4295:4484\"")
    p.add_argument("--channel", nargs="*", type=parse_channel_arg, default=[],
                   help="推动浪平行通道：1浪高点索引:3浪高点索引:2浪低点索引。"
                        "例：--channel \"4174:4223:4178\"")
    p.add_argument("--pivot", nargs="*", type=parse_pivot_arg, default=[],
                   help="大级别浪标注：标注:索引[:peak/trough]（如 [I]:4484:peak），挂在对应端点，"
                        "白框大号字，与子浪编号框区分（分级标注）。peak=波峰标上方默认、"
                        "trough=波谷标下方。例：--pivot \"[I]:4484:peak\" \"[II]:4612:trough\"")
    args = p.parse_args()

    # 输出路径：--out-auto（embed 固定命名权威）优先，与 --out 互斥
    if args.out_auto:
        if args.out:
            p.error("--out 与 --out-auto 只能二选一")
        parts = args.out_auto.split("|")
        if len(parts) != 3 or parts[1] not in SCHEME_NAMES or parts[2] not in CHART_VIEWS:
            p.error('--out-auto 格式应为 "目录|主方案|全景"（方案∈{主方案,替代方案}，图型∈{全景,放大}），'
                    "收到: %s" % args.out_auto)
        out_path = os.path.join(parts[0], chart_png(parts[1], parts[2]))
    elif args.out:
        out_path = args.out
    else:
        p.error("必须提供 --out 或 --out-auto 之一")

    df = load_ohlc(args.csv, set_date_index=True)

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

    draw_chart(df, out_path, args.title, args.waves, args.invalid,
               current_price=args.current, fib_zones=args.fib, last_n=args.last,
               levels=args.level, font_scale=args.font_scale,
               gann_fans=gann_fans, theme=args.theme, paths=args.path,
               channels=args.channel, pivots=args.pivot)


if __name__ == "__main__":
    main()
