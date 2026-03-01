import pandas as pd


def align_calendar(df):
    dates = pd.Series(df["date"].unique()).sort_values().to_list()
    sectors = df["sector"].dropna().unique().tolist()
    out = []
    for s in sectors:
        g = df[df["sector"] == s].sort_values("date").drop_duplicates("date", keep="last")
        g = g.set_index("date").reindex(dates)
        g["sector"] = s
        g = g.reset_index().rename(columns={"index": "date"})
        out.append(g)
    return pd.concat(out, ignore_index=True)


def _normalize_numeric(df):
    out = df.copy()
    for col in ["pct", "amount", "volume", "turnover", "open", "high", "low", "close"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _trade_flag(df):
    flag = pd.Series(False, index=df.index)
    if "amount" in df:
        flag = flag | (df["amount"].fillna(0) > 0)
    if "volume" in df:
        flag = flag | (df["volume"].fillna(0) > 0)
    if "pct" in df:
        flag = flag | (df["pct"].notna() & (df["pct"] != 0))
    if "turnover" in df:
        flag = flag | (df["turnover"].fillna(0) > 0)
    return flag


def trim_to_first_trade(df):
    out = []
    for sector, g in df.groupby("sector"):
        g = g.sort_values("date")
        flag = _trade_flag(g)
        if flag.any():
            first_idx = flag.idxmax()
            g = g.loc[g.index >= first_idx]
        out.append(g)
    if not out:
        return df
    return pd.concat(out, ignore_index=True)


def keep_common_trade_dates(df):
    flag = _trade_flag(df)
    tmp = df.assign(_trade=flag)
    common = tmp.groupby("date")["_trade"].all()
    dates = common[common].index
    return df[df["date"].isin(dates)]


def crop_to_market_dates(df, market_name="上证"):
    if not market_name:
        return df
    g = df[df["sector"] == market_name]
    if g.empty:
        return df
    dates = g[_trade_flag(g)]["date"].unique()
    if len(dates) == 0:
        return df
    return df[df["date"].isin(dates)]


def fill_missing(df, pct_fill=0.0, amount_fill=0.0, volume_fill=0.0, turnover_fill=0.0, open_fill=None, high_fill=None, low_fill=None, close_fill=None):
    out = df.copy()
    if "pct" in out:
        out["pct"] = pd.to_numeric(out["pct"], errors="coerce").fillna(pct_fill)
    if "amount" in out:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(amount_fill)
    if "volume" in out:
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(volume_fill)
    if "turnover" in out:
        out["turnover"] = pd.to_numeric(out["turnover"], errors="coerce").fillna(turnover_fill)
    if "open" in out:
        out["open"] = pd.to_numeric(out["open"], errors="coerce")
        if open_fill is not None:
            out["open"] = out["open"].fillna(open_fill)
    if "high" in out:
        out["high"] = pd.to_numeric(out["high"], errors="coerce")
        if high_fill is not None:
            out["high"] = out["high"].fillna(high_fill)
    if "low" in out:
        out["low"] = pd.to_numeric(out["low"], errors="coerce")
        if low_fill is not None:
            out["low"] = out["low"].fillna(low_fill)
    if "close" in out:
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
        if close_fill is not None:
            out["close"] = out["close"].fillna(close_fill)
    return out


def clean_for_features(df, market_name="上证"):
    out = _normalize_numeric(df)
    out = out.dropna(subset=["date", "sector"])
    out = out.sort_values(["date", "sector"])
    if "code" in out.columns:
        out = out.drop_duplicates(subset=["date", "code"], keep="last")
    else:
        out = out.drop_duplicates(subset=["date", "sector"], keep="last")
    out = fill_missing(out)
    return out
