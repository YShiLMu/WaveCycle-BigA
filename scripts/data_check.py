#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据自检与数据基准输出脚本（workflow 第 1 步 1.4/1.5 节，D28 口径）。

用途：进入数浪前对行情 CSV 执行数据自检，输出《数据自检表》（markdown，
与 05_模板_templates/01_分析报告_report.md 第 1 章格式同构）与数据基准
四要素。本脚本只输出事实与机械判定结果，"是否盘中""循环覆盖是否足够"
等判断仍由模型结合披露事实作出（D28 明确口径）。

与 key_levels.py 的硬拦截不同：本脚本是自检器，坏数据不 raise，而是记为
"不通过"行并整体退出码 1，把完整自检表打出来供披露与退回取数。

检查项（自动判定）：
  1. 表头契约：date,open,high,low,close[,volume]
  2. OHLC 合理性：high ≥ low ≥ 0；open/close ∈ [low, high]；volume ≥ 0（如有）
  3. 日期升序、无重复、可解析（兼容 YYYY-MM-DD 与 YYYYMMDD）
  4. 复权口径已标注（--fq 提供）且全程一致（单文件天然一致）
  5. 数据源已标注（--source 提供）

披露项（脚本给事实、模型判定）：
  - 日历缺口（相邻 bar 间隔 > 3 天的区间列表，停牌/节假日由模型说明）
  - 数据根数与时间跨度（供"覆盖一个完整 5+3 循环"判断）
  - 最新 bar 日期 vs 当前日期（供"是否收盘"判断）
  - 区间极端价位（最高 high / 最低 low + 日期，R20 口径）

用法：
    python data_check.py --csv data.csv [--source 腾讯fqkline] [--fq qfq]

退出码：0 = 全部通过；1 = 存在"不通过"项。
CSV 列：date,open,high,low,close[,volume]（date 兼容 YYYY-MM-DD 与 YYYYMMDD）。
"""

import argparse
import datetime
import sys

import pandas as pd


def load_csv(csv_path):
    """读 CSV，返回 (df 或 None, 表头错误信息)。不做硬拦截，错误交由自检表披露。"""
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:  # noqa: BLE001 —— 自检器不抛，转披露
        return None, "CSV 读取失败：%s" % e
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        return None, "CSV 缺少列: %s" % sorted(missing)
    return df, None


def _parse_dates(df):
    """返回 (成功解析的 Series 或 None, 错误信息)。"""
    raw = df["date"].astype(str)
    try:
        if raw.str.contains("-").any():
            return pd.to_datetime(raw, errors="coerce"), None
        return pd.to_datetime(raw, format="%Y%m%d", errors="coerce"), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def _rows(mask, limit=10):
    """坏行号（按 CSV 数据行，含表头偏移 +2），最多列 limit 个。"""
    return [int(i) + 2 for i in df_index(mask)[:limit]]


def df_index(mask):
    return mask.index[mask]


def run_checks(df, fq, source):
    """执行全部检查，返回 (rows, facts)。
    rows: [(检查项, 判定, 说明)]；facts: 披露事实 dict（循环覆盖/缺口/极值/最新bar）。"""
    rows = []
    facts = {}
    n = len(df)

    # ---- 1/2. OHLC 合理性 ----
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    o = df["open"].astype(float)
    c = df["close"].astype(float)
    bad = []
    m = h < l
    if m.any():
        bad.append("high<low 行 %s" % _rows(m))
    m = l < 0
    if m.any():
        bad.append("low<0 行 %s" % _rows(m))
    m = ((o < l - 1e-9) | (o > h + 1e-9))
    if m.any():
        bad.append("open 超出 [low,high] 行 %s" % _rows(m))
    m = ((c < l - 1e-9) | (c > h + 1e-9))
    if m.any():
        bad.append("close 超出 [low,high] 行 %s" % _rows(m))
    if (h.isna() | l.isna() | o.isna() | c.isna()).any():
        bad.append("OHLC 存在缺失值 行 %s" % _rows(h.isna() | l.isna() | o.isna() | c.isna()))
    if bad:
        rows.append(("OHLC 合理性", "不通过", "；".join(bad)))
    else:
        rows.append(("OHLC 合理性", "通过", "high≥low≥0，open/close 均在区间内"))

    # ---- volume ----
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        m = v < 0
        if m.any():
            rows.append(("volume ≥ 0", "不通过", "volume<0 行 %s" % _rows(m)))
        else:
            rows.append(("volume ≥ 0", "通过", ""))
    else:
        rows.append(("volume ≥ 0", "不适用", "CSV 无 volume 列"))

    # ---- 3. 日期升序、无重复、可解析 ----
    dates, derr = _parse_dates(df)
    if dates is None or dates.isna().any():
        bad_d = "日期解析失败（%s）" % derr if derr else "日期无法解析 行 %s" % _rows(dates.isna())
        rows.append(("日期升序、无重复、可解析", "不通过", bad_d))
    else:
        dup = dates.duplicated()
        if dup.any():
            rows.append(("日期升序、无重复、可解析", "不通过",
                         "日期重复：%s" % sorted(dates[dup].dt.strftime("%Y-%m-%d").unique()[:5])))
        elif not dates.is_monotonic_increasing:
            rows.append(("日期升序、无重复、可解析", "不通过", "日期未按升序排列"))
        else:
            rows.append(("日期升序、无重复、可解析", "通过", "%d 根，%s 至 %s"
                         % (n, dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d"))))
    # 缺口披露（解析成功才做）
    if dates is not None and not dates.isna().any():
        delta = dates.diff().dt.days
        gaps = dates[delta > 3]
        if len(gaps):
            facts["calendar_gaps"] = ["%s（前一根 %s，间隔 %d 天）"
                                      % (dates[i].strftime("%Y-%m-%d"),
                                         dates[i - 1].strftime("%Y-%m-%d"), int(delta.iloc[i]))
                                      for i in gaps.index][:10]
        else:
            facts["calendar_gaps"] = []

    # ---- 4/5. 复权与数据源标注 ----
    if fq:
        rows.append(("复权口径已标注且全程一致", "通过", "%s（单文件，全程一致）" % fq))
    else:
        rows.append(("复权口径已标注且全程一致", "不通过",
                     "未标注（--fq 未提供）；禁止声称未核实过的复权方式"))
    if source:
        rows.append(("数据源与截至时间已记录", "通过",
                     "%s；最新 bar %s" % (source, dates.iloc[-1].strftime("%Y-%m-%d")
                                          if dates is not None and not dates.isna().any() else "未知")))
    else:
        rows.append(("数据源与截至时间已记录", "不通过", "未标注（--source 未提供）"))

    # ---- 披露事实 ----
    if dates is not None and not dates.isna().any():
        facts["n_bars"] = n
        facts["date_range"] = [dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d")]
        facts["span_days"] = int((dates.iloc[-1] - dates.iloc[0]).days)
        facts["last_bar"] = dates.iloc[-1].strftime("%Y-%m-%d")
        facts["today"] = datetime.date.today().isoformat()
        # 极值用 pandas idxmax/idxmin（默认 skipna），全 NaN 时记 None，
        # 防止 np.argmax 命中 NaN 位置导致输出 "nan" 假事实
        facts["extremes"] = {
            "high": (float(h.max()), dates.iloc[int(h.idxmax())].strftime("%Y-%m-%d"))
                    if h.notna().any() else None,
            "low": (float(l.min()), dates.iloc[int(l.idxmin())].strftime("%Y-%m-%d"))
                   if l.notna().any() else None,
        }
        facts["last_close"] = float(c.iloc[-1]) if pd.notna(c.iloc[-1]) else None
    return rows, facts


def main(argv=None):
    ap = argparse.ArgumentParser(description="数据自检与数据基准输出（workflow 第 1 步 1.4/1.5，D28）")
    ap.add_argument("--csv", required=True, help="行情 CSV 路径")
    ap.add_argument("--source", default="", help="数据源标注（如：腾讯 fqkline / 东财 2.931152），未提供判不通过")
    ap.add_argument("--fq", default="", help="复权口径标注（none/qfq/hfq），未提供判不通过")
    args = ap.parse_args(argv)

    df, err = load_csv(args.csv)
    print("## 数据自检表（data_check.py）\n")
    print("| 检查项 | 判定结果 | 说明 |")
    print("| --- | --- | --- |")
    if df is None:
        print("| 表头契约 | 不通过 | %s |" % err)
        print("\n存在不通过项：退回重新取数或按数据获取协议降级，禁止带病数据进入数浪。")
        return 1
    rows, facts = run_checks(df, args.fq, args.source)
    for name, verdict, note in rows:
        print("| %s | %s | %s |" % (name, verdict, note))
    # 表头契约本身
    extra = set(df.columns) - {"date", "open", "high", "low", "close", "volume"}
    print("| 表头契约 | 通过 | date,open,high,low,close[,volume]%s |"
          % ("；含附加列 %s（已忽略）" % sorted(extra) if extra else ""))

    failed = [r for r in rows if r[1] == "不通过"]

    print("\n## 数据基准（四要素）\n")
    if facts:
        hi, hi_d = facts["extremes"]["high"] or (None, None)
        lo, lo_d = facts["extremes"]["low"] or (None, None)
        print("1. 数据时间范围：%s 至 %s（%d 根，跨度 %d 天）"
              % (facts["date_range"][0], facts["date_range"][1], facts["n_bars"], facts["span_days"]))
        if hi is not None and lo is not None:
            print("2. 区间极端价位（R20 极端价位口径）：最高 %.3f（%s）、最低 %.3f（%s）"
                  % (hi, hi_d, lo, lo_d))
        else:
            print("2. 区间极端价位：OHLC 存在缺失，无可靠极值可披露（见自检表不通过项）")
        if facts["last_close"] is not None and hi is not None and lo is not None:
            print("3. 当前价格位置：最新收盘 %.3f（区间分位 %.1f%%）"
                  % (facts["last_close"],
                     100 * (facts["last_close"] - lo) / (hi - lo) if hi > lo else 0.0))
        else:
            print("3. 当前价格位置：极值或最新收盘缺失，分位不可算（见自检表不通过项）")
        print("4. 复权方式 %s、数据源 %s、最新 bar %s（今天 %s，%s）"
              % (args.fq or "未标注", args.source or "未标注", facts["last_bar"], facts["today"],
                 "最新 bar 为今日——请判定是否已收盘" if facts["last_bar"] == facts["today"]
                 else "最新 bar 非今日，间隔 %d 天" % (datetime.date.fromisoformat(facts["today"])
                                                     - datetime.date.fromisoformat(facts["last_bar"])).days))
        if facts.get("calendar_gaps"):
            print("\n披露：日历缺口（停牌/节假日由模型说明）——%s" % "；".join(facts["calendar_gaps"]))
        print("\n披露：循环覆盖判定素材——共 %d 根 / %d 天，是否覆盖一个完整 5+3 循环由模型判定并披露。"
              % (facts["n_bars"], facts["span_days"]))
    else:
        print("（数据读取失败或日期不可解析，无基准可输出）")

    if failed:
        print("\n存在 %d 项不通过：退回重新取数或按数据获取协议第 4 节降级标注，禁止带病数据进入数浪。"
              % len(failed))
        return 1
    print("\n自检全部通过，可进入数浪。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
