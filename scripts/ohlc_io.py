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
import hashlib
import json
import os
import re

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
    """日期/时刻值 → 'YYYY-MM-DD'（日级）或 'YYYY-MM-DD HH:MM'（分钟级保留时刻）；None → '-'。"""
    if d is None:
        return "-"
    ts = pd.Timestamp(d)
    if ts.hour or ts.minute or ts.second:
        return ts.strftime("%Y-%m-%d %H:%M")
    return ts.strftime("%Y-%m-%d")


def check_metadata(csv_path, metadata_path=None, source="", fq="", require=False):
    """校验数据声明与 CSV 的绑定；不把哈希一致解释为来源真实性已验证。

    自动发现同名 ``<CSV去扩展名>.metadata.json``；旧 key=value 声明可读，
    缺哈希时仅作未绑定声明。正式链用 require=True 要求五个字段完整。
    """
    candidate = os.path.splitext(os.path.abspath(csv_path))[0] + ".metadata.json"
    path = metadata_path or (candidate if os.path.isfile(candidate) else None)
    if path is None:
        if require:
            raise ValueError("正式数据链要求元数据：提供 --metadata 或同名 .metadata.json")
        return {"source": source, "fq": fq, "timezone": "未知",
                "as_of": None, "bound": False, "note": "未绑定元数据；数据源与复权仅为调用者声明"}
    with open(path, encoding="utf-8-sig") as stream:
        text = stream.read()
    if text.lstrip().startswith("{"):
        def unique_fields(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("元数据字段重复：%s" % key)
                result[key] = value
            return result
        meta = json.loads(text, object_pairs_hook=unique_fields)
        if not isinstance(meta, dict):
            raise ValueError("元数据必须为 JSON 对象")
    else:
        meta = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError("旧元数据每行须为 key=value")
            key, value = line.split("=", 1)
            if key.strip() in meta:
                raise ValueError("元数据字段重复：%s" % key.strip())
            meta[key.strip()] = value.strip()
        if "adj" in meta and "fq" not in meta:
            meta["fq"] = meta["adj"]
    required = ("source", "fq", "as_of", "timezone", "csv_sha256")
    for key, value in meta.items():
        if key in required and (not isinstance(value, str) or not value.strip()):
            raise ValueError("元数据 %s 须为非空字符串" % key)
    if require and any(not meta.get(key) for key in required):
        raise ValueError("正式数据链元数据缺少字段：%s" % ", ".join(key for key in required if not meta.get(key)))
    for key, declared in (("source", source), ("fq", fq)):
        if declared and meta.get(key) and declared.strip() != meta[key].strip():
            raise ValueError("--%s 与元数据冲突" % key)
    digest = meta.get("csv_sha256")
    if digest:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("csv_sha256 须为 64 位十六进制 SHA-256")
        with open(csv_path, "rb") as stream:
            actual = hashlib.sha256(stream.read()).hexdigest()
        if digest.lower() != actual:
            raise ValueError("元数据 CSV 哈希不匹配，禁止沿用旧数据声明")
    as_of = meta.get("as_of")
    if as_of:
        try:
            as_of_ts = pd.Timestamp(as_of)
            if pd.isna(as_of_ts):
                raise ValueError("空日期")
            csv_dates = pd.read_csv(csv_path, usecols=["date"])["date"].astype(str)
            latest = max(pd.Timestamp(value) for value in csv_dates)
            # date-only 声明按当天覆盖；未知时区不替数据猜测 UTC 偏移。
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{8}", as_of):
                earlier = as_of_ts.date() < latest.date()
            elif as_of_ts.tzinfo is not None and latest.tzinfo is not None:
                earlier = as_of_ts.tz_convert("UTC") < latest.tz_convert("UTC")
            else:
                earlier = as_of_ts.tz_localize(None) < latest.tz_localize(None)
            if earlier:
                raise ValueError("as_of 早于 CSV 最新 bar")
        except (TypeError, ValueError) as exc:
            raise ValueError("元数据 as_of 日期无效或与 CSV 不一致：%s" % exc) from exc
    adjust = meta.get("adjust")
    if adjust is not None:
        if not isinstance(adjust, dict):
            raise ValueError("元数据 adjust 须为对象")
        if adjust.get("kind") != meta.get("fq"):
            raise ValueError("元数据 adjust.kind 与 fq 不一致")
        if not isinstance(adjust.get("product_constant"), bool):
            raise ValueError("元数据 adjust.product_constant 须为布尔值")
        factor_digest = adjust.get("factor_sha256")
        if not isinstance(factor_digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", factor_digest):
            raise ValueError("元数据 adjust.factor_sha256 须为 64 位十六进制 SHA-256")
    return {"source": meta.get("source", source), "fq": meta.get("fq", fq),
            "timezone": meta.get("timezone", "未知"), "as_of": as_of,
            "adjust": adjust,
            "bound": bool(digest),
            "note": ("CSV 哈希绑定通过；来源与复权为元数据声明，未独立验证" if digest
                     else "未绑定元数据（缺 csv_sha256）；数据源与复权仅为声明")}
