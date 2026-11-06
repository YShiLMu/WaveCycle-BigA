#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""minute_slice.py —— 分钟分形层取数与动态切片（细分深度第 4 层：60m/30m/15m 级联）

定位：分钟层「取数 → 全量算指标 → 锚点对齐 → 动态切片 → 契约 CSV + 元数据 +
指标 sidecar + 分形 Pivot 候选事实」的唯一入口。脚本只产出事实（切片、极值、
摆动候选），浪级/形态/完成状态裁决一律由模型执行（tool_discipline 总原则）。

三轮交互中的位置：
  第 2 轮（日线 T_d0 → 60m 切片）：
    python minute_slice.py --code sh688137 --freq 60 \
        --anchor-date 2026-10-15 --anchor-kind L [--daily-csv 日线.csv]
  第 3 轮（60m 锚点 → 30m + 15m 联合切片）：
    python minute_slice.py --code sh688137 --freq 30,15 \
        --anchor-ts "2026-10-15 10:30" --anchor-kind L

取数口径（2026-11-03 端点实测，references/data.md 分钟分形层切片协议）：
  - 唯一主源：腾讯 mkline（全板块可用；tdx/mootdx 已作废，同花顺无真 30/60 分）；
  - 固定按上限 800 根请求（>800 会静默回退 320，本脚本绝不请求超过 800 并校验
    返回根数）；无翻页能力，只能拿最近 N 根；
  - 腾讯分钟线字段序为 时间,开,收,高,低,量(手)——close 在 high 前，落盘前强制
    重排为契约列序 date,open,high,low,close,volume（references/workflow.md 第 1 步第 1 节）；
  - 时间戳标 bar 结束时刻（60m 单日 4 根 = 10:30/11:30/14:00/15:00）；
  - 分钟线全源不复权（none），与日线 qfq/hfq 只做时间戳锚定与结构映射，
    禁止跨周期混算价格（references/data.md）。

切片规则（09 默认口径 D42）：
  - 60m：锚点 bar（日级锚点用当日 argmin(low)/argmax(high) 定位，并列取最早）
    左留 8 根前浪缓冲，切至最新；锚点后不足 32 根则向前保底取满 32+8；
  - 30m：锚点 bar（时间戳精确匹配）左留 4 根缓冲，保底 24+4；
  - 15m：起点取「30m 切片最新摆动段起点」与「最新往前 32 根」的较早者，
    窗口上限 64 根；
  - 指标（MACD(12,26,9)/RSI(14)/MA(5,10,20,60)）在全量 800 根上先算好，
    再随切片同步截取，避免切片开头指标为 NaN；指标仅作辅助共振证据，
    禁入结构判定（workflow 第 1 步错误 5）。

退出码：0 = 完成；1 = 数据自检不通过 / 取数或锚定失败（见 stderr 与披露行）。
输出全部写入 --out-dir（缺省在系统临时目录新建 wavecycle_m_* 目录），
禁止落盘到仓库或分析输出目录。
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request

import pandas as pd

from ohlc_io import load_ohlc, validate_ohlc
from swings import fractal_pivots, fmt_price

TX_MKLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
TX_REFERER = "https://gu.qq.com/"
FETCH_COUNT = 800            # 腾讯 mkline 实测硬上限；>800 静默回退 320，禁止请求更大值
TIMEOUT = 20

BAR_PER_DAY = {60: 4, 30: 8, 15: 16}     # A 股 bar 密度（D42）
MIN_BARS = {60: 32, 30: 24, 15: 32}      # 保底根数（当前浪段）
BUFFER_BARS = {60: 8, 30: 4, 15: 0}      # 前浪上下文缓冲（左側）
MAX_15M_BARS = 64                        # 15m 窗口上限
EXTREME_TOLERANCE = 0.005                # 跨源极值核对容差 0.5%（实测腾讯与同花顺差 0.3–0.4%）

FREQ_ARG = {"60": 60, "30": 30, "15": 15}
KINDS = ("H", "L")


# ---------------------------------------------------------------------------
# 1. 取数（vendor 细节隔离在本节）
# ---------------------------------------------------------------------------

def fetch_tencent_minute(code, freq):
    """腾讯 mkline 取数 → 契约列序 DataFrame（date 列为 'YYYY-MM-DD HH:MM' 字符串）。

    返回 (df, note)；note 为披露行（截断/根数校验等）。失败抛 SystemExit。
    """
    url = "%s?param=%s,m%d,,%d" % (TX_MKLINE_URL, code, freq, FETCH_COUNT)
    req = urllib.request.Request(url, headers={"Referer": TX_REFERER,
                                               "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("[错误] 腾讯 mkline 取数失败（%s）：%s——按数据纪律披露缺证，禁止编造" % (code, exc))
    node = (payload.get("data") or {}).get(code) or {}
    bars = node.get("m%d" % freq) or []
    if not bars:
        raise SystemExit("[错误] 腾讯 mkline 返回空（%s m%d）——核对代码前缀与标的，按数据纪律披露缺证"
                         % (code, freq))
    if len(bars) > FETCH_COUNT:
        raise SystemExit("[错误] 腾讯 mkline 返回 %d 根超过上限 %d——口径变更，须人工核验后再用"
                         % (len(bars), FETCH_COUNT))
    rows = []
    for b in bars:
        # 字段序实测：时间,开,收,高,低,量(手),{},换手率基点——重排为契约列序
        ts, o, c, h, l, v = b[0], float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])
        rows.append(("%s-%s-%s %s:%s" % (ts[:4], ts[4:6], ts[6:8], ts[8:10], ts[10:12]), o, h, l, c, v))
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    note = "腾讯 mkline 实际返回 %d 根（请求 %d）" % (len(df), FETCH_COUNT)
    return df, note


# ---------------------------------------------------------------------------
# 2. 指标（先全量计算，后随切片截取；仅辅助共振证据，禁入结构判定）
# ---------------------------------------------------------------------------

def compute_indicators(df):
    """在全量帧上计算 MACD(12,26,9)/RSI(14)/MA(5,10,20,60)，返回指标 DataFrame。"""
    close = df["close"].astype(float)
    dif = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    ind = pd.DataFrame({"date": df["date"], "macd_dif": dif, "macd_dea": dea,
                        "macd_bar": 2 * (dif - dea), "rsi14": rsi})
    for n in (5, 10, 20, 60):
        ind["ma%d" % n] = close.rolling(n).mean()
    return ind.round(4)


# ---------------------------------------------------------------------------
# 3. 锚点对齐与切片
# ---------------------------------------------------------------------------

def locate_anchor_by_day(df, day, kind):
    """日级锚点 → 当日极值 bar 的帧内位置：L 取 argmin(low)、H 取 argmax(high)，
    并列时 idxmin/idxmax 天然取最早一根（日内极值排名定位，不跨源比价格）。"""
    mask = df["date"].str[:10] == day
    if not mask.any():
        near = sorted({d[:10] for d in df["date"]})
        raise SystemExit("[错误] 锚点日 %s 不在 60m 数据内（可得 %s … %s）——"
                         "核对 T_d0 是否节假日/停牌，或锚点超出 800 根覆盖" % (day, near[0], near[-1]))
    day_df = df.loc[mask]
    pos = (day_df["low"].idxmin() if kind == "L" else day_df["high"].idxmax())
    return int(pos)


def locate_anchor_by_ts(df, ts):
    """bar 级锚点（'YYYY-MM-DD HH:MM'）→ 帧内位置，精确匹配。"""
    hit = df.index[df["date"] == ts]
    if len(hit) == 0:
        same_day = df.loc[df["date"].str[:10] == ts[:10], "date"].tolist()
        raise SystemExit("[错误] 锚点时间戳 %s 不在数据内；当日可得 bar：%s"
                         % (ts, "、".join(same_day) or "（当日无数据）"))
    return int(hit[0])


def slice_from_anchor(df, anchor_pos, freq):
    """切片：锚点左留缓冲、锚点后保底 MIN_BARS 根、右端取到最新。

    返回 (切片 DataFrame, 披露行列表)。start 被数据边界钳住时如实披露。
    """
    notes = []
    n = len(df)
    start = min(anchor_pos - BUFFER_BARS[freq], n - (MIN_BARS[freq] + BUFFER_BARS[freq]))
    if start < 0:
        start = 0
        notes.append("切片被数据起点钳位：缓冲/保底根数不足（60m 覆盖约 %d 个交易日）"
                     % (n // BAR_PER_DAY[freq]))
    if n - anchor_pos < MIN_BARS[freq]:
        notes.append("锚点后仅 %d 根（不足保底 %d 根）：已向前保底扩取，前浪缓冲段相应加深"
                     % (n - anchor_pos, MIN_BARS[freq]))
    return df.iloc[start:].reset_index(drop=True), notes


def slice_15m(df15, pivot_ts_30m):
    """15m 窗口：起点 = 30m 最新摆动段起点 与 最新往前 32 根 的较早者，上限 64 根。"""
    n = len(df15)
    by_min = max(0, n - MIN_BARS[15])
    start = by_min
    if pivot_ts_30m is not None:
        hit = df15.index[df15["date"] <= pivot_ts_30m]
        if len(hit):
            start = min(by_min, int(hit[-1]))
    start = max(start, n - MAX_15M_BARS)
    notes = ["15m 窗口起点规则：min(30m 最新摆动段起点 %s, 最新往前 %d 根)，上限 %d 根"
             % (pivot_ts_30m or "（30m 无摆动点，退化为保底）", MIN_BARS[15], MAX_15M_BARS)]
    return df15.iloc[start:].reset_index(drop=True), notes


def pivot_facts(df_slice, k):
    """切片上的分形 Pivot 候选（事实，不裁决浪级）；索引 = 切片 CSV 数据行号（0 起）。"""
    piv = fractal_pivots(df_slice["high"].astype(float).tolist(),
                         df_slice["low"].astype(float).tolist(), k)
    return [(idx, df_slice["date"].iloc[idx], price, kind) for idx, price, kind in piv]


def cross_check_daily(daily_csv, day, kind, day_bars):
    """锚点日分钟聚合极值 vs 日线极值的容差核对（0.5%）；超差披露不阻断。"""
    daily = load_ohlc(daily_csv)
    hit = daily.loc[daily["date"].dt.strftime("%Y-%m-%d") == day]
    if hit.empty:
        return ["跨源核对：日线 CSV 中无 %s——跳过（披露：锚点日未与日线核对）" % day]
    col = "low" if kind == "L" else "high"
    d_val = float(hit.iloc[0][col])
    m_val = float(day_bars[col].min() if kind == "L" else day_bars[col].max())
    diff = abs(m_val - d_val) / d_val
    if diff <= EXTREME_TOLERANCE:
        return ["跨源核对：锚点日 %s 分钟聚合 %s=%.3f vs 日线 %.3f，偏差 %.2f%%（容差 0.5%% 内）"
                % (day, col, m_val, d_val, diff * 100)]
    return ["跨源核对超差披露：锚点日 %s 分钟聚合 %s=%.3f vs 日线 %.3f，偏差 %.2f%% > 0.5%%——"
            "核对数据源一致性/复权口径（分钟线为 none，日线若为 qfq 属预期差异）"
            % (day, col, m_val, d_val, diff * 100)]


# ---------------------------------------------------------------------------
# 4. 落盘（契约 CSV + 元数据 + 指标 sidecar）
# ---------------------------------------------------------------------------

def write_outputs(df_slice, ind_slice, meta, out_dir, stem):
    csv_path = os.path.join(out_dir, stem + ".csv")
    df_slice.to_csv(csv_path, index=False, encoding="utf-8")
    ind_path = os.path.join(out_dir, stem + ".indicators.csv")
    ind_slice.to_csv(ind_path, index=False, encoding="utf-8", na_rep="")
    meta = dict(meta)
    meta["csv_sha256"] = hashlib.sha256(open(csv_path, "rb").read()).hexdigest()
    meta_path = os.path.join(out_dir, stem + ".metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return csv_path, meta_path, ind_path


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(
        description="分钟分形层取数与动态切片（60m/30m/15m 级联；脚本出事实，浪级裁决由模型）")
    p.add_argument("--code", required=True, help="带市场前缀代码，如 sh688137（禁止 .SH/.SZ 后缀）")
    p.add_argument("--freq", required=True,
                   help="60（第 2 轮，配 --anchor-date）或 30,15（第 3 轮，配 --anchor-ts）")
    p.add_argument("--anchor-date", default=None,
                   help="日级锚点 T_d0（YYYY-MM-DD，仅 --freq 60）：当日极值 bar 由日内排名定位")
    p.add_argument("--anchor-ts", default=None,
                   help="bar 级锚点 T_60m0（'YYYY-MM-DD HH:MM'，--freq 30,15 时必填）：精确匹配")
    p.add_argument("--anchor-kind", required=True, choices=KINDS,
                   help="锚点极值属性：H=高点（前一浪终点为顶），L=低点")
    p.add_argument("--daily-csv", default=None,
                   help="可选：第 1 轮日线契约 CSV，用于锚点日跨源极值容差核对（0.5%%）")
    p.add_argument("--k", type=int, default=5, help="分形 Pivot 窗口（默认 5，同 swings 口径）")
    p.add_argument("--out-dir", default=None,
                   help="输出目录（缺省在系统临时目录新建 wavecycle_m_*；禁止指向仓库/分析输出）")
    args = p.parse_args(argv)

    import re
    if not re.fullmatch(r"(sh|sz|bj)\d{6}", args.code):
        p.error("--code 须为 sh/sz/bj 前缀 + 6 位数字（如 sh688137），禁止 .SH/.SZ 后缀")
    freqs = [FREQ_ARG[t] for t in args.freq.split(",") if t in FREQ_ARG]
    if sorted(set(freqs)) == [60]:
        if not args.anchor_date:
            p.error("--freq 60（第 2 轮）必须提供 --anchor-date")
    elif sorted(set(freqs)) == [15, 30]:
        if not args.anchor_ts:
            p.error("--freq 30,15（第 3 轮）必须提供 --anchor-ts")
    else:
        p.error("--freq 只支持 60 或 30,15 两种组合（对应第 2/3 轮交互）")

    out_dir = args.out_dir or tempfile.mkdtemp(prefix="wavecycle_m_")
    os.makedirs(out_dir, exist_ok=True)
    print("[分钟分形层切片] code=%s freq=%s out=%s" % (args.code, args.freq, out_dir))
    print("[数据源锁定] 单次分析单一源：腾讯 mkline（不复权 none；禁止跨源拼接、禁止与日线混算价格）")

    pivot_ts_30m = None
    for freq in (60, 30, 15):
        if freq not in freqs:
            continue
        full, fetch_note = fetch_tencent_minute(args.code, freq)
        try:
            validate_ohlc(full)
        except ValueError as exc:
            print("[错误] m%d 数据自检不通过：%s——禁止带病数浪" % (freq, exc), file=sys.stderr)
            return 1
        indicators = compute_indicators(full)

        if freq == 60:
            anchor_pos = locate_anchor_by_day(full, args.anchor_date, args.anchor_kind)
            anchor_label = "T_d0=%s(%s)" % (args.anchor_date, args.anchor_kind)
        elif freq == 30:
            anchor_pos = locate_anchor_by_ts(full, args.anchor_ts)
            anchor_label = "T_60m0=%s(%s)" % (args.anchor_ts, args.anchor_kind)
        else:
            anchor_pos = None
            anchor_label = "15m 窗口（随 30m 摆动段对齐）"

        if freq == 15:
            sliced, slice_notes = slice_15m(full, pivot_ts_30m)
        else:
            sliced, slice_notes = slice_from_anchor(full, anchor_pos, freq)
        anchor_bar = full["date"].iloc[anchor_pos] if anchor_pos is not None else None
        # 切片均为「切到最新」的尾部窗口：指标按尾部长度同步截取（先全量算、后切）
        ind_sliced = indicators.iloc[len(full) - len(sliced):].reset_index(drop=True)

        stem = "%s_m%d" % (args.code, freq)
        meta = {"source": "腾讯 mkline", "fq": "none",
                "as_of": full["date"].iloc[-1] + ":00+08:00", "timezone": "Asia/Shanghai",
                "freq": "m%d" % freq, "anchor": anchor_label,
                "anchor_bar": anchor_bar or "",
                "bar_time_labeling": "bar 结束时刻（60m=10:30/11:30/14:00/15:00）",
                "volume_unit": "手", "slice_rule": "D42（保底/缓冲见 09 默认口径）",
                "indicator_warmup": "指标在全量 %d 根上先算后切片" % len(full)}
        csv_path, meta_path, ind_path = write_outputs(sliced, ind_sliced, meta, out_dir, stem)

        print("\n== m%d 切片 ==" % freq)
        print("  %s" % fetch_note)
        print("  锚点：%s → bar %s" % (anchor_label, anchor_bar or "（窗口规则定位）"))
        print("  切片：%d 根，%s 至 %s（缓冲段 %s 起为前浪上下文，不参与当前浪数浪）"
              % (len(sliced), sliced["date"].iloc[0], sliced["date"].iloc[-1],
                 sliced["date"].iloc[0]))
        for note in slice_notes:
            print("  披露：%s" % note)
        if freq == 60 and args.daily_csv:
            day_bars = full.loc[full["date"].str[:10] == args.anchor_date]
            for note in cross_check_daily(args.daily_csv, args.anchor_date, args.anchor_kind, day_bars):
                print("  %s" % note)
        print("  CSV：%s\n  元数据：%s\n  指标：%s（MACD/RSI/MA 仅辅助共振证据，禁入结构判定）"
              % (csv_path, meta_path, ind_path))

        pivots = pivot_facts(sliced, args.k)
        print("  分形 Pivot 候选（k=%d，共 %d 个；索引=切片 CSV 行号，EG-05 含影线口径）："
              % (args.k, len(pivots)))
        for idx, ts, price, kind in pivots:
            print("    idx=%-4d %s  %s %s" % (idx, ts, kind, fmt_price(price)))
        if freq == 30:
            pivot_ts_30m = pivots[-1][1] if pivots else None

    print("\n[完成] 切片、元数据与指标 sidecar 已就绪；浪级/形态/完成状态由模型裁决（EG-01/EG-03）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
