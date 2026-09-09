# -*- coding: utf-8 -*-
"""OHLC CSV 读取与数据自检的共享实现（key_levels / ew_chart / invalidation_check 共用）。

分工口径：
  - 本模块提供 pandas 版读取 + 硬拦截式自检（坏数据 raise ValueError，行号按
    CSV 数据行 +2，workflow 第 1 步 1.5 口径）；
  - swings.py 保留纯 csv 版自实现：它依赖 # 注释行跳过与 has_volume 元组语义，
    且是「索引 = CSV 数据行号」基准的权威口径，不强行并入；
  - data_check.py 是自检器（坏数据不 raise，记「不通过」行整体退出码 1），检查
    项与本模块同口径但输出路径不同，不共用实现。
"""
import pandas as pd
import numpy as np


def validate_ohlc(df):
    """数据自检（workflow 第 1 步 1.5 口径）：high ≥ low ≥ 0、open/close 落在
    [low, high]、volume ≥ 0（如有）、日期升序无重复。坏数据直接报错（行号按 CSV）。"""

    if df.empty:
        raise ValueError("数据自检失败：分析窗口为空")
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df]
    if not np.isfinite(df[cols].astype(float).to_numpy()).all() or df["date"].isna().any():
        raise ValueError("数据自检失败：含缺失或非有限数值/日期")

    def rows(mask):
        return [int(i) + 2 for i in df.index[mask][:10]]

    h = df["high"].astype(float)
    l = df["low"].astype(float)
    o = df["open"].astype(float)
    c = df["close"].astype(float)
    if (h < l).any():
        raise ValueError("数据自检失败：high < low 的行号 %s" % rows(h < l))
    if (l < 0).any():
        raise ValueError("数据自检失败：low < 0 的行号 %s" % rows(l < 0))
    oob_o = (o < l - 1e-9) | (o > h + 1e-9)
    if oob_o.any():
        raise ValueError("数据自检失败：open 超出 [low, high] 的行号 %s" % rows(oob_o))
    oob_c = (c < l - 1e-9) | (c > h + 1e-9)
    if oob_c.any():
        raise ValueError("数据自检失败：close 超出 [low, high] 的行号 %s" % rows(oob_c))
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        if (v < 0).any():
            raise ValueError("数据自检失败：volume < 0 的行号 %s" % rows(v < 0))
    dup = df["date"].duplicated()
    if dup.any():
        raise ValueError("数据自检失败：日期重复：%s" % sorted(df.loc[dup, "date"].astype(str).head(5)))
    if not df["date"].is_monotonic_increasing:
        raise ValueError("数据自检失败：日期未按升序排列")


def select_range(df, start=None, end=None):
    """统一窗口，保留原始数据行索引；非法日期不静默过滤。"""
    dates = pd.to_datetime(df["date"].astype(str), errors="raise")
    if dates.isna().any():
        raise ValueError("数据包含缺失日期")
    mask = dates.notna()
    if start:
        mask &= dates >= pd.Timestamp(start)
    if end:
        mask &= dates <= pd.Timestamp(end)
    if not mask.any():
        raise ValueError("分析日期窗口为空")
    return df.loc[mask].copy()


def load_ohlc(csv_path, set_date_index=False, start=None, end=None):
    """读 OHLC CSV（date,open,high,low,close[,volume]），兼容 YYYY-MM-DD 与
    YYYYMMDD 两种日期写法；读取后执行 validate_ohlc 硬拦截。

    set_date_index=False（key_levels / invalidation_check 用）：返回带 datetime
    "date" 列的 DataFrame；
    set_date_index=True（ew_chart 用）：set_index("date").sort_index()，返回
    datetime 索引 DataFrame。

    日期列若为纯数字（如 20070801），pandas 会读成 int64；直接 pd.to_datetime(int)
    会被当成 Unix 纳秒时间戳 → 全部解析成 1970-01-01。必须先 astype(str) 再解析。
    """
    df = pd.read_csv(csv_path)
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("CSV 缺少列: %s" % sorted(missing))
    df["date"] = pd.to_datetime(df["date"].astype(str))
    df = select_range(df, start, end)
    validate_ohlc(df)
    if set_date_index:
        df = df.set_index("date").sort_index()
    return df


def fmt_date(d):
    """日期值 → 'YYYY-MM-DD'；None → '-'（判定表格的未发生占位）。"""
    return pd.Timestamp(d).strftime("%Y-%m-%d") if d is not None else "-"
